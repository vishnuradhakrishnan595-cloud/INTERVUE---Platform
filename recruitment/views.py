from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsCandidate, IsCompanyMember, IsHRStaff
from accounts.utils import log_action

from ai_engine.models import AIRunLog
from ai_engine.services import resume_parser

from . import code_runner, services
from .models import (
    Application,
    ApplicationStatusHistory,
    Assessment,
    AssessmentAttempt,
    CodingProblem,
    HiringDecision,
    Job,
    Notification,
    Offer,
    Resume,
    SavedJob,
    Submission,
)
from .serializers import (
    ApplicationSerializer,
    ApplicationStatusHistorySerializer,
    AssessmentSerializer,
    AssignAssessmentSerializer,
    AttemptSerializer,
    CandidateListSerializer,
    CandidateProblemSerializer,
    CodingProblemSerializer,
    CompareSerializer,
    HiringDecisionSerializer,
    JobSerializer,
    NotificationSerializer,
    OfferSerializer,
    ResumeSerializer,
    SavedJobSerializer,
    ScorecardSerializer,
    StatusChangeSerializer,
    SubmissionSerializer,
    SubmitCodeSerializer,
)


SA = User.Role.SUPER_ADMIN
CAND = User.Role.CANDIDATE


# ============================================================
# SHARED HELPERS
# ============================================================

def scope_company(queryset, user, lookup="company_id"):
    """
    Super administrators can access all records.
    Other company users are restricted to their company.
    """
    if user.role == SA:
        return queryset

    return queryset.filter(**{lookup: user.company_id})


def serialize(serializer_class, instance, request, many=False):
    return serializer_class(
        instance,
        many=many,
        context={"request": request},
    )


def apply_query_parameters(view, queryset):
    """
    Apply the filterset_fields, search_fields, and ordering_fields
    declared on a view.

    This replaces the automatic filter handling that generic views
    would normally provide.
    """
    params = view.request.query_params

    for field in getattr(view, "filterset_fields", []):
        value = params.get(field)

        if value is None or value == "":
            continue

        if field == "is_ai_conducted":
            normalized = value.lower()

            if normalized in ("true", "1", "yes"):
                value = True
            elif normalized in ("false", "0", "no"):
                value = False

        queryset = queryset.filter(**{field: value})

    search = params.get("search", "").strip()

    if search:
        condition = Q()

        for field in getattr(view, "search_fields", []):
            condition |= Q(**{f"{field}__icontains": search})

        if condition:
            queryset = queryset.filter(condition)

    ordering = params.get("ordering", "").strip()

    allowed_ordering = getattr(view, "ordering_fields", [])

    if ordering and allowed_ordering:
        requested_fields = []

        for field in ordering.split(","):
            field = field.strip()
            actual_field = field.lstrip("-")

            if actual_field in allowed_ordering:
                requested_fields.append(field)

        if requested_fields:
            queryset = queryset.order_by(*requested_fields)

    return queryset


def list_response(view, queryset, serializer_class):
    """
    Use configured page-number pagination when available.
    Otherwise return the complete serialized list.
    """
    paginator = PageNumberPagination()

    page = paginator.paginate_queryset(
        queryset,
        view.request,
        view=view,
    )

    if page is not None:
        data = serialize(
            serializer_class,
            page,
            view.request,
            many=True,
        ).data

        return paginator.get_paginated_response(data)

    data = serialize(
        serializer_class,
        queryset,
        view.request,
        many=True,
    ).data

    return Response(data)


# ============================================================
# CUSTOM APIView CRUD BASE CLASSES
# These are our own APIView subclasses, not DRF generics.
# ============================================================

class APIViewList(APIView):
    serializer_class = None

    def get_queryset(self):
        raise NotImplementedError(
            "Define get_queryset() in the view."
        )

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        queryset = apply_query_parameters(self, queryset)

        return list_response(
            self,
            queryset,
            self.serializer_class,
        )


class APIViewListCreate(APIViewList):
    def perform_create(self, serializer):
        serializer.save()

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )


class APIViewRetrieve(APIView):
    serializer_class = None

    def get_queryset(self):
        raise NotImplementedError(
            "Define get_queryset() in the view."
        )

    def get_object(self):
        return get_object_or_404(
            self.get_queryset(),
            pk=self.kwargs["pk"],
        )

    def get(self, request, *args, **kwargs):
        instance = self.get_object()

        return Response(
            serialize(
                self.serializer_class,
                instance,
                request,
            ).data
        )


