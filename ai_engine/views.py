
"""
Stateless AI endpoints (utilities / previews).

Persisted AI results are produced by the recruitment
(screening) and interviews (questions, answers) apps
through the same services.
"""

from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend

from accounts.models import User
from accounts.permissions import IsCompanyMember, IsHRStaff

from recruitment.models import Job, Resume
from recruitment.services import build_job_context

from .models import AIRunLog

from .serializers import (
    AIRunLogSerializer,
    AnalyzeAnswerSerializer,
    MatchSerializer,
    ParseResumeSerializer,
    QuestionGenSerializer,
)

from .services import interview as interview_ai
from .services import llm, matcher, resume_parser


# ================================================================
# HELPER FUNCTIONS
# ================================================================

def _job_for(user, job_id):
    """
    Return a job only if the current user has access to it.
    """

    queryset = Job.objects.all()

    # Candidates can only access open jobs.
    if user.role == User.Role.CANDIDATE:

        queryset = queryset.filter(
            status="open"
        )

    # Company users can only access their own company's jobs.
    elif user.role != User.Role.SUPER_ADMIN:

        queryset = queryset.filter(
            company_id=user.company_id
        )

    return get_object_or_404(
        queryset,
        pk=job_id
    )


def _provider():
    """
    Return the currently available AI provider.
    """

    return (
        "llm"
        if llm.llm_available()
        else "heuristic"
    )


def _log(request, task, ref, output):
    """
    Store AI execution information.
    """

    AIRunLog.objects.create(
        task=task,
        user=request.user,
        provider=_provider(),
        input_ref=ref,
        output=output,
    )


def _candidate_ctx(request, validated_data):
    """
    Build candidate context from:
    1. Resume
    2. Explicit skills, experience, and education.
    """

    context = {
        "skills": validated_data.get(
            "skills",
            []
        ),
        "experience_years": validated_data.get(
            "experience_years",
            0
        ),
        "education": validated_data.get(
            "education",
            ""
        ),
    }

    resume_id = validated_data.get("resume_id")

    if resume_id:

        queryset = Resume.objects.all()

        # Candidates can only use their own resumes.
        if request.user.role == User.Role.CANDIDATE:

            queryset = queryset.filter(
                candidate=request.user
            )

        # Company users can only access resumes
        # associated with applications for their company.
        elif request.user.role != User.Role.SUPER_ADMIN:

            queryset = queryset.filter(
                applications__job__company_id=
                request.user.company_id
            )

        resume = get_object_or_404(
            queryset.distinct(),
            pk=resume_id
        )

        context = {
            "skills": resume.skills,
            "experience_years": (
                resume.parsed_data or {}
            ).get(
                "experience_years",
                0
            ),
            "education": (
                resume.parsed_data or {}
            ).get(
                "education",
                []
            ),
        }

    return context


# ================================================================
# RESUME PARSING
# ================================================================

