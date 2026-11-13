import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


# =========================================================
# USER MANAGER
# =========================================================

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)

        user = self.model(
            email=email,
            **extra
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)

        return self._create_user(
            email,
            password,
            **extra
        )

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", "super_admin")

        return self._create_user(
            email,
            password,
            **extra
        )


# =========================================================
# COMPANY
# =========================================================

class Company(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    class Size(models.TextChoices):
        S1 = "1-10", "1-10"
        S2 = "11-50", "11-50"
        S3 = "51-200", "51-200"
        S4 = "201-1000", "201-1000"
        S5 = "1000+", "1000+"

    name = models.CharField(
        max_length=200,
        unique=True
    )

    industry = models.CharField(
        max_length=120,
        blank=True
    )

    email = models.EmailField()

    website = models.URLField(
        blank=True
    )

    location = models.CharField(
        max_length=200,
        blank=True
    )

    size = models.CharField(
        max_length=20,
        choices=Size.choices,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    logo = models.ImageField(
        upload_to="company_logos/",
        blank=True,
        null=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name


# =========================================================
# USER
# =========================================================

class User(AbstractUser):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        COMPANY_ADMIN = "company_admin", "Company Admin"
        HR = "hr", "HR / Recruiter"
        INTERVIEWER = "interviewer", "Interviewer"
        CANDIDATE = "candidate", "Candidate"

    # Remove username
    username = None

    # Login using email
    email = models.EmailField(
        unique=True
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CANDIDATE,
        db_index=True
    )

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    designation = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. HR Manager, Technical Interviewer"
    )

    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members"
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True
    )

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = [
        "first_name"
    ]

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]

    @property
    def full_name(self):
        return (
            f"{self.first_name} {self.last_name}".strip()
            or self.email
        )

    @property
    def is_company_staff(self):
        return self.role in (
            self.Role.COMPANY_ADMIN,
            self.Role.HR,
            self.Role.INTERVIEWER,
        )

    def __str__(self):
        return f"{self.full_name} <{self.email}>"


# =========================================================
# CANDIDATE PROFILE
# =========================================================

class CandidateProfile(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="candidate_profile"
    )

    location = models.CharField(
        max_length=200,
        blank=True
    )

    headline = models.CharField(
        max_length=200,
        blank=True
    )

    education = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"degree": "", "institution": "", "year": ""}]'
    )

    experience_years = models.FloatField(
        default=0
    )

    experience = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"title": "", "company": "", "from": "", "to": ""}]'
    )

    skills = models.JSONField(
        default=list,
        blank=True
    )

    certifications = models.JSONField(
        default=list,
        blank=True
    )

    is_public = models.BooleanField(
        default=False,
        help_text="Allow anyone with the portfolio link to view this profile.",
    )

    github = models.URLField(
        blank=True
    )

    linkedin = models.URLField(
        blank=True
    )

    portfolio = models.URLField(
        blank=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"Profile of {self.user.email}"


class CandidateProject(models.Model):
    profile = models.ForeignKey(
        CandidateProfile,
        on_delete=models.CASCADE,
        related_name="candidate_projects",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    technologies = models.JSONField(default=list, blank=True)
    github_url = models.URLField(blank=True)
    live_demo_url = models.URLField(blank=True)
    image = models.ImageField(
        upload_to="candidate_projects/",
        blank=True,
        null=True,
    )
    featured = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "display_order", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile"],
                condition=models.Q(featured=True),
                name="unique_featured_candidate_project",
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.profile.user.email})"


# =========================================================
# AUDIT LOG
# =========================================================

class AuditLog(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs"
    )

    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs"
    )

    action = models.CharField(
        max_length=100
    )

    entity = models.CharField(
        max_length=100,
        blank=True
    )

    entity_id = models.CharField(
        max_length=50,
        blank=True
    )

    meta = models.JSONField(
        default=dict,
        blank=True
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.entity}:{self.entity_id}"