class APIViewUpdate(APIViewRetrieve):
    def perform_update(self, serializer):
        serializer.save()

    def put(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    def patch(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        instance = self.get_object()

        serializer = self.serializer_class(
            instance,
            data=request.data,
            partial=partial,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)


class APIViewRetrieveUpdate(APIViewUpdate):
    pass


class APIViewRetrieveUpdateDestroy(APIViewUpdate):
    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class APIViewRetrieveDestroy(APIViewRetrieve):
    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


# ============================================================
# JOBS
# ============================================================

class JobListCreateView(APIViewListCreate):
    """
    GET  /api/jobs/
    POST /api/jobs/
    """

    serializer_class = JobSerializer

    search_fields = [
        "title",
        "department",
        "location",
        "description",
    ]

    filterset_fields = [
        "status",
        "employment_type",
        "department",
        "location",
        "company",
    ]

    ordering_fields = [
        "created_at",
        "deadline",
        "title",
    ]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]

        return [IsHRStaff()]

    def get_queryset(self):
        user = self.request.user

        queryset = (
            Job.objects
            .select_related("company")
            .prefetch_related("stages")
        )

        if user.role == CAND:
            return queryset.filter(
                status=Job.Status.OPEN
            ).filter(
                Q(deadline__isnull=True)
                | Q(deadline__gte=timezone.localdate())
            )

        return scope_company(queryset, user)

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user

        if user.company_id is None:
            raise ValidationError(
                "Your account is not linked to a company."
            )

        job = serializer.save(
            company=user.company,
            created_by=user,
        )

        log_action(
            self.request,
            "job.created",
            "Job",
            job.pk,
        )


class JobDetailView(APIViewRetrieveUpdateDestroy):
    """
    GET, PUT, PATCH, DELETE /api/jobs/<id>/
    """

    serializer_class = JobSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]

        return [IsHRStaff()]

    def get_queryset(self):
        user = self.request.user

        queryset = (
            Job.objects
            .select_related("company")
            .prefetch_related("stages")
        )

        if user.role == CAND:
            return queryset.filter(
                status=Job.Status.OPEN
            ).filter(
                Q(deadline__isnull=True)
                | Q(deadline__gte=timezone.localdate())
            )

        return scope_company(queryset, user)


class JobPublishView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, pk):
        job = get_object_or_404(
            scope_company(Job.objects.all(), request.user),
            pk=pk,
        )

        job.status = Job.Status.OPEN
        job.save(update_fields=["status", "updated_at"])

        return Response(
            serialize(JobSerializer, job, request).data
        )


class JobCloseView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, pk):
        job = get_object_or_404(
            scope_company(Job.objects.all(), request.user),
            pk=pk,
        )

        job.status = Job.Status.CLOSED
        job.save(update_fields=["status", "updated_at"])

        return Response(
            serialize(JobSerializer, job, request).data
        )


class JobApplicationsView(APIViewList):
    permission_classes = [IsCompanyMember]
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        job = get_object_or_404(
            scope_company(Job.objects.all(), self.request.user),
            pk=self.kwargs["pk"],
        )

        return (
            job.applications
            .select_related(
                "candidate",
                "job",
                "job__company",
            )
            .order_by("-overall_match")
        )


# ============================================================
# RESUMES
# ============================================================

class ResumeListCreateView(APIViewListCreate):
    permission_classes = [IsCandidate]
    serializer_class = ResumeSerializer

    def get_queryset(self):
        return Resume.objects.filter(
            candidate=self.request.user
        )

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user

        uploaded_file = self.request.FILES.get("file")

        if not uploaded_file:
            raise ValidationError("Resume file is required.")

        resume = serializer.save(
            candidate=user,
            original_name=uploaded_file.name,
        )

        with resume.file.open("rb") as file_handle:
            text = resume_parser.extract_text(
                file_handle,
                resume.original_name,
            )

        parsed = resume_parser.parse_resume_text(text)

        resume.extracted_text = text
        resume.parsed_data = parsed
        resume.skills = parsed["skills"]

        should_be_primary = (
            resume.is_primary
            or not Resume.objects.filter(
                candidate=user,
                is_primary=True,
            ).exclude(pk=resume.pk).exists()
        )

        if should_be_primary:
            Resume.objects.filter(
                candidate=user
            ).exclude(
                pk=resume.pk
            ).update(is_primary=False)

            resume.is_primary = True

        resume.save()

        AIRunLog.objects.create(
            task="resume_parse",
            user=user,
            provider=parsed["parser"],
            input_ref=f"resume:{resume.pk}",
            output={"skills": parsed["skills"]},
        )


class ResumeDetailView(APIViewRetrieveDestroy):
    permission_classes = [IsCandidate]
    serializer_class = ResumeSerializer

    def get_queryset(self):
        return Resume.objects.filter(
            candidate=self.request.user
        )


