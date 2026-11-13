from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import CandidateProfile, User
from accounts.serializers import CandidateProjectSerializer
from ai_engine.services.skills import canonicalize_list

from .models import (
    Application,
    ApplicationStatusHistory,
    Assessment,
    AssessmentAttempt,
    CandidateScore,
    CodingProblem,
    HiringDecision,
    Job,
    JobStage,
    Notification,
    Offer,
    ProblemTestCase,
    Resume,
    SavedJob,
    Submission,
)


LANGS = ["python", "javascript", "java", "cpp"]


# =========================================================
# JOBS
# =========================================================

class JobStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobStage
        fields = ["id", "name", "stage_type", "order"]


DEFAULT_STAGES = [
    ("Resume Screening", "resume_screening"),
    ("Coding Assessment", "coding_assessment"),
    ("Technical Interview", "technical_interview"),
    ("HR Interview", "hr_interview"),
    ("Final Decision", "final_decision"),
]


class JobSerializer(serializers.ModelSerializer):
    stages = JobStageSerializer(many=True, required=False)
    company_name = serializers.CharField(
        source="company.name",
        read_only=True,
    )
    applications_count = serializers.SerializerMethodField()
    has_applied = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "company",
            "company_name",
            "created_by",
            "title",
            "department",
            "location",
            "employment_type",
            "salary_min",
            "salary_max",
            "currency",
            "experience_min",
            "experience_max",
            "required_skills",
            "preferred_skills",
            "education",
            "description",
            "responsibilities",
            "requirements",
            "deadline",
            "status",
            "stages",
            "applications_count",
            "has_applied",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_applications_count(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return obj.applications.count()

        if request.user.role == User.Role.CANDIDATE:
            return None

        return obj.applications.count()

    def get_has_applied(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return None

        if request.user.role == User.Role.CANDIDATE:
            return obj.applications.filter(
                candidate=request.user
            ).exists()

        return None

    def validate(self, attrs):
        salary_min = attrs.get(
            "salary_min",
            getattr(self.instance, "salary_min", None),
        )
        salary_max = attrs.get(
            "salary_max",
            getattr(self.instance, "salary_max", None),
        )

        if (
            salary_min is not None
            and salary_max is not None
            and salary_min > salary_max
        ):
            raise serializers.ValidationError(
                "salary_min cannot exceed salary_max."
            )

        experience_min = attrs.get(
            "experience_min",
            getattr(self.instance, "experience_min", 0),
        )
        experience_max = attrs.get(
            "experience_max",
            getattr(self.instance, "experience_max", None),
        )

        if (
            experience_max is not None
            and experience_min > experience_max
        ):
            raise serializers.ValidationError(
                "experience_min cannot exceed experience_max."
            )

        return attrs

    def validate_required_skills(self, value):
        if not value:
            raise serializers.ValidationError(
                "At least one required skill is needed."
            )

        return canonicalize_list(value)

    def validate_preferred_skills(self, value):
        return canonicalize_list(value)

    @transaction.atomic
    def create(self, validated_data):
        stages = validated_data.pop("stages", None)

        job = Job.objects.create(**validated_data)
        self._save_stages(job, stages)

        return job

    @transaction.atomic
    def update(self, instance, validated_data):
        stages = validated_data.pop("stages", None)

        instance = super().update(instance, validated_data)

        if stages is not None:
            instance.stages.all().delete()
            self._save_stages(instance, stages)

        return instance

    @staticmethod
    def _save_stages(job, stages):
        if stages:
            for index, stage in enumerate(stages, start=1):
                JobStage.objects.create(
                    job=job,
                    name=stage["name"],
                    stage_type=stage["stage_type"],
                    order=stage.get("order") or index,
                )

        elif not job.stages.exists():
            for index, (name, stage_type) in enumerate(
                DEFAULT_STAGES,
                start=1,
            ):
                JobStage.objects.create(
                    job=job,
                    name=name,
                    stage_type=stage_type,
                    order=index,
                )


# =========================================================
# RESUMES
# =========================================================

class ResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = [
            "id",
            "file",
            "original_name",
            "parsed_data",
            "skills",
            "is_primary",
            "uploaded_at",
        ]
        read_only_fields = [
            "id",
            "original_name",
            "parsed_data",
            "skills",
            "uploaded_at",
        ]

    def validate_file(self, file):
        max_size = settings.RESUME_MAX_MB * 1024 * 1024

        if file.size > max_size:
            raise serializers.ValidationError(
                f"File too large (max {settings.RESUME_MAX_MB} MB)."
            )

        extension = (
            file.name.rsplit(".", 1)[-1].lower()
            if "." in file.name
            else ""
        )

        allowed_extensions = settings.RESUME_ALLOWED_EXTENSIONS

        if extension not in allowed_extensions:
            raise serializers.ValidationError(
                "Allowed types: " + ", ".join(allowed_extensions)
            )

        return file


# =========================================================
# APPLICATIONS
# =========================================================

class ApplicationStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.full_name",
        read_only=True,
        default=None,
    )

    class Meta:
        model = ApplicationStatusHistory
        fields = [
            "id",
            "from_status",
            "to_status",
            "changed_by_name",
            "note",
            "created_at",
        ]


class ApplicationSerializer(serializers.ModelSerializer):
    job_title = serializers.CharField(
        source="job.title",
        read_only=True,
    )
    company_name = serializers.CharField(
        source="job.company.name",
        read_only=True,
    )
    candidate_name = serializers.CharField(
        source="candidate.full_name",
        read_only=True,
    )
    candidate_email = serializers.CharField(
        source="candidate.email",
        read_only=True,
    )

    AI_FIELDS = (
        "skill_match",
        "experience_match",
        "education_match",
        "overall_match",
        "matched_skills",
        "missing_skills",
        "ai_summary",
    )

    class Meta:
        model = Application
        fields = [
            "id",
            "job",
            "job_title",
            "company_name",
            "candidate",
            "candidate_name",
            "candidate_email",
            "resume",
            "cover_letter",
            "status",
            "source",
            "skill_match",
            "experience_match",
            "education_match",
            "overall_match",
            "matched_skills",
            "missing_skills",
            "ai_summary",
            "applied_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "candidate",
            "status",
            "skill_match",
            "experience_match",
            "education_match",
            "overall_match",
            "matched_skills",
            "missing_skills",
            "ai_summary",
            "applied_at",
            "updated_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")

        if request is None:
            return attrs

        if self.instance is None:
            job = attrs["job"]
            candidate = request.user

            if job.status != Job.Status.OPEN:
                raise serializers.ValidationError({
                    "job": "This job is not open for applications."
                })

            if (
                job.deadline
                and job.deadline < timezone.localdate()
            ):
                raise serializers.ValidationError({
                    "job": "The application deadline has passed."
                })

            if Application.objects.filter(
                job=job,
                candidate=candidate,
            ).exists():
                raise serializers.ValidationError({
                    "job": "You have already applied to this job."
                })

            resume = attrs.get("resume")

            if resume and resume.candidate_id != candidate.id:
                raise serializers.ValidationError({
                    "resume": "Invalid resume."
                })

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")

        if (
            request
            and request.user.is_authenticated
            and request.user.role == User.Role.CANDIDATE
        ):
            for field in self.AI_FIELDS:
                data.pop(field, None)

        return data


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=Application.Status.choices
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=300,
    )