class ParseResumeView(APIView):
    """
    POST /api/ai/parse-resume/

    Multipart:
        file

    OR JSON:
        {
            "resume_id": 1
        }

    Supported files:
        PDF
        DOCX
        TXT
    """

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):

        serializer = ParseResumeSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        validated_data = serializer.validated_data

        # --------------------------------------------------------
        # Uploaded file
        # --------------------------------------------------------

        if validated_data.get("file"):

            file = validated_data["file"]

            if file.size > 5 * 1024 * 1024:

                return Response(
                    {
                        "detail": (
                            "File too large "
                            "(max 5 MB)."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            text = resume_parser.extract_text(
                file,
                file.name
            )

            reference = f"upload:{file.name}"

        # --------------------------------------------------------
        # Existing resume
        # --------------------------------------------------------

        else:

            resume_id = validated_data["resume_id"]

            # Validate resume access.
            _candidate_ctx(
                request,
                {
                    "resume_id": resume_id
                }
            )

            resume = get_object_or_404(
                Resume.objects.all(),
                pk=resume_id
            )

            text = resume.extracted_text

            reference = f"resume:{resume.pk}"

        # --------------------------------------------------------
        # Parse resume
        # --------------------------------------------------------

        parsed = resume_parser.parse_resume_text(
            text
        )

        _log(
            request,
            "resume_parse",
            reference,
            {
                "skills": parsed.get(
                    "skills",
                    []
                )
            }
        )

        return Response(
            parsed,
            status=status.HTTP_200_OK
        )


# ================================================================
# JOB MATCHING
# ================================================================

class MatchView(APIView):
    """
    POST /api/ai/match/

    Example:
    {
        "job_id": 1,
        "resume_id": 5
    }

    OR:
    {
        "job_id": 1,
        "skills": ["Python", "Django"],
        "experience_years": 2,
        "education": "BCA"
    }
    """

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):

        serializer = MatchSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        validated_data = serializer.validated_data

        job = _job_for(
            request.user,
            validated_data["job_id"]
        )

        candidate_context = _candidate_ctx(
            request,
            validated_data
        )

        result = matcher.compute_match(
            build_job_context(job),
            candidate_context
        )

        _log(
            request,
            "job_match",
            f"job:{job.pk}",
            {
                "overall": result.get(
                    "overall_match"
                )
            }
        )

        return Response(
            result,
            status=status.HTTP_200_OK
        )


# ================================================================
# AI QUESTION GENERATION
# ================================================================

class GenerateQuestionsView(APIView):
    """
    POST /api/ai/generate-questions/

    Generates AI interview questions based on
    job and candidate context.
    """

    permission_classes = [
        IsCompanyMember
    ]

    def post(self, request):

        serializer = QuestionGenSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        validated_data = serializer.validated_data

        job = _job_for(
            request.user,
            validated_data["job_id"]
        )

        candidate_context = _candidate_ctx(
            request,
            validated_data
        )

        questions = interview_ai.generate_questions(
            build_job_context(job),
            candidate_context,
            validated_data["round_type"],
            validated_data["difficulty"],
            validated_data["count"],
        )

        _log(
            request,
            "generate_questions",
            f"job:{job.pk}",
            {
                "count": len(questions)
            }
        )

        return Response(
            {
                "provider": _provider(),
                "questions": questions,
            },
            status=status.HTTP_200_OK
        )


# ================================================================
# AI ANSWER ANALYSIS
# ================================================================

class AnalyzeAnswerView(APIView):
    """
    POST /api/ai/analyze-answer/

    Example:
    {
        "question": "Explain Django ORM.",
        "answer": "Django ORM is...",
        "expected_points": [
            "Models",
            "QuerySets"
        ],
        "job_id": 1
    }
    """

    permission_classes = [
        IsCompanyMember
    ]

    def post(self, request):

        serializer = AnalyzeAnswerSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        validated_data = serializer.validated_data

        job_context = None

        if validated_data.get("job_id"):

            job = _job_for(
                request.user,
                validated_data["job_id"]
            )

            job_context = build_job_context(
                job
            )

        result = interview_ai.analyze_answer(
            validated_data["question"],
            validated_data["answer"],
            validated_data.get(
                "expected_points"
            ),
            job_context,
        )

        _log(
            request,
            "analyze_answer",
            "adhoc",
            {
                "overall": result.get(
                    "overall_score"
                )
            }
        )

        return Response(
            result,
            status=status.HTTP_200_OK
        )


# ================================================================
# AI STATUS
# ================================================================

class StatusView(APIView):
    """
    GET /api/ai/status/
    """

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):

        return Response(
            {
                "llm_enabled": llm.llm_available(),
                "mode": _provider(),
                "features": [
                    "resume_parsing",
                    "job_matching",
                    "question_generation",
                    "adaptive_interview",
                    "answer_analysis",
                ],
            },
            status=status.HTTP_200_OK
        )


# ================================================================
# AI RUN LOG LIST
# ================================================================

class AIRunLogListView(APIView):
    """
    GET /api/ai/run-logs/

    Optional filters:
        ?task=job_match
        ?provider=llm

    HR staff can see AI execution logs
    belonging to their company.

    Super Admin can see all logs.
    """

    permission_classes = [
        IsHRStaff
    ]

    def get_queryset(self, request):

        queryset = AIRunLog.objects.all()

        user = request.user

        if user.role == User.Role.SUPER_ADMIN:
            return queryset

        return queryset.filter(
            user__company_id=user.company_id
        )

    def get(self, request):

        queryset = self.get_queryset(request)

        # --------------------------------------------------------
        # Optional filtering
        # --------------------------------------------------------

        task = request.query_params.get("task")

        provider = request.query_params.get("provider")

        if task:
            queryset = queryset.filter(
                task=task
            )

        if provider:
            queryset = queryset.filter(
                provider=provider
            )

        # Newest logs first.
        queryset = queryset.order_by(
            "-pk"
        )

        serializer = AIRunLogSerializer(
            queryset,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# ================================================================
# AI RUN LOG DETAIL
# ================================================================

class AIRunLogDetailView(APIView):
    """
    GET /api/ai/run-logs/<id>/

    View a single AI execution log.

    HR staff can access logs belonging to their
    company. Super Admin can access all logs.
    """

    permission_classes = [
        IsHRStaff
    ]

    def get_queryset(self, request):

        queryset = AIRunLog.objects.all()

        user = request.user

        if user.role == User.Role.SUPER_ADMIN:
            return queryset

        return queryset.filter(
            user__company_id=user.company_id
        )

    def get(self, request, pk):

        run_log = get_object_or_404(
            self.get_queryset(request),
            pk=pk
        )

        serializer = AIRunLogSerializer(
            run_log
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