class ResumeMakePrimaryView(APIView):
    permission_classes = [IsCandidate]

    @transaction.atomic
    def post(self, request, pk):
        resume = get_object_or_404(
            Resume.objects.filter(candidate=request.user),
            pk=pk,
        )

        Resume.objects.filter(
            candidate=request.user
        ).update(is_primary=False)

        resume.is_primary = True
        resume.save(update_fields=["is_primary"])

        return Response(
            serialize(ResumeSerializer, resume, request).data
        )


# ============================================================
# SAVED JOBS
# ============================================================

class SavedJobListCreateView(APIViewListCreate):
    permission_classes = [IsAuthenticated]
    serializer_class = SavedJobSerializer

    def get_queryset(self):
        return (
            SavedJob.objects
            .filter(candidate=self.request.user)
            .select_related("job", "job__company")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(candidate=self.request.user)


class SavedJobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        saved_job = get_object_or_404(
            SavedJob.objects.filter(candidate=request.user),
            pk=pk,
        )

        saved_job.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


# ============================================================
# APPLICATIONS
# ============================================================

class ApplicationListCreateView(APIViewListCreate):
    serializer_class = ApplicationSerializer

    search_fields = [
        "candidate__first_name",
        "candidate__last_name",
        "candidate__email",
        "job__title",
    ]

    filterset_fields = [
        "status",
        "job",
    ]

    ordering_fields = [
        "overall_match",
        "applied_at",
        "skill_match",
    ]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsCandidate()]

        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user

        queryset = Application.objects.select_related(
            "job",
            "job__company",
            "candidate",
            "resume",
        )

        if user.role == CAND:
            return queryset.filter(candidate=user)

        if user.role == User.Role.INTERVIEWER:
            return queryset.filter(
                interviews__interviewer=user
            ).distinct()

        return scope_company(
            queryset,
            user,
            "job__company_id",
        )

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user

        resume = (
            serializer.validated_data.get("resume")
            or Resume.objects.filter(
                candidate=user,
                is_primary=True,
            ).first()
        )

        app = serializer.save(
            candidate=user,
            resume=resume,
        )

        ApplicationStatusHistory.objects.create(
            application=app,
            to_status=app.status,
            changed_by=user,
            note="Applied",
        )

        services.screen_application(app)

        services.notify(
            user,
            "Application submitted",
            f"You applied for {app.job.title}.",
            "application",
        )

        services.notify(
            app.job.created_by,
            "New application",
            (
                f"{user.full_name} applied for {app.job.title} "
                f"(match {app.overall_match}%)."
            ),
            "application",
        )


class ApplicationDetailView(APIViewRetrieve):
    permission_classes = [IsAuthenticated]
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        user = self.request.user

        queryset = Application.objects.select_related(
            "job",
            "job__company",
            "candidate",
            "resume",
        )

        if user.role == CAND:
            return queryset.filter(candidate=user)

        if user.role == User.Role.INTERVIEWER:
            return queryset.filter(
                interviews__interviewer=user
            ).distinct()

        return scope_company(
            queryset,
            user,
            "job__company_id",
        )


class ApplicationWithdrawView(APIView):
    permission_classes = [IsCandidate]

    def post(self, request, pk):
        app = get_object_or_404(
            Application.objects.filter(candidate=request.user),
            pk=pk,
        )

        if app.status in ("hired", "rejected", "withdrawn"):
            raise ValidationError(
                "This application can no longer be withdrawn."
            )

        app = services.change_status(
            app,
            "withdrawn",
            by=request.user,
            note="Withdrawn by candidate",
        )

        return Response(
            serialize(ApplicationSerializer, app, request).data
        )


class ApplicationScreenView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, pk):
        app = get_object_or_404(
            scope_company(
                Application.objects.all(),
                request.user,
                "job__company_id",
            ),
            pk=pk,
        )

        app = services.screen_application(app, by=request.user)

        return Response(
            serialize(ApplicationSerializer, app, request).data
        )


class ApplicationShortlistView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, pk):
        app = get_object_or_404(
            scope_company(
                Application.objects.all(),
                request.user,
                "job__company_id",
            ),
            pk=pk,
        )

        app = services.change_status(
            app,
            "shortlisted",
            by=request.user,
            note="Shortlisted by HR",
        )

        return Response(
            serialize(ApplicationSerializer, app, request).data
        )


class ApplicationSetStatusView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, pk):
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = get_object_or_404(
            scope_company(
                Application.objects.all(),
                request.user,
                "job__company_id",
            ),
            pk=pk,
        )

        app = services.change_status(
            app,
            serializer.validated_data["status"],
            by=request.user,
            note=serializer.validated_data.get("note", ""),
        )

        log_action(
            request,
            "application.status",
            "Application",
            app.pk,
            {"status": app.status},
        )

        return Response(
            serialize(ApplicationSerializer, app, request).data
        )


