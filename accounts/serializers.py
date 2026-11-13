from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from urllib.parse import urlparse

from rest_framework import serializers

from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
)

from .models import (
    AuditLog,
    CandidateProject,
    CandidateProfile,
    Company,
    User,
)


# ================================================================
# COMPANY
# ================================================================

class CompanySerializer(serializers.ModelSerializer):

    members_count = serializers.IntegerField(
        source="members.count",
        read_only=True
    )

    class Meta:

        model = Company

        fields = [
            "id",
            "name",
            "industry",
            "email",
            "website",
            "location",
            "size",
            "description",
            "logo",
            "is_active",
            "members_count",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "members_count",
        ]


# ================================================================
# USER
# ================================================================

class UserSerializer(serializers.ModelSerializer):

    full_name = serializers.CharField(
        read_only=True
    )

    company_name = serializers.CharField(
        source="company.name",
        read_only=True,
        default=None,
    )

    class Meta:

        model = User

        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "designation",
            "company",
            "company_name",
            "avatar",
            "is_active",
            "date_joined",
        ]

        read_only_fields = [
            "id",
            "role",
            "company",
            "date_joined",
        ]


# ================================================================
# ADMIN USER
# ================================================================

class AdminUserSerializer(UserSerializer):

    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
    )

    class Meta(UserSerializer.Meta):

        fields = (
            UserSerializer.Meta.fields
            + ["password"]
        )

        read_only_fields = [
            "id",
            "date_joined",
        ]

    def create(self, validated_data):

        password = validated_data.pop(
            "password",
            None
        )

        user = User.objects.create_user(
            password=password,
            **validated_data
        )

        return user

    def update(self, instance, validated_data):

        password = validated_data.pop(
            "password",
            None
        )

        instance = super().update(
            instance,
            validated_data
        )

        if password:

            instance.set_password(
                password
            )

            instance.save(
                update_fields=["password"]
            )

        return instance


# ================================================================
# CANDIDATE REGISTRATION
# ================================================================

class CandidateRegisterSerializer(
    serializers.Serializer
):

    email = serializers.EmailField()

    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    first_name = serializers.CharField(
        max_length=150
    )

    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
    )

    phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
    )

    def validate_email(self, value):

        value = value.lower()

        if User.objects.filter(
            email__iexact=value
        ).exists():

            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        return value

    @transaction.atomic
    def create(self, validated_data):

        user = User.objects.create_user(
            role=User.Role.CANDIDATE,
            **validated_data
        )

        CandidateProfile.objects.create(
            user=user
        )

        return user


# ================================================================
# COMPANY REGISTRATION
# ================================================================

class CompanyRegisterSerializer(
    serializers.Serializer
):

    # ------------------------------
    # COMPANY
    # ------------------------------

    company_name = serializers.CharField(
        max_length=200
    )

    industry = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
    )

    company_email = serializers.EmailField()

    website = serializers.URLField(
        required=False,
        allow_blank=True,
    )

    location = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
    )

    size = serializers.ChoiceField(
        choices=Company.Size.choices,
        required=False,
        allow_blank=True,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    # ------------------------------
    # ADMIN
    # ------------------------------

    first_name = serializers.CharField(
        max_length=150
    )

    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
    )

    email = serializers.EmailField()

    phone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
    )

    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    def validate_company_name(self, value):

        if Company.objects.filter(
            name__iexact=value
        ).exists():

            raise serializers.ValidationError(
                "A company with this name already exists."
            )

        return value

    def validate_email(self, value):

        value = value.lower()

        if User.objects.filter(
            email__iexact=value
        ).exists():

            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        return value

    @transaction.atomic
    def create(self, validated_data):

        company = Company.objects.create(
            name=validated_data["company_name"],
            email=validated_data["company_email"],
            industry=validated_data.get(
                "industry",
                ""
            ),
            website=validated_data.get(
                "website",
                ""
            ),
            location=validated_data.get(
                "location",
                ""
            ),
            size=validated_data.get(
                "size",
                ""
            ),
            description=validated_data.get(
                "description",
                ""
            ),
        )

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data.get(
                "last_name",
                ""
            ),
            phone=validated_data.get(
                "phone",
                ""
            ),
            role=User.Role.COMPANY_ADMIN,
            designation="Company Admin",
            company=company,
        )

        return user


# ================================================================
# STAFF
# ================================================================

