from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


User = settings.AUTH_USER_MODEL


class Interview(models.Model):

    class RoundType(models.TextChoices):
        CODING = "coding", "Coding"
        TECHNICAL = "technical", "Technical"
        AI = "ai", "AI interview"
        HR = "hr", "HR"
        FINAL = "final", "Final"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CONFIRMED = "confirmed", "Confirmed"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        RESCHEDULED = "rescheduled", "Rescheduled"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"
        ADAPTIVE = "adaptive", "Adaptive"

    application = models.ForeignKey(
        "recruitment.Application",
        on_delete=models.CASCADE,
        related_name="interviews",
    )

    round_number = models.PositiveSmallIntegerField(default=1)

    round_type = models.CharField(
        max_length=10,
        choices=RoundType.choices,
        default=RoundType.TECHNICAL,
    )

    title = models.CharField(max_length=200, blank=True)

    interviewer = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="interviews_assigned",
        help_text="Empty for AI-conducted rounds",
    )

    is_ai_conducted = models.BooleanField(default=False)

    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.ADAPTIVE,
    )

    max_questions = models.PositiveSmallIntegerField(default=8)

    scheduled_at = models.DateTimeField()

    duration_minutes = models.PositiveSmallIntegerField(default=45)

    meeting_link = models.URLField(blank=True)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True,
    )

    started_at = models.DateTimeField(null=True, blank=True)

    ended_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return (
            f"Interview #{self.pk} "
            f"({self.round_type}) app={self.application_id}"
        )


class InterviewQuestion(models.Model):

    class Source(models.TextChoices):
        AI = "ai", "AI generated"
        MANUAL = "manual", "Manual"

    interview = models.ForeignKey(
        Interview,
        on_delete=models.CASCADE,
        related_name="questions",
    )

    order = models.PositiveSmallIntegerField(default=1)

    text = models.TextField()

    topic = models.CharField(max_length=100, blank=True)

    difficulty = models.CharField(max_length=10, default="medium")

    expected_points = models.JSONField(default=list, blank=True)

    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.AI,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Question {self.order} - Interview #{self.interview_id}"


class InterviewAnswer(models.Model):

    question = models.OneToOneField(
        InterviewQuestion,
        on_delete=models.CASCADE,
        related_name="answer",
    )

    answer_text = models.TextField()

    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    technical_score = models.FloatField(default=0)

    communication_score = models.FloatField(default=0)

    problem_solving_score = models.FloatField(default=0)

    relevance_score = models.FloatField(default=0)

    confidence_score = models.FloatField(default=0)

    overall_score = models.FloatField(default=0)

    analysis = models.JSONField(default=dict, blank=True)

    submitted_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Answer for Question #{self.question_id}"


class InterviewFeedback(models.Model):

    class Recommendation(models.TextChoices):
        STRONG_HIRE = "strong_hire", "Strong hire"
        HIRE = "hire", "Hire"
        HOLD = "hold", "Hold"
        NO_HIRE = "no_hire", "No hire"

    interview = models.ForeignKey(
        Interview,
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )

    interviewer = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    technical_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    communication_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    problem_solving_rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    strengths = models.TextField(blank=True)

    weaknesses = models.TextField(blank=True)

    comments = models.TextField(blank=True)

    recommendation = models.CharField(
        max_length=12,
        choices=Recommendation.choices,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["interview", "interviewer"],
                name="unique_interview_feedback_per_interviewer",
            ),
        ]

    def __str__(self):
        return f"Feedback for Interview #{self.interview_id}"


class IntegrityEvent(models.Model):
    """
    Signals raised during an online interview.

    Events require human review and must not automatically determine
    whether a candidate has engaged in misconduct.
    """

    class EventType(models.TextChoices):
        NO_FACE = "no_face", "No face detected"
        MULTIPLE_FACES = "multiple_faces", "Multiple faces detected"
        PERSON_DETECTED = "person_detected", "Another person detected"
        MULTIPLE_VOICES = "multiple_voices", "Multiple voices"
        UNEXPECTED_AUDIO = "unexpected_audio", "Unexpected audio"
        AV_DESYNC = "av_desync", "Audio/video desync"
        CAMERA_CHANGE = "camera_change", "Sudden camera change"
        TAB_SWITCH = "tab_switch", "Left interview tab"
        OTHER = "other", "Other"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Review(models.TextChoices):
        PENDING = "pending", "Pending review"
        DISMISSED = "dismissed", "Dismissed (no concern)"
        CONCERN = "concern", "Confirmed concern"

    interview = models.ForeignKey(
        Interview,
        on_delete=models.CASCADE,
        related_name="integrity_events",
    )

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )

    severity = models.CharField(
        max_length=6,
        choices=Severity.choices,
        default=Severity.LOW,
    )

    offset_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Seconds since interview start",
    )

    duration_seconds = models.PositiveIntegerField(default=0)

    confidence = models.FloatField(null=True, blank=True)

    details = models.JSONField(default=dict, blank=True)

    source = models.CharField(max_length=20, default="client")

    detected_at = models.DateTimeField(auto_now_add=True)

    review_status = models.CharField(
        max_length=10,
        choices=Review.choices,
        default=Review.PENDING,
        db_index=True,
    )

    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    review_note = models.TextField(blank=True)

    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["offset_seconds", "detected_at"]

    def __str__(self):
        return (
            f"{self.event_type} - Interview #{self.interview_id}"
        )