class ApplicationResumeView(APIView):
    permission_classes = [IsCompanyMember]

    def get(self, request, pk):
        app = get_object_or_404(
            scope_company(
                Application.objects.all(),
                request.user,
                "job__company_id",
            ),
            pk=pk,
        )

        resume = app.resume

        if resume is None:
            return Response(
                {"detail": "No resume attached."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "id": resume.id,
            "file": request.build_absolute_uri(resume.file.url),
            "original_name": resume.original_name,
            "skills": resume.skills,
            "parsed_data": resume.parsed_data,
        })


class ApplicationHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = request.user

        queryset = Application.objects.select_related(
            "job",
            "candidate",
        )

        if user.role == CAND:
            queryset = queryset.filter(candidate=user)
        elif user.role == User.Role.INTERVIEWER:
            queryset = queryset.filter(
                interviews__interviewer=user
            ).distinct()
        else:
            queryset = scope_company(
                queryset,
                user,
                "job__company_id",
            )

        app = get_object_or_404(queryset, pk=pk)

        data = ApplicationStatusHistorySerializer(
            app.history.select_related("changed_by"),
            many=True,
            context={"request": request},
        ).data

        return Response(data)


class ApplicationScorecardView(APIView):
    permission_classes = [IsCompanyMember]

    def get_application(self, request, pk):
        return get_object_or_404(
            scope_company(
                Application.objects.all(),
                request.user,
                "job__company_id",
            ),
            pk=pk,
        )

    def get(self, request, pk):
        app = self.get_application(request, pk)
        card = services.recompute_scorecard(app)

        return Response(
            serialize(ScorecardSerializer, card, request).data
        )

    def patch(self, request, pk):
        if request.user.role == User.Role.INTERVIEWER:
            raise PermissionDenied(
                "Only HR can edit the scorecard."
            )

        app = self.get_application(request, pk)
        card = services.recompute_scorecard(app)

        serializer = ScorecardSerializer(
            card,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)


class ApplicationCompareView(APIView):
    permission_classes = [IsCompanyMember]

    def post(self, request):
        serializer = CompareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        apps = list(
            scope_company(
                Application.objects.select_related(
                    "candidate",
                    "job",
                ),
                request.user,
                "job__company_id",
            ).filter(
                pk__in=serializer.validated_data["application_ids"]
            )
        )

        if len(apps) < 2:
            raise ValidationError(
                "Provide at least two accessible applications."
            )

        rows = []

        for app in apps:
            card = services.recompute_scorecard(app)

            rows.append({
                "application_id": app.id,
                "candidate": app.candidate.full_name,
                "job": app.job.title,
                "status": app.status,
                "resume": card.resume_score,
                "coding": card.coding_score,
                "interview": card.interview_score,
                "communication": card.communication_score,
                "problem_solving": card.problem_solving_score,
                "overall": card.overall_score,
                "suggested_recommendation": (
                    card.suggested_recommendation
                ),
            })

        rows.sort(
            key=lambda row: row["overall"],
            reverse=True,
        )

        return Response({
            "best_overall": rows[0]["application_id"],
            "candidates": rows,
        })


# ============================================================
# CANDIDATES
# ============================================================

class CandidateListView(APIViewList):
    permission_classes = [IsCompanyMember]
    serializer_class = CandidateListSerializer

    search_fields = [
        "email",
        "first_name",
        "last_name",
    ]

    def get_queryset(self):
        user = self.request.user

        queryset = User.objects.filter(role=CAND)

        if user.role != SA:
            queryset = queryset.filter(
                applications__job__company_id=user.company_id
            )

        return queryset.distinct()


class CandidateDetailView(APIViewRetrieve):
    permission_classes = [IsCompanyMember]
    serializer_class = CandidateListSerializer

    def get_queryset(self):
        user = self.request.user

        queryset = User.objects.filter(role=CAND)

        if user.role != SA:
            queryset = queryset.filter(
                applications__job__company_id=user.company_id
            )

        return queryset.distinct()


# ============================================================
# CODING PROBLEMS
# ============================================================

class CodingProblemListCreateView(APIViewListCreate):
    permission_classes = [IsHRStaff]
    serializer_class = CodingProblemSerializer

    search_fields = ["title", "description"]
    filterset_fields = ["difficulty"]

    def get_queryset(self):
        return scope_company(
            CodingProblem.objects.prefetch_related("test_cases"),
            self.request.user,
        )

    def perform_create(self, serializer):
        serializer.save(
            company=self.request.user.company,
            created_by=self.request.user,
        )


