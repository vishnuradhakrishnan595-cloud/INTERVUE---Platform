
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import (
    IsCandidate,
    IsCompanyMember,
    IsHRStaff,
)

from accounts.utils import log_action

from ai_engine.models import AIRunLog
from ai_engine.services import interview as ai

from recruitment import services

from .models import (
    Interview,
    InterviewAnswer,
    InterviewFeedback,
    InterviewQuestion,
    IntegrityEvent,
)

from .serializers import (
    GenerateQuestionsSerializer,
    IntegrityEventSerializer,
    InterviewFeedbackSerializer,
    InterviewQuestionSerializer,
    InterviewSerializer,
    RescheduleSerializer,
    ReviewEventSerializer,
    SubmitAnswerSerializer,
)


SA = User.Role.SUPER_ADMIN
CAND = User.Role.CANDIDATE
INTV = User.Role.INTERVIEWER


# ================================================================
# HELPER FUNCTIONS
# ================================================================

def interviews_for(user):
    """
    Return interviews the current user is allowed to see.
    """

    queryset = Interview.objects.select_related(
        "application__candidate",
        "application__job__company",
        "interviewer",
    )

    if user.role == SA:
        return queryset

    if user.role == CAND:
        return queryset.filter(
            application__candidate=user
        )

    if user.role == INTV:
        return queryset.filter(
            interviewer=user
        )

    return queryset.filter(
        application__job__company_id=user.company_id
    )


def _contexts(interview):
    """
    Build job and candidate AI contexts.
    """

    application = interview.application

    return (
        services.build_job_context(
            application.job
        ),
        services.build_candidate_context(
            application
        ),
    )


def _require_ai_session(user, interview):
    """
    Candidates can access questions and answers only
    during an active AI-conducted interview.
    """

    if user.role == CAND:

        if not (
            interview.is_ai_conducted
            and interview.status == "in_progress"
        ):
            raise PermissionDenied(
                "Questions are only available to candidates "
                "during an active AI interview."
            )


def _filter_queryset(
    request,
    queryset,
    filter_fields=None,
    search_fields=None,
    ordering_fields=None,
):
    """
    Apply filtering, searching, and ordering without generics.

    Supported query parameters:
        ?status=scheduled
        ?round_type=technical
        ?search=Python
        ?ordering=-scheduled_at
    """

    filter_fields = filter_fields or []
    search_fields = search_fields or []
    ordering_fields = ordering_fields or []

    # ------------------------------------------------------------
    # Exact field filters
    # ------------------------------------------------------------

    for field in filter_fields:

        value = request.query_params.get(field)

        if value is not None and value != "":
            queryset = queryset.filter(
                **{field: value}
            )

    # ------------------------------------------------------------
    # Search
    # ------------------------------------------------------------

    search = request.query_params.get(
        "search",
        ""
    ).strip()

    if search and search_fields:

        condition = Q()

        for field in search_fields:

            condition |= Q(
                **{
                    f"{field}__icontains": search
                }
            )

        queryset = queryset.filter(condition)

    # ------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------

    ordering = request.query_params.get(
        "ordering",
        ""
    ).strip()

    if ordering:

        requested_fields = [
            field.strip()
            for field in ordering.split(",")
            if field.strip()
        ]

        valid_fields = []

        for field in requested_fields:

            field_name = field.lstrip("-")

            if field_name in ordering_fields:
                valid_fields.append(field)

        if valid_fields:
            queryset = queryset.order_by(
                *valid_fields
            )

    return queryset


def _next_question(interview):
    """
    Return the next unanswered question.

    If there are no pending questions, generate an
    adaptive follow-up question when the maximum
    question count has not been reached.
    """

    pending = (
        interview.questions
        .filter(answer__isnull=True)
        .order_by("order")
        .first()
    )

    if pending:
        return pending

    total = interview.questions.count()

    if total >= interview.max_questions:
        return None

    job_context, candidate_context = _contexts(
        interview
    )

    history = [
        {
            "text": question.text,
            "topic": question.topic,
            "difficulty": question.difficulty,
            "overall_score": question.answer.overall_score,
        }
        for question in (
            interview.questions
            .select_related("answer")
            .filter(answer__isnull=False)
            .order_by("order")
        )
    ]

    data = ai.next_question(
        job_context,
        candidate_context,
        history,
        interview.round_type,
    )

    return InterviewQuestion.objects.create(
        interview=interview,
        order=total + 1,
        text=data["text"],
        topic=data.get("topic", ""),
        difficulty=data.get("difficulty", "medium"),
        expected_points=data.get("expected_points", []),
        source="ai",
    )