class CompareSerializer(serializers.Serializer):
    application_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=2,
        max_length=10,
    )


# =========================================================
# SAVED JOBS
# =========================================================

class SavedJobSerializer(serializers.ModelSerializer):
    job_title = serializers.CharField(
        source="job.title",
        read_only=True,
    )
    company_name = serializers.CharField(
        source="job.company.name",
        read_only=True,
    )

    class Meta:
        model = SavedJob
        fields = [
            "id",
            "job",
            "job_title",
            "company_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "job_title",
            "company_name",
            "created_at",
        ]

    def validate_job(self, job):
        request = self.context.get("request")

        if request and SavedJob.objects.filter(
            candidate=request.user,
            job=job,
        ).exists():
            raise serializers.ValidationError(
                "You have already saved this job."
            )

        return job


# =========================================================
# CODING PROBLEMS AND TEST CASES
# =========================================================

class TestCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProblemTestCase
        fields = [
            "id",
            "input_data",
            "expected_output",
            "is_hidden",
            "weight",
        ]


class CodingProblemSerializer(serializers.ModelSerializer):
    test_cases = TestCaseSerializer(
        many=True,
        required=False,
    )

    class Meta:
        model = CodingProblem
        fields = [
            "id",
            "company",
            "title",
            "description",
            "input_format",
            "output_format",
            "constraints",
            "examples",
            "difficulty",
            "time_limit_seconds",
            "memory_limit_mb",
            "test_cases",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_at",
        ]

    @transaction.atomic
    def create(self, validated_data):
        test_cases = validated_data.pop("test_cases", [])

        problem = CodingProblem.objects.create(**validated_data)

        ProblemTestCase.objects.bulk_create([
            ProblemTestCase(
                problem=problem,
                **test_case,
            )
            for test_case in test_cases
        ])

        return problem

    @transaction.atomic
    def update(self, instance, validated_data):
        test_cases = validated_data.pop("test_cases", None)

        instance = super().update(instance, validated_data)

        if test_cases is not None:
            instance.test_cases.all().delete()

            ProblemTestCase.objects.bulk_create([
                ProblemTestCase(
                    problem=instance,
                    **test_case,
                )
                for test_case in test_cases
            ])

        return instance