class CodingProblemDetailView(APIViewRetrieveUpdateDestroy):
    permission_classes = [IsHRStaff]
    serializer_class = CodingProblemSerializer

    def get_queryset(self):
        return scope_company(
            CodingProblem.objects.prefetch_related("test_cases"),
            self.request.user,
        )


# ============================================================
# ASSESSMENTS
# ============================================================

class AssessmentListCreateView(APIViewListCreate):
    permission_classes = [IsHRStaff]
    serializer_class = AssessmentSerializer

    filterset_fields = ["job", "is_active"]
    search_fields = ["title"]

    def get_queryset(self):
        return scope_company(
            Assessment.objects.prefetch_related("problems"),
            self.request.user,
        )

    def perform_create(self, serializer):
        serializer.save(
            company=self.request.user.company,
            created_by=self.request.user,
        )


class AssessmentDetailView(APIViewRetrieveUpdateDestroy):
    permission_classes = [IsHRStaff]
    serializer_class = AssessmentSerializer

    def get_queryset(self):
        return scope_company(
            Assessment.objects.prefetch_related("problems"),
            self.request.user,
        )


class AssessmentAssignView(APIView):
    permission_classes = [IsHRStaff]

    @transaction.atomic
    def post(self, request, pk):
        assessment = get_object_or_404(
            scope_company(
                Assessment.objects.all(),
                request.user,
            ),
            pk=pk,
        )

        serializer = AssignAssessmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        apps = scope_company(
            Application.objects.select_related(
                "candidate",
                "job",
            ),
            request.user,
            "job__company_id",
        ).filter(
            pk__in=serializer.validated_data["application_ids"]
        )

        created = []

        for app in apps:
            attempt, was_new = AssessmentAttempt.objects.get_or_create(
                assessment=assessment,
                application=app,
            )

            if was_new:
                created.append(attempt.pk)

                services.change_status(
                    app,
                    "assessment",
                    by=request.user,
                    note=f"Assigned: {assessment.title}",
                )

                services.notify(
                    app.candidate,
                    "Coding assessment assigned",
                    (
                        f"{assessment.title} "
                        f"({assessment.duration_minutes} min)"
                    ),
                    "assessment",
                    f"/assessments/{attempt.pk}",
                )

        return Response(
            {
                "assigned": len(created),
                "attempt_ids": created,
            },
            status=status.HTTP_201_CREATED,
        )


# ============================================================
# ASSESSMENT ATTEMPTS
# ============================================================

class AttemptListView(APIViewList):
    permission_classes = [IsAuthenticated]
    serializer_class = AttemptSerializer

    filterset_fields = [
        "status",
        "assessment",
        "application",
    ]

    def get_queryset(self):
        user = self.request.user

        queryset = AssessmentAttempt.objects.select_related(
            "assessment",
            "application__candidate",
            "application__job",
        )

        if user.role == CAND:
            return queryset.filter(
                application__candidate=user
            )

        return scope_company(
            queryset,
            user,
            "assessment__company_id",
        )


class AttemptDetailView(APIViewRetrieve):
    permission_classes = [IsAuthenticated]
    serializer_class = AttemptSerializer

    def get_queryset(self):
        user = self.request.user

        queryset = AssessmentAttempt.objects.select_related(
            "assessment",
            "application__candidate",
            "application__job",
        )

        if user.role == CAND:
            return queryset.filter(
                application__candidate=user
            )

        return scope_company(
            queryset,
            user,
            "assessment__company_id",
        )


class AttemptStartView(APIView):
    permission_classes = [IsCandidate]

    def post(self, request, pk):
        attempt = get_object_or_404(
            AssessmentAttempt.objects.filter(
                application__candidate=request.user
            ),
            pk=pk,
        )

        if attempt.status == "submitted":
            raise ValidationError("Already submitted.")

        if attempt.started_at is None:
            attempt.started_at = timezone.now()
            attempt.status = "in_progress"
            attempt.save(update_fields=["started_at", "status"])

        return Response(
            serialize(AttemptSerializer, attempt, request).data
        )


class AttemptProblemsView(APIView):
    permission_classes = [IsCandidate]

    def get(self, request, pk):
        attempt = get_object_or_404(
            AssessmentAttempt.objects.filter(
                application__candidate=request.user
            ),
            pk=pk,
        )

        if attempt.started_at is None:
            raise ValidationError(
                "Start the assessment first."
            )

        return Response(
            serialize(
                CandidateProblemSerializer,
                attempt.assessment.problems.prefetch_related("test_cases"),
                request,
                many=True,
            ).data
        )


