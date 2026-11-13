from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


User = settings.AUTH_USER_MODEL


# =========================================================
# JOBS
# =========================================================

class Job(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full time"
        PART_TIME = "part_time", "Part time"
        CONTRACT = "contract", "Contract"
        INTERNSHIP = "internship", "Internship"

    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs_created",
    )
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=200, blank=True)

    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )

    salary_min = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    salary_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=3, default="INR")

    experience_min = models.PositiveSmallIntegerField(default=0)
    experience_max = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    required_skills = models.JSONField(default=list)
    preferred_skills = models.JSONField(default=list, blank=True)

    education = models.CharField(max_length=200, blank=True)
    description = models.TextField()
    responsibilities = models.TextField(blank=True)
    requirements = models.TextField(blank=True)

    deadline = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} @ {self.company}"


class JobStage(models.Model):
    class StageType(models.TextChoices):
        RESUME_SCREENING = "resume_screening", "Resume Screening"
        CODING_ASSESSMENT = "coding_assessment", "Coding Assessment"
        TECHNICAL_INTERVIEW = "technical_interview", "Technical Interview"
        AI_INTERVIEW = "ai_interview", "AI Interview"
        HR_INTERVIEW = "hr_interview", "HR Interview"
        FINAL_DECISION = "final_decision", "Final Decision"

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="stages",
    )
    name = models.CharField(max_length=100)
    stage_type = models.CharField(
        max_length=30,
        choices=StageType.choices,
    )
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "order"],
                name="unique_job_stage_order",
            )
        ]

    def __str__(self):
        return f"{self.job_id}:{self.order} {self.name}"


# =========================================================
# SAVED JOBS
# =========================================================

class SavedJob(models.Model):
    candidate = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_jobs",
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="saved_by_candidates",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "job"],
                name="unique_candidate_saved_job",
            )
        ]

    def __str__(self):
        return f"{self.candidate} saved {self.job}"


# =========================================================
# RESUMES
# =========================================================

def resume_upload_path(instance, filename):
    return f"resumes/{instance.candidate_id}/{filename}"


class Resume(models.Model):
    candidate = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="resumes",
    )

    file = models.FileField(
        upload_to=resume_upload_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "docx", "txt"]
            )
        ],
    )

    original_name = models.CharField(max_length=255, blank=True)
    extracted_text = models.TextField(blank=True)
    parsed_data = models.JSONField(default=dict, blank=True)
    skills = models.JSONField(default=list, blank=True)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Resume #{self.pk} of {self.candidate_id}"


# =========================================================
# APPLICATIONS
# =========================================================

class Application(models.Model):
    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        SCREENING = "screening", "Screening"
        SHORTLISTED = "shortlisted", "Shortlisted"
        ASSESSMENT = "assessment", "Assessment"
        INTERVIEW = "interview", "Interview"
        FINAL_REVIEW = "final_review", "Final Review"
        SELECTED = "selected", "Selected"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"
        HIRED = "hired", "Hired"

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    candidate = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    resume = models.ForeignKey(
        Resume,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications",
    )

    cover_letter = models.TextField(blank=True)

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.APPLIED,
        db_index=True,
    )

    source = models.CharField(
        max_length=50,
        blank=True,
        default="portal",
    )

    # AI resume screening and matching
    skill_match = models.FloatField(default=0)
    experience_match = models.FloatField(default=0)
    education_match = models.FloatField(default=0)
    overall_match = models.FloatField(default=0, db_index=True)

    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    ai_summary = models.TextField(blank=True)

    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-overall_match", "-applied_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "candidate"],
                name="unique_job_candidate_application",
            )
        ]

    def __str__(self):
        return (
            f"{self.candidate_id} -> "
            f"{self.job_id} ({self.status})"
        )


class ApplicationStatusHistory(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="history",
    )

    from_status = models.CharField(max_length=15, blank=True)
    to_status = models.CharField(max_length=15)

    changed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return (
            f"Application {self.application_id}: "
            f"{self.from_status} -> {self.to_status}"
        )


# =========================================================
# CODING PROBLEMS
# =========================================================

class CodingProblem(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        related_name="coding_problems",
    )

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    title = models.CharField(max_length=200)
    description = models.TextField()

    input_format = models.TextField(blank=True)
    output_format = models.TextField(blank=True)
    constraints = models.TextField(blank=True)

    examples = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            '[{"input": "", "output": "", '
            '"explanation": ""}]'
        ),
    )

    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.EASY,
    )

    time_limit_seconds = models.PositiveSmallIntegerField(default=2)
    memory_limit_mb = models.PositiveIntegerField(default=256)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ProblemTestCase(models.Model):
    problem = models.ForeignKey(
        CodingProblem,
        on_delete=models.CASCADE,
        related_name="test_cases",
    )

    input_data = models.TextField(blank=True)
    expected_output = models.TextField()
    is_hidden = models.BooleanField(default=True)
    weight = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f"TestCase {self.pk} of problem {self.problem_id}"


