
from rest_framework import serializers

from .models import AIRunLog


# ============================================================
# RESUME PARSING
# ============================================================

class ParseResumeSerializer(serializers.Serializer):

    file = serializers.FileField(required=False)

    resume_id = serializers.IntegerField(
        required=False,
        min_value=1
    )

    def validate(self, attrs):

        file = attrs.get("file")
        resume_id = attrs.get("resume_id")

        if not file and not resume_id:
            raise serializers.ValidationError(
                "Provide either 'file' or 'resume_id'."
            )

        if file and resume_id:
            raise serializers.ValidationError(
                "Provide either 'file' or 'resume_id', not both."
            )

        return attrs


# ============================================================
# JOB MATCHING
# ============================================================

class MatchSerializer(serializers.Serializer):

    job_id = serializers.IntegerField(
        min_value=1
    )

    resume_id = serializers.IntegerField(
        required=False,
        min_value=1
    )

    skills = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )

    experience_years = serializers.FloatField(
        required=False,
        min_value=0,
        default=0
    )

    education = serializers.CharField(
        required=False,
        allow_blank=True,
        default=""
    )

    def validate(self, attrs):

        if attrs.get("resume_id") and (
            attrs.get("skills")
            or attrs.get("experience_years", 0) > 0
            or attrs.get("education")
        ):
            raise serializers.ValidationError(
                "Provide either 'resume_id' or explicit candidate details."
            )

        return attrs


# ============================================================
# INTERVIEW QUESTION GENERATION
# ============================================================

class QuestionGenSerializer(serializers.Serializer):

    job_id = serializers.IntegerField(
        min_value=1
    )

    resume_id = serializers.IntegerField(
        required=False,
        min_value=1
    )

    skills = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )

    round_type = serializers.ChoiceField(
        choices=[
            "technical",
            "ai",
            "hr",
            "final"
        ],
        default="technical"
    )

    difficulty = serializers.ChoiceField(
        choices=[
            "easy",
            "medium",
            "hard"
        ],
        default="medium"
    )

    count = serializers.IntegerField(
        min_value=1,
        max_value=15,
        default=5
    )


# ============================================================
# INTERVIEW ANSWER ANALYSIS
# ============================================================

class AnalyzeAnswerSerializer(serializers.Serializer):

    question = serializers.CharField()

    answer = serializers.CharField(
        allow_blank=True
    )

    expected_points = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list
    )

    job_id = serializers.IntegerField(
        required=False,
        min_value=1
    )


# ============================================================
# AI RUN LOG SERIALIZER
# ============================================================

class AIRunLogSerializer(serializers.ModelSerializer):

    class Meta:
        model = AIRunLog

        fields = [
            "id",
            "task",
            "user",
            "provider",
            "input_ref",
            "output",
            "created_at",
        ]

        read_only_fields = fields