class AttemptSubmitCodeView(APIView):
    permission_classes = [IsCandidate]

    def get_attempt(self, request, pk):
        return get_object_or_404(
            AssessmentAttempt.objects.filter(
                application__candidate=request.user
            ),
            pk=pk,
        )

    def check_active(self, attempt):
        if attempt.status == "submitted":
            raise ValidationError(
                "This assessment has already been submitted."
            )

        if attempt.started_at:
            deadline = attempt.started_at + timedelta(
                minutes=attempt.assessment.duration_minutes
            )

            if timezone.now() > deadline + timedelta(minutes=1):
                AttemptFinishView.finalize(attempt, expired=True)

                raise ValidationError(
                    "Time is up; the assessment was closed."
                )

    def post(self, request, pk):
        attempt = self.get_attempt(request, pk)

        if attempt.started_at is None:
            raise ValidationError(
                "Start the assessment first."
            )

        self.check_active(attempt)

        serializer = SubmitCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        problem = serializer.validated_data["problem"]
        language = serializer.validated_data["language"]
        code = serializer.validated_data["code"]

        if not attempt.assessment.problems.filter(
            pk=problem.pk
        ).exists():
            raise ValidationError(
                "This problem is not part of the assessment."
            )

        if language not in attempt.assessment.languages:
            raise ValidationError(
                f"Language not allowed. "
                f"Allowed: {attempt.assessment.languages}"
            )

        result = code_runner.run_against_tests(
            language,
            code,
            problem,
        )

        submission = Submission.objects.create(
            attempt=attempt,
            problem=problem,
            language=language,
            code=code,
            verdict=result["verdict"],
            passed_cases=result["passed_cases"],
            total_cases=result["total_cases"],
            score=result["score"],
            results=result["results"],
        )

        return Response(
            serialize(SubmissionSerializer, submission, request).data,
            status=status.HTTP_201_CREATED,
        )


class AttemptFinishView(APIView):
    permission_classes = [IsCandidate]

    @staticmethod
    @transaction.atomic
    def finalize(attempt, expired=False):
        problems = list(attempt.assessment.problems.all())

        best = {problem.id: 0.0 for problem in problems}

        for submission in attempt.submissions.all():
            best[submission.problem_id] = max(
                best.get(submission.problem_id, 0),
                submission.score,
            )

        attempt.score = (
            round(sum(best.values()) / len(best), 1)
            if best
            else 0.0
        )

        attempt.passed = (
            attempt.score >= attempt.assessment.passing_score
        )

        attempt.status = (
            "expired"
            if expired and not attempt.submissions.exists()
            else "submitted"
        )

        attempt.submitted_at = timezone.now()
        attempt.save()

        app = attempt.application

        services.notify_company_staff(
            app.job.company,
            [User.Role.HR, User.Role.COMPANY_ADMIN],
            "Assessment completed",
            (
                f"{app.candidate.full_name}: {attempt.score}% "
                f"on {attempt.assessment.title}"
            ),
            "assessment",
            f"/applications/{app.pk}",
        )

        services.recompute_scorecard(app)

    def post(self, request, pk):
        attempt = get_object_or_404(
            AssessmentAttempt.objects.filter(
                application__candidate=request.user
            ),
            pk=pk,
        )

        if attempt.status == "submitted":
            raise ValidationError("Already submitted.")

        self.finalize(attempt)

        return Response(
            serialize(AttemptSerializer, attempt, request).data
        )


class AttemptSubmissionsView(APIViewList):
    permission_classes = [IsCompanyMember]
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        attempt = get_object_or_404(
            scope_company(
                AssessmentAttempt.objects.all(),
                self.request.user,
                "assessment__company_id",
            ),
            pk=self.kwargs["pk"],
        )

        return attempt.submissions.select_related("problem")


# ============================================================
# HIRING DECISIONS
# ============================================================

class HiringDecisionListCreateView(APIViewListCreate):
    permission_classes = [IsHRStaff]
    serializer_class = HiringDecisionSerializer

    filterset_fields = ["decision", "application"]

    def get_queryset(self):
        return scope_company(
            HiringDecision.objects.select_related(
                "application__job"
            ),
            self.request.user,
            "application__job__company_id",
        )

    def apply_decision(self, decision):
        app = decision.application

        target = {
            "selected": "selected",
            "rejected": "rejected",
            "hold": "final_review",
        }[decision.decision]

        services.change_status(
            app,
            target,
            by=self.request.user,
            note=decision.reason[:300],
        )

        log_action(
            self.request,
            "hiring.decision",
            "Application",
            app.pk,
            {"decision": decision.decision},
        )

    def perform_create(self, serializer):
        app = serializer.validated_data["application"]

        if (
            self.request.user.role != SA
            and app.job.company_id != self.request.user.company_id
        ):
            raise PermissionDenied(
                "Application belongs to another company."
            )

        decision = serializer.save(decided_by=self.request.user)
        self.apply_decision(decision)