class CandidateProblemSerializer(serializers.ModelSerializer):
    sample_cases = serializers.SerializerMethodField()

    class Meta:
        model = CodingProblem
        fields = [
            "id",
            "title",
            "description",
            "input_format",
            "output_format",
            "constraints",
            "examples",
            "difficulty",
            "time_limit_seconds",
            "memory_limit_mb",
            "sample_cases",
        ]

    def get_sample_cases(self, obj):
        return [
            {
                "input": test_case.input_data,
                "expected_output": test_case.expected_output,
            }
            for test_case in obj.test_cases.all()
            if not test_case.is_hidden
        ]


# =========================================================
# ASSESSMENTS
# =========================================================

class AssessmentSerializer(serializers.ModelSerializer):
    problem_ids = serializers.PrimaryKeyRelatedField(
        queryset=CodingProblem.objects.all(),
        many=True,
        source="problems",
        write_only=True,
    )
    problems = serializers.SerializerMethodField()

    class Meta:
        model = Assessment
        fields = [
            "id",
            "company",
            "job",
            "title",
            "instructions",
            "problem_ids",
            "problems",
            "duration_minutes",
            "passing_score",
            "languages",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "company",
            "created_at",
        ]

    def get_problems(self, obj):
        return [
            {
                "id": problem.id,
                "title": problem.title,
                "difficulty": problem.difficulty,
            }
            for problem in obj.problems.all()
        ]

    def validate_languages(self, value):
        unsupported = [
            language
            for language in value
            if language not in LANGS
        ]

        if unsupported:
            raise serializers.ValidationError(
                f"Unsupported languages: {unsupported}. "
                f"Supported: {LANGS}"
            )

        return value

    def validate(self, attrs):
        request = self.context.get("request")

        if not request:
            return attrs

        company_id = request.user.company_id

        for problem in attrs.get("problems", []):
            if company_id and problem.company_id != company_id:
                raise serializers.ValidationError({
                    "problem_ids": (
                        "Problem belongs to another company."
                    )
                })

        return attrs


class AssignAssessmentSerializer(serializers.Serializer):
    application_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
    )


class SubmissionSerializer(serializers.ModelSerializer):
    problem_title = serializers.CharField(
        source="problem.title",
        read_only=True,
    )

    class Meta:
        model = Submission
        fields = [
            "id",
            "problem",
            "problem_title",
            "language",
            "code",
            "verdict",
            "passed_cases",
            "total_cases",
            "score",
            "results",
            "submitted_at",
        ]
        read_only_fields = [
            "id",
            "verdict",
            "passed_cases",
            "total_cases",
            "score",
            "results",
            "submitted_at",
        ]


class SubmitCodeSerializer(serializers.Serializer):
    problem = serializers.PrimaryKeyRelatedField(
        queryset=CodingProblem.objects.all()
    )
    language = serializers.ChoiceField(choices=LANGS)
    code = serializers.CharField(max_length=50000)


