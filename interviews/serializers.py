from django.utils import timezone
from rest_framework import serializers

from accounts.models import User

from .models import (
    Interview,
    InterviewAnswer,
    InterviewFeedback,
    InterviewQuestion,
    IntegrityEvent,
)


class InterviewSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(
        source="application.candidate.full_name",
        read_only=True,
    )

    job_title = serializers.CharField(
        source="application.job.title",
        read_only=True,
    )

    interviewer_name = serializers.CharField(
        source="interviewer.full_name",
        read_only=True,
        default=None,
    )

    questions_count = serializers.IntegerField(
        source="questions.count",
        read_only=True,
    )

    class Meta:
        model = Interview
        fields = [
            "id",
            "application",
            "candidate_name",
            "job_title",
            "round_number",
            "round_type",
            "title",
            "interviewer",
            "interviewer_name",
            "is_ai_conducted",
            "difficulty",
            "max_questions",
            "scheduled_at",
            "duration_minutes",
            "meeting_link",
            "status",
            "started_at",
            "ended_at",
            "notes",
            "questions_count",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "status",
            "started_at",
            "ended_at",
            "created_at",
        ]

    def validate_scheduled_at(self, value):
        if self.instance is None and value < timezone.now():
            raise serializers.ValidationError(
                "Interview must be scheduled in the future."
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request")

        if request is None:
            raise serializers.ValidationError(
                "Request context is required."
            )

        user = request.user

        application = attrs.get("application")

        if application is None and self.instance is not None:
            application = self.instance.application

        if (
            user.role != User.Role.SUPER_ADMIN
            and application
            and application.job.company_id != user.company_id
        ):
            raise serializers.ValidationError({
                "application": (
                    "Application belongs to another company."
                )
            })

        interviewer = attrs.get("interviewer")

        if interviewer is None and self.instance is not None:
            interviewer = self.instance.interviewer

        if (
            interviewer
            and application
            and interviewer.company_id != application.job.company_id
        ):
            raise serializers.ValidationError({
                "interviewer": (
                    "Interviewer must belong to the same company."
                )
            })

        if (
            interviewer
            and interviewer.role == User.Role.CANDIDATE
        ):
            raise serializers.ValidationError({
                "interviewer": "Invalid interviewer."
            })

        is_ai_conducted = attrs.get(
            "is_ai_conducted",
            (
                self.instance.is_ai_conducted
                if self.instance is not None
                else False
            ),
        )

        if not is_ai_conducted and not interviewer:
            raise serializers.ValidationError({
                "interviewer": (
                    "Assign an interviewer or mark the round "
                    "as AI-conducted."
                )
            })

        return attrs


class RescheduleSerializer(serializers.Serializer):
    scheduled_at = serializers.DateTimeField()

    meeting_link = serializers.URLField(
        required=False,
        allow_blank=True,
    )

    def validate_scheduled_at(self, value):
        if value < timezone.now():
            raise serializers.ValidationError(
                "New time must be in the future."
            )
        return value


class InterviewAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterviewAnswer

        fields = [
            "id",
            "answer_text",
            "duration_seconds",
            "technical_score",
            "communication_score",
            "problem_solving_score",
            "relevance_score",
            "confidence_score",
            "overall_score",
            "analysis",
            "submitted_at",
        ]

        read_only_fields = fields


class InterviewQuestionSerializer(serializers.ModelSerializer):
    answer = InterviewAnswerSerializer(read_only=True)

    class Meta:
        model = InterviewQuestion

        fields = [
            "id",
            "order",
            "text",
            "topic",
            "difficulty",
            "expected_points",
            "source",
            "answer",
        ]

        read_only_fields = [
            "id",
            "order",
            "source",
            "answer",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        request = self.context.get("request")

        if (
            request is not None
            and request.user.role == User.Role.CANDIDATE
        ):
            # Candidates should not see the scoring rubric or
            # AI-generated answer analysis.
            data.pop("expected_points", None)
            data.pop("answer", None)

        return data


class GenerateQuestionsSerializer(serializers.Serializer):
    count = serializers.IntegerField(
        min_value=1,
        max_value=15,
        default=5,
    )

    difficulty = serializers.ChoiceField(
        choices=["easy", "medium", "hard"],
        default="medium",
    )


class SubmitAnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()

    answer_text = serializers.CharField(
        max_length=10_000,
        allow_blank=True,
    )

    duration_seconds = serializers.IntegerField(
        min_value=0,
        required=False,
    )

    request_next = serializers.BooleanField(
        default=False,
        help_text=(
            "Adaptive mode: also return the next question."
        ),
    )


class InterviewFeedbackSerializer(serializers.ModelSerializer):
    interviewer_name = serializers.CharField(
        source="interviewer.full_name",
        read_only=True,
        default=None,
    )

    class Meta:
        model = InterviewFeedback

        fields = [
            "id",
            "interview",
            "interviewer",
            "interviewer_name",
            "technical_rating",
            "communication_rating",
            "problem_solving_rating",
            "strengths",
            "weaknesses",
            "comments",
            "recommendation",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "interview",
            "interviewer",
            "created_at",
        ]


class IntegrityEventSerializer(serializers.ModelSerializer):
    event_label = serializers.CharField(
        source="get_event_type_display",
        read_only=True,
    )

    class Meta:
        model = IntegrityEvent

        fields = [
            "id",
            "interview",
            "event_type",
            "event_label",
            "severity",
            "offset_seconds",
            "duration_seconds",
            "confidence",
            "details",
            "source",
            "detected_at",
            "review_status",
            "reviewed_by",
            "review_note",
            "reviewed_at",
        ]

        read_only_fields = [
            "id",
            "source",
            "detected_at",
            "review_status",
            "reviewed_by",
            "review_note",
            "reviewed_at",
        ]

    def validate_interview(self, interview):
        if interview.status != Interview.Status.IN_PROGRESS:
            raise serializers.ValidationError(
                "Events can only be logged while the interview "
                "is in progress."
            )
        return interview


class ReviewEventSerializer(serializers.Serializer):
    review_status = serializers.ChoiceField(
        choices=[
            ("dismissed", "Dismissed"),
            ("concern", "Confirmed concern"),
        ]
    )

    review_note = serializers.CharField(
        required=False,
        allow_blank=True,
    )