class HiringDecisionDetailView(APIViewRetrieveUpdate):
    permission_classes = [IsHRStaff]
    serializer_class = HiringDecisionSerializer

    def get_queryset(self):
        return scope_company(
            HiringDecision.objects.select_related(
                "application__job"
            ),
            self.request.user,
            "application__job__company_id",
        )

    def perform_update(self, serializer):
        decision = serializer.save(decided_by=self.request.user)
        app = decision.application

        target = {
            "selected": "selected",
            "rejected": "rejected",
            "hold": "final_review",
        }[decision.decision]

        services.change_status(
            app,
            target,
            by=self.request.user,
            note=decision.reason[:300],
        )

        log_action(
            self.request,
            "hiring.decision",
            "Application",
            app.pk,
            {"decision": decision.decision},
        )


# ============================================================
# OFFERS
# ============================================================

class OfferListCreateView(APIViewListCreate):
    serializer_class = OfferSerializer
    filterset_fields = ["status", "application"]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]

        return [IsHRStaff()]

    def get_queryset(self):
        user = self.request.user

        queryset = Offer.objects.select_related(
            "application__candidate",
            "application__job__company",
        )

        if user.role == CAND:
            return queryset.filter(
                application__candidate=user
            ).exclude(status="draft")

        return scope_company(
            queryset,
            user,
            "application__job__company_id",
        )

    def perform_create(self, serializer):
        app = serializer.validated_data["application"]

        if (
            self.request.user.role != SA
            and app.job.company_id != self.request.user.company_id
        ):
            raise PermissionDenied(
                "Application belongs to another company."
            )

        if app.status != "selected":
            raise ValidationError(
                "Offers can only be created for selected candidates."
            )

        serializer.save(created_by=self.request.user)


class OfferDetailView(APIViewRetrieveUpdate):
    serializer_class = OfferSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]

        return [IsHRStaff()]

    def get_queryset(self):
        user = self.request.user

        queryset = Offer.objects.select_related(
            "application__candidate",
            "application__job__company",
        )

        if user.role == CAND:
            return queryset.filter(
                application__candidate=user
            ).exclude(status="draft")

        return scope_company(
            queryset,
            user,
            "application__job__company_id",
        )

    def perform_update(self, serializer):
        if serializer.instance.status != "draft":
            raise ValidationError(
                "Only draft offers can be edited."
            )

        serializer.save()


class OfferSendView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, pk):
        offer = get_object_or_404(
            scope_company(
                Offer.objects.select_related(
                    "application__candidate",
                    "application__job__company",
                ),
                request.user,
                "application__job__company_id",
            ),
            pk=pk,
        )

        if offer.status != "draft":
            raise ValidationError("Offer was already sent.")

        offer.status = "sent"
        offer.sent_at = timezone.now()
        offer.save(update_fields=["status", "sent_at"])

        services.notify(
            offer.application.candidate,
            "You have received an offer",
            (
                f"{offer.position} at "
                f"{offer.application.job.company.name}"
            ),
            "offer",
            f"/offers/{offer.pk}",
        )

        return Response(
            serialize(OfferSerializer, offer, request).data
        )


class OfferWithdrawView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, pk):
        offer = get_object_or_404(
            scope_company(
                Offer.objects.all(),
                request.user,
                "application__job__company_id",
            ),
            pk=pk,
        )

        if offer.status in ("accepted", "rejected"):
            raise ValidationError("Offer already answered.")

        offer.status = "withdrawn"
        offer.save(update_fields=["status"])

        return Response(
            serialize(OfferSerializer, offer, request).data
        )


class OfferRespondView(APIView):
    permission_classes = [IsCandidate]

    def post(self, request, pk):
        offer = get_object_or_404(
            Offer.objects.filter(
                application__candidate=request.user
            ),
            pk=pk,
        )

        if offer.status != "sent":
            raise ValidationError(
                "This offer is not awaiting a response."
            )

        if offer.expiry_date < timezone.localdate():
            offer.status = "expired"
            offer.save(update_fields=["status"])

            raise ValidationError("This offer has expired.")

        accept_value = request.data.get("accept")

        if not isinstance(accept_value, bool):
            raise ValidationError({
                "accept": "Provide true or false."
            })

        offer.status = "accepted" if accept_value else "rejected"
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "responded_at"])

        app = offer.application

        if accept_value:
            services.change_status(
                app,
                "hired",
                by=request.user,
                note="Offer accepted",
            )

        services.notify(
            app.job.created_by,
            f"Offer {offer.status}",
            (
                f"{app.candidate.full_name} {offer.status} "
                f"the offer for {offer.position}."
            ),
            "offer",
        )

        return Response(
            serialize(OfferSerializer, offer, request).data
        )