# ================================================================
# INTERVIEW LIST + CREATE
# ================================================================

class InterviewListCreateView(APIView):
    """
    GET  /api/interviews/
    POST /api/interviews/
    """

    def get_permissions(self):

        if self.request.method == "POST":
            return [IsHRStaff()]

        return [IsAuthenticated()]

    def get_queryset(self):

        return interviews_for(
            self.request.user
        )

    def get(self, request):
        """
        List interviews accessible to the current user.

        Optional filters:
            status
            round_type
            application
            interviewer
            is_ai_conducted
            search
            ordering
        """

        queryset = self.get_queryset()

        queryset = _filter_queryset(
            request,
            queryset,
            filter_fields=[
                "status",
                "round_type",
                "application",
                "interviewer",
                "is_ai_conducted",
            ],
            search_fields=[
                "application__candidate__first_name",
                "application__candidate__last_name",
                "title",
            ],
            ordering_fields=[
                "scheduled_at",
                "created_at",
            ],
        )

        serializer = InterviewSerializer(
            queryset,
            many=True,
            context={
                "request": request
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        """
        Create an interview.
        """

        serializer = InterviewSerializer(
            data=request.data,
            context={
                "request": request
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        with transaction.atomic():

            interview = serializer.save(
                created_by=request.user
            )

            application = interview.application

            if application.status in (
                "applied",
                "screening",
                "shortlisted",
                "assessment",
            ):

                services.change_status(
                    application,
                    "interview",
                    by=request.user,
                    note=(
                        f"Interview round "
                        f"{interview.round_number}"
                    ),
                )

            message = (
                f"{interview.get_round_type_display()} "
                f"on "
                f"{interview.scheduled_at:%d %b %Y %H:%M}"
            )

            services.notify(
                application.candidate,
                "Interview scheduled",
                message,
                "interview",
                f"/interviews/{interview.pk}",
            )

            if interview.interviewer:

                services.notify(
                    interview.interviewer,
                    "Interview assigned",
                    (
                        f"{application.candidate.full_name}: "
                        f"{message}"
                    ),
                    "interview",
                    f"/interviews/{interview.pk}",
                )

        return Response(
            InterviewSerializer(
                interview,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ================================================================
# INTERVIEW DETAIL
# ================================================================

class InterviewDetailView(APIView):
    """
    GET    /api/interviews/<id>/
    PUT    /api/interviews/<id>/
    PATCH  /api/interviews/<id>/
    DELETE /api/interviews/<id>/
    """

    def get_permissions(self):

        if self.request.method in (
            "PUT",
            "PATCH",
            "DELETE",
        ):
            return [IsHRStaff()]

        return [IsAuthenticated()]

    def get_queryset(self):

        return interviews_for(
            self.request.user
        )

    def get_object(self, pk):

        return get_object_or_404(
            self.get_queryset(),
            pk=pk,
        )

    def get(self, request, pk):

        interview = self.get_object(pk)

        serializer = InterviewSerializer(
            interview,
            context={
                "request": request
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):

        interview = self.get_object(pk)

        serializer = InterviewSerializer(
            interview,
            data=request.data,
            context={
                "request": request
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        interview = serializer.save()

        return Response(
            InterviewSerializer(
                interview,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):

        interview = self.get_object(pk)

        serializer = InterviewSerializer(
            interview,
            data=request.data,
            partial=True,
            context={
                "request": request
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        interview = serializer.save()

        return Response(
            InterviewSerializer(
                interview,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):

        interview = self.get_object(pk)

        interview.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


# ================================================================
# CONFIRM INTERVIEW
# ================================================================

class InterviewConfirmView(APIView):

    permission_classes = [
        IsCandidate
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        if interview.status not in (
            "scheduled",
            "rescheduled",
        ):
            raise ValidationError(
                "Only scheduled interviews can be confirmed."
            )

        interview.status = "confirmed"

        interview.save(
            update_fields=["status"]
        )

        services.notify(
            interview.interviewer or interview.created_by,
            "Interview confirmed",
            (
                f"{interview.application.candidate.full_name} "
                f"confirmed the interview."
            ),
            "interview",
        )

        return Response(
            InterviewSerializer(
                interview,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# RESCHEDULE INTERVIEW
# ================================================================

class InterviewRescheduleView(APIView):

    permission_classes = [
        IsHRStaff
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        if interview.status in (
            "completed",
            "cancelled",
            "in_progress",
        ):
            raise ValidationError(
                "This interview cannot be rescheduled."
            )

        serializer = RescheduleSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        interview.scheduled_at = (
            serializer.validated_data["scheduled_at"]
        )

        interview.meeting_link = (
            serializer.validated_data.get(
                "meeting_link",
                interview.meeting_link,
            )
        )

        interview.status = "rescheduled"

        interview.save()

        for user in (
            interview.application.candidate,
            interview.interviewer,
        ):

            if user:

                services.notify(
                    user,
                    "Interview rescheduled",
                    (
                        f"New time: "
                        f"{interview.scheduled_at:%d %b %Y %H:%M}"
                    ),
                    "interview",
                    f"/interviews/{interview.pk}",
                )

        return Response(
            InterviewSerializer(
                interview,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# CANCEL INTERVIEW
# ================================================================

class InterviewCancelView(APIView):

    permission_classes = [
        IsHRStaff
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        if interview.status in (
            "completed",
            "cancelled",
        ):
            raise ValidationError(
                "Interview already closed."
            )

        interview.status = "cancelled"

        interview.save(
            update_fields=["status"]
        )

        for user in (
            interview.application.candidate,
            interview.interviewer,
        ):

            if user:

                services.notify(
                    user,
                    "Interview cancelled",
                    (
                        interview.title
                        or interview.get_round_type_display()
                    ),
                    "interview",
                )

        return Response(
            InterviewSerializer(
                interview,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# START INTERVIEW
# ================================================================

class InterviewStartView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        if interview.status not in (
            "scheduled",
            "confirmed",
            "rescheduled",
        ):
            raise ValidationError(
                f"Cannot start an interview "
                f"that is {interview.status}."
            )

        interview.status = "in_progress"
        interview.started_at = timezone.now()

        interview.save(
            update_fields=[
                "status",
                "started_at",
            ]
        )

        first_question = None

        if interview.is_ai_conducted:

            first_question = _next_question(
                interview
            )

        data = InterviewSerializer(
            interview,
            context={
                "request": request
            },
        ).data

        if first_question:

            data["current_question"] = (
                InterviewQuestionSerializer(
                    first_question,
                    context={
                        "request": request
                    },
                ).data
            )

        return Response(
            data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# COMPLETE INTERVIEW
# ================================================================

class InterviewCompleteView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        if interview.status != "in_progress":
            raise ValidationError(
                "Only interviews in progress "
                "can be completed."
            )

        self.complete_interview(interview)

        return Response(
            InterviewSerializer(
                interview,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def complete_interview(interview):

        interview.status = "completed"
        interview.ended_at = timezone.now()

        interview.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        services.notify_company_staff(
            interview.application.job.company,
            [
                User.Role.HR,
                User.Role.COMPANY_ADMIN,
            ],
            "Interview completed",
            (
                f"{interview.application.candidate.full_name} - "
                f"{interview.get_round_type_display()}"
            ),
            "interview",
            f"/interviews/{interview.pk}",
        )

        services.recompute_scorecard(
            interview.application
        )


# ================================================================
# INTERVIEW QUESTIONS
# ================================================================

class InterviewQuestionsView(APIView):
    """
    GET  /api/interviews/<id>/questions/
    POST /api/interviews/<id>/questions/
    """

    permission_classes = [
        IsAuthenticated
    ]

    def get_interview(self, request, pk):

        return get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

    def get(self, request, pk):

        interview = self.get_interview(
            request,
            pk,
        )

        _require_ai_session(
            request.user,
            interview,
        )

        queryset = interview.questions.select_related(
            "answer"
        ).order_by("order")

        serializer = InterviewQuestionSerializer(
            queryset,
            many=True,
            context={
                "request": request
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request, pk):

        interview = self.get_interview(
            request,
            pk,
        )

        _require_ai_session(
            request.user,
            interview,
        )

        if request.user.role == CAND:
            raise PermissionDenied(
                "Candidates cannot create manual questions."
            )

        serializer = InterviewQuestionSerializer(
            data=request.data,
            context={
                "request": request
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        question = serializer.save(
            interview=interview,
            order=interview.questions.count() + 1,
            source="manual",
        )

        return Response(
            InterviewQuestionSerializer(
                question,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ================================================================
# GENERATE AI QUESTIONS
# ================================================================

class InterviewGenerateQuestionsView(APIView):

    permission_classes = [
        IsCompanyMember
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        serializer = GenerateQuestionsSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        job_context, candidate_context = _contexts(
            interview
        )

        existing = list(
            interview.questions.values_list(
                "text",
                flat=True
            )
        )

        if interview.difficulty == "adaptive":

            difficulty = serializer.validated_data[
                "difficulty"
            ]

        else:

            difficulty = interview.difficulty

        generated = ai.generate_questions(
            job_context,
            candidate_context,
            interview.round_type,
            difficulty,
            serializer.validated_data["count"],
            exclude=existing,
        )

        with transaction.atomic():

            base = interview.questions.count()

            created = []

            for index, question in enumerate(
                generated,
                start=1,
            ):

                created.append(
                    InterviewQuestion.objects.create(
                        interview=interview,
                        order=base + index,
                        text=question["text"],
                        topic=question.get(
                            "topic",
                            ""
                        ),
                        difficulty=question.get(
                            "difficulty",
                            difficulty,
                        ),
                        expected_points=question.get(
                            "expected_points",
                            []
                        ),
                        source="ai",
                    )
                )

            AIRunLog.objects.create(
                task="generate_questions",
                user=request.user,
                input_ref=f"interview:{interview.pk}",
                provider=(
                    "llm"
                    if ai.llm.llm_available()
                    else "heuristic"
                ),
                output={
                    "count": len(created)
                },
            )

        return Response(
            InterviewQuestionSerializer(
                created,
                many=True,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ================================================================
# NEXT QUESTION
# ================================================================

class InterviewNextQuestionView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        _require_ai_session(
            request.user,
            interview,
        )

        if interview.status != "in_progress":
            raise ValidationError(
                "The interview is not in progress."
            )

        question = _next_question(
            interview
        )

        if question is None:

            return Response(
                {
                    "finished": True,
                    "next_question": None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "finished": False,
                "next_question": (
                    InterviewQuestionSerializer(
                        question,
                        context={
                            "request": request
                        },
                    ).data
                ),
            },
            status=status.HTTP_200_OK,
        )


# ================================================================
# SUBMIT ANSWER
# ================================================================

class InterviewAnswerView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        _require_ai_session(
            request.user,
            interview,
        )

        if interview.status != "in_progress":
            raise ValidationError(
                "The interview is not in progress."
            )

        serializer = SubmitAnswerSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        validated_data = serializer.validated_data

        question = get_object_or_404(
            interview.questions,
            pk=validated_data["question_id"],
        )

        job_context, _ = _contexts(
            interview
        )

        result = ai.analyze_answer(
            question.text,
            validated_data["answer_text"],
            question.expected_points,
            job_context,
        )

        with transaction.atomic():

            answer, _ = (
                InterviewAnswer.objects.update_or_create(
                    question=question,
                    defaults={
                        "answer_text": (
                            validated_data["answer_text"]
                        ),
                        "duration_seconds": (
                            validated_data.get(
                                "duration_seconds"
                            )
                        ),
                        "technical_score": (
                            result["technical_score"]
                        ),
                        "communication_score": (
                            result["communication_score"]
                        ),
                        "problem_solving_score": (
                            result["problem_solving_score"]
                        ),
                        "relevance_score": (
                            result["relevance_score"]
                        ),
                        "confidence_score": (
                            result["confidence_score"]
                        ),
                        "overall_score": (
                            result["overall_score"]
                        ),
                        "analysis": {
                            key: result[key]
                            for key in (
                                "level",
                                "strengths",
                                "improvements",
                                "provider",
                                "disclaimer",
                            )
                        },
                    },
                )
            )

            AIRunLog.objects.create(
                task="analyze_answer",
                user=request.user,
                input_ref=f"question:{question.pk}",
                provider=result["provider"],
                output={
                    "overall": result["overall_score"]
                },
            )

        payload = {
            "saved": True
        }

        is_candidate = (
            request.user.role == CAND
        )

        if not is_candidate:

            question.refresh_from_db()

            payload["analysis"] = (
                InterviewQuestionSerializer(
                    question,
                    context={
                        "request": request
                    },
                ).data["answer"]
            )

        if (
            validated_data["request_next"]
            or interview.is_ai_conducted
        ):

            next_question = _next_question(
                interview
            )

            payload["finished"] = (
                next_question is None
            )

            payload["next_question"] = (
                InterviewQuestionSerializer(
                    next_question,
                    context={
                        "request": request
                    },
                ).data
                if next_question
                else None
            )

            if (
                next_question is None
                and interview.is_ai_conducted
            ):

                InterviewCompleteView.complete_interview(
                    interview
                )

        return Response(
            payload,
            status=status.HTTP_200_OK,
        )


# ================================================================
# AI SUMMARY
# ================================================================

class InterviewAISummaryView(APIView):

    permission_classes = [
        IsCompanyMember
    ]

    def get(self, request, pk):

        interview = get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

        answers = InterviewAnswer.objects.filter(
            question__interview=interview
        )

        aggregate = answers.aggregate(
            technical=Avg("technical_score"),
            communication=Avg("communication_score"),
            problem_solving=Avg("problem_solving_score"),
            relevance=Avg("relevance_score"),
            confidence=Avg("confidence_score"),
            overall=Avg("overall_score"),
            n=Count("id"),
        )

        strengths = []
        improvements = []

        for answer in answers:

            strengths.extend(
                answer.analysis.get(
                    "strengths",
                    []
                )
            )

            improvements.extend(
                answer.analysis.get(
                    "improvements",
                    []
                )
            )

        def round_score(value):

            return (
                round(value, 1)
                if value is not None
                else None
            )

        return Response(
            {
                "answered": aggregate["n"],
                "total_questions": interview.questions.count(),
                "scores": {
                    key: round_score(aggregate[key])
                    for key in (
                        "technical",
                        "communication",
                        "problem_solving",
                        "relevance",
                        "confidence",
                        "overall",
                    )
                },
                "strengths": list(
                    dict.fromkeys(strengths)
                )[:8],
                "areas_to_improve": list(
                    dict.fromkeys(improvements)
                )[:8],
                "disclaimer": (
                    "Automated scores are decision-support signals, "
                    "not final judgments."
                ),
            },
            status=status.HTTP_200_OK,
        )


# ================================================================
# INTERVIEW FEEDBACK
# ================================================================

class InterviewFeedbackView(APIView):
    """
    GET  /api/interviews/<id>/feedback/
    POST /api/interviews/<id>/feedback/
    """

    permission_classes = [
        IsCompanyMember
    ]

    def get_interview(self, request, pk):

        return get_object_or_404(
            interviews_for(request.user),
            pk=pk,
        )

    def get(self, request, pk):

        interview = self.get_interview(
            request,
            pk,
        )

        queryset = interview.feedbacks.select_related(
            "interviewer"
        )

        serializer = InterviewFeedbackSerializer(
            queryset,
            many=True,
            context={
                "request": request
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request, pk):

        interview = self.get_interview(
            request,
            pk,
        )

        serializer = InterviewFeedbackSerializer(
            data=request.data,
            context={
                "request": request
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        with transaction.atomic():

            feedback, created = (
                InterviewFeedback.objects.update_or_create(
                    interview=interview,
                    interviewer=request.user,
                    defaults=serializer.validated_data,
                )
            )

            services.notify_company_staff(
                interview.application.job.company,
                [
                    User.Role.HR,
                    User.Role.COMPANY_ADMIN,
                ],
                "Interview feedback submitted",
                (
                    f"{request.user.full_name} for "
                    f"{interview.application.candidate.full_name}"
                ),
                "interview",
                f"/interviews/{interview.pk}",
            )

            services.recompute_scorecard(
                interview.application
            )

            log_action(
                request,
                "interview.feedback",
                "Interview",
                interview.pk,
            )

        return Response(
            InterviewFeedbackSerializer(
                feedback,
                context={
                    "request": request
                },
            ).data,
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )


# ================================================================
# INTEGRITY EVENTS
# ================================================================

class IntegrityEventListCreateView(APIView):
    """
    GET  /api/integrity-events/
    POST /api/integrity-events/
    """

    def get_permissions(self):

        if self.request.method == "POST":
            return [IsAuthenticated()]

        return [IsCompanyMember()]

    def get_queryset(self):

        allowed_interviews = interviews_for(
            self.request.user
        )

        return (
            IntegrityEvent.objects
            .filter(
                interview__in=allowed_interviews
            )
            .select_related("interview")
        )

    def get(self, request):

        queryset = self.get_queryset()

        queryset = _filter_queryset(
            request,
            queryset,
            filter_fields=[
                "interview",
                "event_type",
                "severity",
                "review_status",
            ],
            ordering_fields=[
                "created_at",
                "offset_seconds",
            ],
        )

        serializer = IntegrityEventSerializer(
            queryset,
            many=True,
            context={
                "request": request
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):

        serializer = IntegrityEventSerializer(
            data=request.data,
            context={
                "request": request
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = request.user

        interview = serializer.validated_data[
            "interview"
        ]

        if not (
            interviews_for(user)
            .filter(pk=interview.pk)
            .exists()
        ):
            raise PermissionDenied(
                "You cannot log events for this interview."
            )

        event = serializer.save(
            source=(
                "candidate_client"
                if user.role == CAND
                else f"{user.role}"
            )
        )

        if event.severity == "high":

            services.notify_company_staff(
                interview.application.job.company,
                [User.Role.HR],
                "High-severity integrity event",
                (
                    f"{event.get_event_type_display()} "
                    f"at {event.offset_seconds}s - "
                    f"review needed"
                ),
                "integrity",
                f"/interviews/{interview.pk}",
            )

        return Response(
            IntegrityEventSerializer(
                event,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_201_CREATED,
        )


# ================================================================
# INTEGRITY EVENT DETAIL
# ================================================================

class IntegrityEventDetailView(APIView):
    """
    GET /api/integrity-events/<id>/
    """

    permission_classes = [
        IsCompanyMember
    ]

    def get_queryset(self):

        allowed_interviews = interviews_for(
            self.request.user
        )

        return (
            IntegrityEvent.objects
            .filter(
                interview__in=allowed_interviews
            )
            .select_related("interview")
        )

    def get(self, request, pk):

        event = get_object_or_404(
            self.get_queryset(),
            pk=pk,
        )

        serializer = IntegrityEventSerializer(
            event,
            context={
                "request": request
            },
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# REVIEW INTEGRITY EVENT
# ================================================================

class IntegrityEventReviewView(APIView):

    permission_classes = [
        IsCompanyMember
    ]

    def post(self, request, pk):

        event = get_object_or_404(
            IntegrityEvent.objects.filter(
                interview__in=interviews_for(request.user)
            ),
            pk=pk,
        )

        serializer = ReviewEventSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        event.review_status = (
            serializer.validated_data["review_status"]
        )

        event.review_note = (
            serializer.validated_data.get(
                "review_note",
                "",
            )
        )

        event.reviewed_by = request.user
        event.reviewed_at = timezone.now()

        event.save()

        log_action(
            request,
            "integrity.reviewed",
            "IntegrityEvent",
            event.pk,
            {
                "result": event.review_status
            },
        )

        return Response(
            IntegrityEventSerializer(
                event,
                context={
                    "request": request
                },
            ).data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# INTEGRITY SUMMARY
# ================================================================

class IntegrityEventSummaryView(APIView):

    permission_classes = [
        IsCompanyMember
    ]

    def get(self, request):

        interview_id = request.query_params.get(
            "interview"
        )

        if not interview_id:

            raise ValidationError(
                "interview query parameter is required."
            )

        try:
            interview_id = int(interview_id)

            if interview_id <= 0:
                raise ValueError

        except (TypeError, ValueError):

            raise ValidationError(
                "interview must be a valid positive integer."
            )

        queryset = (
            IntegrityEvent.objects
            .filter(
                interview__in=interviews_for(request.user)
            )
            .filter(
                interview_id=interview_id
            )
        )

        return Response(
            {
                "total": queryset.count(),

                "by_type": list(
                    queryset
                    .values("event_type")
                    .annotate(
                        count=Count("id")
                    )
                ),

                "by_severity": list(
                    queryset
                    .values("severity")
                    .annotate(
                        count=Count("id")
                    )
                ),

                "pending_review": queryset.filter(
                    review_status="pending"
                ).count(),

                "confirmed_concerns": queryset.filter(
                    review_status="concern"
                ).count(),

                "timeline": IntegrityEventSerializer(
                    queryset.order_by(
                        "offset_seconds"
                    ),
                    many=True,
                    context={
                        "request": request
                    },
                ).data,

                "note": (
                    "Events are signals for human review, "
                    "not proof of misconduct."
                ),
            },
            status=status.HTTP_200_OK,
        )


class WebRTCConfigView(APIView):
    """GET /api/webrtc/config/ -> ICE servers + WebSocket path for the video call."""

    permission_classes = [IsAuthenticated]

    def get(self, request, interview_id=None):
        from django.conf import settings as dj_settings

        path = "/ws/interviews/{id}/"
        return Response(
            {
                "iceServers": dj_settings.WEBRTC_ICE_SERVERS,
                "websocket_path": path,
                "websocket_url": path.format(id=interview_id) if interview_id else None,
            }
        )