class StaffCreateSerializer(
    serializers.ModelSerializer
):

    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
    )

    role = serializers.ChoiceField(
        choices=[
            (
                User.Role.HR,
                "HR"
            ),
            (
                User.Role.INTERVIEWER,
                "Interviewer"
            ),
            (
                User.Role.COMPANY_ADMIN,
                "Company Admin"
            ),
        ]
    )

    class Meta:

        model = User

        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "phone",
            "role",
            "designation",
            "is_active",
        ]

        read_only_fields = [
            "id",
        ]

    def validate_email(self, value):

        value = value.lower()

        queryset = User.objects.filter(
            email__iexact=value
        )

        if self.instance:

            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        if queryset.exists():

            raise serializers.ValidationError(
                "A user with this email already exists."
            )

        return value

    def create(self, validated_data):

        password = validated_data.pop(
            "password",
            None
        )

        company = self.context.get(
            "company"
        )

        if company is None:

            raise serializers.ValidationError(
                "Company is required."
            )

        user = User.objects.create_user(
            password=password,
            company=company,
            **validated_data
        )

        return user

    def update(self, instance, validated_data):

        password = validated_data.pop(
            "password",
            None
        )

        instance = super().update(
            instance,
            validated_data
        )

        if password:

            instance.set_password(
                password
            )

            instance.save(
                update_fields=["password"]
            )

        return instance


# ================================================================
# CANDIDATE PROFILE
# ================================================================

class CandidateProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateProject
        fields = [
            "id",
            "title",
            "description",
            "technologies",
            "github_url",
            "live_demo_url",
            "image",
            "featured",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_github_url(self, value):
        if value:
            hostname = (urlparse(value).hostname or "").lower()
            if hostname != "github.com" and not hostname.endswith(".github.com"):
                raise serializers.ValidationError("Enter a GitHub repository URL.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        profile = validated_data["profile"]
        if validated_data.get("featured"):
            profile.candidate_projects.update(featured=False)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        if validated_data.get("featured", instance.featured):
            instance.profile.candidate_projects.exclude(pk=instance.pk).update(featured=False)
        return super().update(instance, validated_data)


class CandidateProfileSerializer(
    serializers.ModelSerializer
):

    user = UserSerializer(
        read_only=True
    )
    projects = CandidateProjectSerializer(
        source="candidate_projects",
        many=True,
        read_only=True,
    )

    class Meta:

        model = CandidateProfile

        fields = [
            "id",
            "user",
            "location",
            "headline",
            "education",
            "experience_years",
            "experience",
            "skills",
            "projects",
            "certifications",
            "is_public",
            "github",
            "linkedin",
            "portfolio",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "updated_at",
        ]

    def validate_github(self, value):
        if value:
            hostname = (urlparse(value).hostname or "").lower()
            if hostname != "github.com" and not hostname.endswith(".github.com"):
                raise serializers.ValidationError("Enter a GitHub profile URL.")
        return value

    def validate_linkedin(self, value):
        if value:
            hostname = (urlparse(value).hostname or "").lower()
            if hostname != "linkedin.com" and not hostname.endswith(".linkedin.com"):
                raise serializers.ValidationError("Enter a LinkedIn profile URL.")
        return value


class PublicCandidateProfileSerializer(serializers.ModelSerializer):
    candidate_name = serializers.SerializerMethodField()
    projects = CandidateProjectSerializer(
        source="candidate_projects",
        many=True,
        read_only=True,
    )

    class Meta:
        model = CandidateProfile
        fields = [
            "candidate_name",
            "location",
            "headline",
            "education",
            "experience_years",
            "experience",
            "skills",
            "projects",
            "certifications",
            "github",
            "linkedin",
            "portfolio",
        ]

    def get_candidate_name(self, obj):
        return obj.user.full_name


# ================================================================
# CHANGE PASSWORD
# ================================================================

class ChangePasswordSerializer(
    serializers.Serializer
):

    old_password = serializers.CharField(
        write_only=True
    )

    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )

    def validate_old_password(self, value):

        request = self.context.get(
            "request"
        )

        if not request:

            raise serializers.ValidationError(
                "Request context is required."
            )

        if not request.user.check_password(
            value
        ):

            raise serializers.ValidationError(
                "Old password is incorrect."
            )

        return value


# ================================================================
# LOGIN / JWT
# ================================================================

class EmailTokenSerializer(
    TokenObtainPairSerializer
):
    """
    Login using email and password.

    Response contains only:

    user:
        id
        name

    JWT contains:

    role
    company_id
    email
    """

    @classmethod
    def get_token(cls, user):

        token = super().get_token(
            user
        )

        token["role"] = user.role

        token["company_id"] = (
            str(user.company_id)
            if user.company_id
            else None
        )

        token["email"] = user.email

        return token

    def validate(self, attrs):

        data = super().validate(
            attrs
        )

        data["user"] = UserSerializer(self.user).data

        return data


# ================================================================
# AUDIT LOG
# ================================================================

class AuditLogSerializer(
    serializers.ModelSerializer
):

    user_email = serializers.CharField(
        source="user.email",
        read_only=True,
        default=None,
    )

    class Meta:

        model = AuditLog

        fields = [
            "id",
            "user",
            "user_email",
            "company",
            "action",
            "entity",
            "entity_id",
            "meta",
            "ip_address",
            "created_at",
        ]