# ============================================================
# NOTIFICATIONS
# ============================================================

class NotificationListView(APIViewList):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    filterset_fields = ["is_read", "type"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationDetailView(APIViewRetrieve):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(
            Notification.objects.filter(user=request.user),
            pk=pk,
        )

        notification.is_read = True
        notification.save(update_fields=["is_read"])

        return Response(
            serialize(NotificationSerializer, notification, request).data
        )


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).update(is_read=True)

        return Response({"updated": updated})


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unread = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()

        return Response({"unread": unread})


# ============================================================
# DASHBOARD / ANALYTICS
# ============================================================

FUNNEL = [
    "applied",
    "screening",
    "shortlisted",
    "assessment",
    "interview",
    "final_review",
    "selected",
    "hired",
]


class DashboardView(APIView):
    permission_classes = [IsHRStaff]

    def get(self, request):
        user = request.user

        jobs = scope_company(Job.objects.all(), user)

        apps = scope_company(
            Application.objects.all(),
            user,
            "job__company_id",
        )

        job_id = request.query_params.get("job")

        if job_id:
            jobs = jobs.filter(pk=job_id)
            apps = apps.filter(job_id=job_id)

        counts = dict(
            apps.values("status")
            .annotate(n=Count("id"))
            .values_list("status", "n")
        )

        hist = ApplicationStatusHistory.objects.filter(
            application__in=apps
        )

        funnel = []

        for stage in FUNNEL:
            count = (
                hist.filter(to_status=stage)
                .order_by()
                .values("application")
                .distinct()
                .count()
            )

            funnel.append({
                "stage": stage,
                "count": count,
            })

        hired = hist.filter(
            to_status="hired"
        ).select_related("application")

        days = [
            (
                history.created_at
                - history.application.applied_at
            ).total_seconds() / 86400
            for history in hired
        ]

        from interviews.models import Interview, InterviewFeedback

        interviews = scope_company(
            Interview.objects.all(),
            user,
            "application__job__company_id",
        )

        feedback = InterviewFeedback.objects.filter(
            interview__in=interviews
        )

        feedback_total = feedback.count()

        feedback_pass = feedback.filter(
            recommendation__in=["hire", "strong_hire"]
        ).count()

        attempts = AssessmentAttempt.objects.filter(
            application__in=apps,
            status="submitted",
        )

        by_job = (
            jobs.annotate(
                applications_n=Count("applications"),
                hired_n=Count(
                    "applications",
                    filter=Q(applications__status="hired"),
                ),
                avg_match=Avg("applications__overall_match"),
            )
            .values(
                "id",
                "title",
                "status",
                "applications_n",
                "hired_n",
                "avg_match",
            )
        )

        by_department = (
            jobs.values("department")
            .annotate(
                hired=Count(
                    "applications",
                    filter=Q(applications__status="hired"),
                ),
                applications=Count("applications"),
            )
            .order_by("-applications")
        )

        total = apps.count()

        interview_count = (
            interviews.order_by()
            .values("application")
            .distinct()
            .count()
        )

        return Response({
            "totals": {
                "jobs": jobs.count(),
                "active_jobs": jobs.filter(status="open").count(),
                "applications": total,
                "shortlisted": counts.get("shortlisted", 0),
                "interviews": interviews.count(),
                "selected": (
                    counts.get("selected", 0)
                    + counts.get("hired", 0)
                ),
                "rejected": counts.get("rejected", 0),
                "hired": counts.get("hired", 0),
            },
            "status_breakdown": counts,
            "hiring_funnel": funnel,
            "avg_time_to_hire_days": (
                round(sum(days) / len(days), 1)
                if days else None
            ),
            "application_to_interview_ratio": (
                round(interview_count / total, 3)
                if total else 0
            ),
            "interview_pass_rate": (
                round(feedback_pass / feedback_total, 3)
                if feedback_total else None
            ),
            "coding_assessment": {
                "attempts": attempts.count(),
                "avg_score": attempts.aggregate(
                    a=Avg("score")
                )["a"],
                "pass_rate": (
                    round(
                        attempts.filter(passed=True).count()
                        / attempts.count(),
                        3,
                    )
                    if attempts.exists() else None
                ),
            },
            "ai_screening": {
                "avg_match_score": apps.aggregate(
                    a=Avg("overall_match")
                )["a"],
                "high_match_count": apps.filter(
                    overall_match__gte=80
                ).count(),
            },
            "job_wise": list(by_job),
            "department_wise": list(by_department),
            "candidate_source": list(
                apps.values("source").annotate(n=Count("id"))
            ),
        })