class AttemptSerializer(serializers.ModelSerializer):
    assessment_title = serializers.CharField(
        source="assessment.title",
        read_only=True,
    )
    duration_minutes = serializers.IntegerField(
        source="assessment.duration_minutes",
        read_only=True,
    )
    candidate_name = serializers.CharField(
        source="application.candidate.full_name",
        read_only=True,
    )
    job_title = serializers.CharField(
        source="application.job.title",
        read_only=True,
    )

    class Meta:
        model = AssessmentAttempt
        fields = [
            "id",
            "assessment",
            "assessment_title",
            "application",
            "candidate_name",
            "job_title",
            "status",
            "duration_minutes",
            "assigned_at",
            "started_at",
            "submitted_at",
            "score",
            "passed",
        ]
        read_only_fields = fields


# =========================================================
# SCORECARDS AND HIRING DECISIONS
# =========================================================

class ScorecardSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(
        source="application.candidate.full_name",
        read_only=True,
    )
    job_title = serializers.CharField(
        source="application.job.title",
        read_only=True,
    )

    class Meta:
        model = CandidateScore
        fields = [
            "id",
            "application",
            "candidate_name",
            "job_title",
            "resume_score",
            "coding_score",
            "interview_score",
            "communication_score",
            "problem_solving_score",
            "overall_score",
            "suggested_recommendation",
            "recommendation",
            "remarks",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "application",
            "resume_score",
            "coding_score",
            "interview_score",
            "communication_score",
            "problem_solving_score",
            "overall_score",
            "suggested_recommendation",
            "updated_at",
        ]


class HiringDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HiringDecision
        fields = [
            "id",
            "application",
            "decision",
            "reason",
            "decided_by",
            "decided_at",
        ]
        read_only_fields = [
            "id",
            "decided_by",
            "decided_at",
        ]


# =========================================================
# OFFERS
# =========================================================

class OfferSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(
        source="application.candidate.full_name",
        read_only=True,
    )
    company_name = serializers.CharField(
        source="application.job.company.name",
        read_only=True,
    )

    class Meta:
        model = Offer
        fields = [
            "id",
            "application",
            "candidate_name",
            "company_name",
            "position",
            "salary",
            "currency",
            "benefits",
            "employment_type",
            "joining_date",
            "expiry_date",
            "status",
            "sent_at",
            "responded_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "sent_at",
            "responded_at",
            "created_at",
        ]

    def validate(self, attrs):
        expiry_date = attrs.get(
            "expiry_date",
            getattr(self.instance, "expiry_date", None),
        )
        joining_date = attrs.get(
            "joining_date",
            getattr(self.instance, "joining_date", None),
        )

        if (
            expiry_date
            and joining_date
            and expiry_date > joining_date
        ):
            raise serializers.ValidationError(
                "Offer expiry must be on or before the joining date."
            )

        return attrs


# =========================================================
# NOTIFICATIONS
# =========================================================

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "type",
            "link",
            "is_read",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "title",
            "message",
            "type",
            "link",
            "created_at",
        ]


# =========================================================
# CANDIDATES
# =========================================================

class CandidateListSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()
    applications = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "profile",
            "applications",
        ]

    def get_profile(self, obj):
        profile = CandidateProfile.objects.filter(user=obj).first()

        if not profile:
            return None

        if not profile.is_public:
            return {"is_public": False}

        return {
            "headline": profile.headline,
            "location": profile.location,
            "experience_years": profile.experience_years,
            "skills": profile.skills,
            "education": profile.education,
            "experience": profile.experience,
            "certifications": profile.certifications,
            "is_public": profile.is_public,
            "github": profile.github,
            "linkedin": profile.linkedin,
            "portfolio": profile.portfolio,
            "projects": CandidateProjectSerializer(
                profile.candidate_projects.all(),
                many=True,
                context=self.context,
            ).data,
        }

    def get_applications(self, obj):
        request = self.context.get("request")
        company_id = (
            request.user.company_id
            if request and request.user.is_authenticated
            else None
        )

        queryset = obj.applications.select_related("job")

        if company_id:
            queryset = queryset.filter(job__company_id=company_id)

        return [
            {
                "id": application.id,
                "job": application.job.title,
                "status": application.status,
                "overall_match": application.overall_match,
            }
            for application in queryset
        ]