# =========================================================
# ASSESSMENTS
# =========================================================

def default_languages():
    return ["python", "javascript", "java", "cpp"]


class Assessment(models.Model):
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        related_name="assessments",
    )

    job = models.ForeignKey(
        Job,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments",
    )

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)

    problems = models.ManyToManyField(
        CodingProblem,
        related_name="assessments",
    )

    duration_minutes = models.PositiveSmallIntegerField(default=60)
    passing_score = models.FloatField(default=60)
    languages = models.JSONField(default=default_languages)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AssessmentAttempt(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        EXPIRED = "expired", "Expired"

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="attempts",
    )

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="assessment_attempts",
    )

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.ASSIGNED,
    )

    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    score = models.FloatField(null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "application"],
                name="unique_assessment_application_attempt",
            )
        ]

    def __str__(self):
        return (
            f"{self.assessment.title} - "
            f"Application {self.application_id}"
        )


class Submission(models.Model):
    class Verdict(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        PARTIAL = "partial", "Partially correct"
        WRONG = "wrong", "Wrong answer"
        ERROR = "error", "Runtime / compile error"
        TIMEOUT = "timeout", "Time limit exceeded"

    attempt = models.ForeignKey(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="submissions",
    )

    problem = models.ForeignKey(
        CodingProblem,
        on_delete=models.CASCADE,
        related_name="submissions",
    )

    language = models.CharField(max_length=20)
    code = models.TextField()

    verdict = models.CharField(
        max_length=10,
        choices=Verdict.choices,
        default=Verdict.WRONG,
    )

    passed_cases = models.PositiveSmallIntegerField(default=0)
    total_cases = models.PositiveSmallIntegerField(default=0)
    score = models.FloatField(default=0)
    results = models.JSONField(default=list, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Submission {self.pk} - {self.verdict}"


# =========================================================
# CANDIDATE SCORECARDS
# =========================================================

class CandidateScore(models.Model):
    class Recommendation(models.TextChoices):
        STRONG_HIRE = "strong_hire", "Strong hire"
        HIRE = "hire", "Hire"
        HOLD = "hold", "Hold"
        NO_HIRE = "no_hire", "No hire"

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name="scorecard",
    )

    resume_score = models.FloatField(default=0)
    coding_score = models.FloatField(null=True, blank=True)
    interview_score = models.FloatField(null=True, blank=True)
    communication_score = models.FloatField(null=True, blank=True)
    problem_solving_score = models.FloatField(null=True, blank=True)

    overall_score = models.FloatField(default=0)

    suggested_recommendation = models.CharField(
        max_length=12,
        choices=Recommendation.choices,
        blank=True,
    )

    recommendation = models.CharField(
        max_length=12,
        choices=Recommendation.choices,
        blank=True,
        help_text="Set manually by HR",
    )

    remarks = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Scorecard for application {self.application_id}"


# =========================================================
# HIRING DECISIONS
# =========================================================

class HiringDecision(models.Model):
    class Decision(models.TextChoices):
        SELECTED = "selected", "Selected"
        REJECTED = "rejected", "Rejected"
        HOLD = "hold", "On hold"

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name="decision",
    )

    decision = models.CharField(
        max_length=10,
        choices=Decision.choices,
    )

    reason = models.TextField(blank=True)

    decided_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    decided_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (
            f"Decision for application {self.application_id}: "
            f"{self.decision}"
        )


# =========================================================
# OFFERS
# =========================================================

class Offer(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        WITHDRAWN = "withdrawn", "Withdrawn"

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name="offer",
    )

    position = models.CharField(max_length=200)
    salary = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    benefits = models.TextField(blank=True)

    employment_type = models.CharField(
        max_length=20,
        choices=Job.EmploymentType.choices,
        default=Job.EmploymentType.FULL_TIME,
    )

    joining_date = models.DateField()
    expiry_date = models.DateField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    sent_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Offer for application {self.application_id}"


# =========================================================
# NOTIFICATIONS
# =========================================================

class Notification(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    type = models.CharField(max_length=30, default="info")
    link = models.CharField(max_length=300, blank=True)

    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.user_id}"