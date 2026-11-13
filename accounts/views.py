from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    AuditLog,
    CandidateProject,
    CandidateProfile,
    Company,
    User,
)

from .permissions import (
    IsCandidate,
    IsCompanyAdmin,
    IsCompanyMember,
    IsSuperAdmin,
)

from .serializers import (
    AdminUserSerializer,
    AuditLogSerializer,
    CandidateProjectSerializer,
    CandidateProfileSerializer,
    CandidateRegisterSerializer,
    ChangePasswordSerializer,
    CompanyRegisterSerializer,
    CompanySerializer,
    EmailTokenSerializer,
    PublicCandidateProfileSerializer,
    StaffCreateSerializer,
    UserSerializer,
)

from .utils import log_action


# ================================================================
# TOKEN HELPER
# ================================================================

def tokens_for(user):
    """
    Generate JWT access and refresh tokens.

    Custom JWT claims:
    - role
    - company_id
    """

    refresh = RefreshToken.for_user(user)

    refresh["role"] = user.role

    refresh["company_id"] = (
        str(user.company_id)
        if user.company_id
        else None
    )

    refresh["email"] = user.email

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


# ================================================================
# AUTHENTICATION
# ================================================================

class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/

    Login using:
    - email
    - password

    Response:
    - refresh
    - access
    - user.id
    - user.name
    """

    serializer_class = EmailTokenSerializer
    throttle_scope = "auth"


class CandidateRegisterView(APIView):
    """
    POST /api/auth/register/candidate/

    Register a candidate.
    """

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):

        serializer = CandidateRegisterSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        log_action(
            request,
            "candidate.registered",
            "User",
            user.pk,
            user=user,
        )

        return Response(
            {
                "user": UserSerializer(user).data,
                **tokens_for(user),
            },
            status=status.HTTP_201_CREATED,
        )


class CompanyRegisterView(APIView):
    """
    POST /api/auth/register/company/

    Creates:
    - Company
    - Company Admin
    """

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):

        serializer = CompanyRegisterSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        log_action(
            request,
            "company.registered",
            "Company",
            user.company_id,
            user=user,
        )

        return Response(
            {
                "user": UserSerializer(user).data,
                "company": CompanySerializer(
                    user.company
                ).data,
                **tokens_for(user),
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    """
    POST /api/auth/logout/

    Blacklist refresh token.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):

        refresh_token = request.data.get(
            "refresh"
        )

        if not refresh_token:

            return Response(
                {
                    "detail": "Refresh token is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:

            token = RefreshToken(
                refresh_token
            )

            token.blacklist()

        except TokenError:

            return Response(
                {
                    "detail": "Invalid or expired token."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class MeView(APIView):
    """
    GET /api/auth/me/
    PATCH /api/auth/me/
    PUT /api/auth/me/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):

        return Response(
            UserSerializer(
                request.user
            ).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request):

        serializer = UserSerializer(
            request.user,
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request):

        serializer = UserSerializer(
            request.user,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = ChangePasswordSerializer(
            data=request.data,
            context={
                "request": request
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        request.user.set_password(
            serializer.validated_data[
                "new_password"
            ]
        )

        request.user.save(
            update_fields=["password"]
        )

        log_action(
            request,
            "password.changed",
            "User",
            request.user.pk,
            user=request.user,
        )

        return Response(
            {
                "detail": "Password updated successfully."
            },
            status=status.HTTP_200_OK,
        )


# ================================================================
# COMPANIES
# ================================================================

class CompanyListView(APIView):
    """
    GET /api/companies/

    Super Admin:
        All companies.

    Company member:
        Own company only.
    """

    permission_classes = [IsCompanyMember]

    def get(self, request):

        user = request.user

        queryset = Company.objects.all()

        if user.role != User.Role.SUPER_ADMIN:

            queryset = queryset.filter(
                pk=user.company_id
            )

        search = request.query_params.get(
            "search"
        )

        if search:

            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                industry__icontains=search
            ) | queryset.filter(
                location__icontains=search
            )

        is_active = request.query_params.get(
            "is_active"
        )

        if is_active is not None:

            queryset = queryset.filter(
                is_active=is_active
            )

        industry = request.query_params.get(
            "industry"
        )

        if industry:

            queryset = queryset.filter(
                industry__iexact=industry
            )

        ordering = request.query_params.get(
            "ordering"
        )

        allowed_ordering = [
            "name",
            "created_at",
            "updated_at",
        ]

        if ordering:

            field = ordering.lstrip("-")

            if field in allowed_ordering:

                queryset = queryset.order_by(
                    ordering
                )

        else:

            queryset = queryset.order_by(
                "name"
            )

        return Response(
            CompanySerializer(
                queryset,
                many=True
            ).data,
            status=status.HTTP_200_OK,
        )


class CompanyCreateView(APIView):
    """
    POST /api/companies/create/

    Super Admin only.
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request):

        serializer = CompanySerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        company = serializer.save()

        log_action(
            request,
            "company.created",
            "Company",
            company.pk,
            user=request.user,
            company=company,
        )

        return Response(
            CompanySerializer(company).data,
            status=status.HTTP_201_CREATED,
        )


class CompanyDetailView(APIView):
    """
    GET /api/companies/<uuid:pk>/
    PUT /api/companies/<uuid:pk>/
    PATCH /api/companies/<uuid:pk>/
    DELETE /api/companies/<uuid:pk>/
    """

    def get_permissions(self):

        if self.request.method == "GET":

            return [IsCompanyMember()]

        if self.request.method in [
            "PUT",
            "PATCH",
        ]:

            return [IsCompanyAdmin()]

        if self.request.method == "DELETE":

            return [IsSuperAdmin()]

        return [IsAuthenticated()]

    def get_company(self, request, pk):

        user = request.user

        if user.role == User.Role.SUPER_ADMIN:

            return get_object_or_404(
                Company,
                pk=pk
            )

        return get_object_or_404(
            Company,
            pk=pk,
            id=user.company_id,
        )

    def get(self, request, pk):

        company = self.get_company(
            request,
            pk
        )

        return Response(
            CompanySerializer(company).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):

        company = self.get_company(
            request,
            pk
        )

        serializer = CompanySerializer(
            company,
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True
        )

        company = serializer.save()

        log_action(
            request,
            "company.updated",
            "Company",
            company.pk,
            user=request.user,
            company=company,
        )

        return Response(
            CompanySerializer(company).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):

        company = self.get_company(
            request,
            pk
        )

        serializer = CompanySerializer(
            company,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(
            raise_exception=True
        )

        company = serializer.save()

        log_action(
            request,
            "company.updated",
            "Company",
            company.pk,
            user=request.user,
            company=company,
        )

        return Response(
            CompanySerializer(company).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):

        company = get_object_or_404(
            Company,
            pk=pk
        )

        company_id = company.pk

        company.delete()

        log_action(
            request,
            "company.deleted",
            "Company",
            company_id,
            user=request.user,
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class MyCompanyView(APIView):
    """
    GET /api/companies/me/
    """

    permission_classes = [IsCompanyMember]

    def get(self, request):

        company = request.user.company

        if not company:

            return Response(
                {
                    "detail": "You are not associated with a company."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            CompanySerializer(company).data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# STAFF
# ================================================================

class StaffListView(APIView):
    """
    GET /api/staff/
    """

    permission_classes = [IsCompanyAdmin]

    def get(self, request):

        user = request.user

        queryset = (
            User.objects
            .select_related("company")
            .exclude(
                role=User.Role.CANDIDATE
            )
            .exclude(
                role=User.Role.SUPER_ADMIN
            )
        )

        if user.role != User.Role.SUPER_ADMIN:

            queryset = queryset.filter(
                company_id=user.company_id
            )

        search = request.query_params.get(
            "search"
        )

        if search:

            queryset = queryset.filter(
                email__icontains=search
            ) | queryset.filter(
                first_name__icontains=search
            ) | queryset.filter(
                last_name__icontains=search
            ) | queryset.filter(
                designation__icontains=search
            )

        role = request.query_params.get(
            "role"
        )

        if role:

            queryset = queryset.filter(
                role=role
            )

        is_active = request.query_params.get(
            "is_active"
        )

        if is_active is not None:

            queryset = queryset.filter(
                is_active=is_active
            )

        ordering = request.query_params.get(
            "ordering"
        )

        allowed_ordering = [
            "date_joined",
            "email",
            "first_name",
        ]

        if ordering:

            field = ordering.lstrip("-")

            if field in allowed_ordering:

                queryset = queryset.order_by(
                    ordering
                )

        else:

            queryset = queryset.order_by(
                "-date_joined"
            )

        return Response(
            UserSerializer(
                queryset,
                many=True
            ).data,
            status=status.HTTP_200_OK,
        )


class StaffCreateView(APIView):
    """
    POST /api/staff/create/

    Company Admin creates:
    - HR
    - Interviewer
    - Company Admin
    """

    permission_classes = [IsCompanyAdmin]

    def post(self, request):

        serializer = StaffCreateSerializer(
            data=request.data,
            context={
                "request": request,
                "company": request.user.company,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        log_action(
            request,
            "staff.created",
            "User",
            user.pk,
            {
                "role": user.role,
            },
            user=request.user,
            company=user.company,
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class StaffDetailView(APIView):
    """
    GET /api/staff/<uuid:pk>/
    PUT /api/staff/<uuid:pk>/
    PATCH /api/staff/<uuid:pk>/
    DELETE /api/staff/<uuid:pk>/
    """

    permission_classes = [IsCompanyAdmin]

    def get_staff(self, request, pk):

        queryset = (
            User.objects
            .select_related("company")
            .exclude(
                role=User.Role.CANDIDATE
            )
            .exclude(
                role=User.Role.SUPER_ADMIN
            )
        )

        if request.user.role != User.Role.SUPER_ADMIN:

            queryset = queryset.filter(
                company_id=request.user.company_id
            )

        return get_object_or_404(
            queryset,
            pk=pk
        )

    def get(self, request, pk):

        user = self.get_staff(
            request,
            pk
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):

        user = self.get_staff(
            request,
            pk
        )

        serializer = StaffCreateSerializer(
            user,
            data=request.data,
            context={
                "request": request,
                "company": request.user.company,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        log_action(
            request,
            "staff.updated",
            "User",
            user.pk,
            {
                "role": user.role,
            },
            user=request.user,
            company=user.company,
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):

        user = self.get_staff(
            request,
            pk
        )

        serializer = StaffCreateSerializer(
            user,
            data=request.data,
            partial=True,
            context={
                "request": request,
                "company": request.user.company,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        log_action(
            request,
            "staff.updated",
            "User",
            user.pk,
            {
                "role": user.role,
            },
            user=request.user,
            company=user.company,
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):

        user = self.get_staff(
            request,
            pk
        )

        if user.pk == request.user.pk:

            return Response(
                {
                    "detail": "You cannot deactivate yourself."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False

        user.save(
            update_fields=["is_active"]
        )

        log_action(
            request,
            "staff.deactivated",
            "User",
            user.pk,
            user=request.user,
            company=user.company,
        )

        return Response(
            {
                "detail": "Staff account deactivated."
            },
            status=status.HTTP_200_OK,
        )


# ================================================================
# CANDIDATE PROFILE
# ================================================================

# ============================================================
# CANDIDATE PROFILE
# ============================================================

class CandidateProfileView(APIView):
    """
    GET   /api/candidate-profile/
    PUT   /api/candidate-profile/
    PATCH /api/candidate-profile/

    Candidates can view and update their own profile.
    """

    permission_classes = [IsCandidate]

    def get_profile(self, request):
        """
        Retrieve the authenticated candidate's profile.

        Create the profile if it does not exist.
        """
        profile, created = CandidateProfile.objects.get_or_create(
            user=request.user
        )

        return profile

    def get(self, request):
        profile = self.get_profile(request)

        serializer = CandidateProfileSerializer(profile)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        profile = self.get_profile(request)

        serializer = CandidateProfileSerializer(
            profile,
            data=request.data,
        )

        serializer.is_valid(raise_exception=True)

        profile = serializer.save()

        return Response(
            CandidateProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        profile = self.get_profile(request)

        serializer = CandidateProfileSerializer(
            profile,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(raise_exception=True)
        profile = serializer.save()

        return Response(
            CandidateProfileSerializer(profile).data,
            status=status.HTTP_200_OK,
        )


class CandidateProjectListView(APIView):
    permission_classes = [IsCandidate]

    def get(self, request):
        profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
        projects = profile.candidate_projects.all()
        return Response(
            CandidateProjectSerializer(projects, many=True, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
        serializer = CandidateProjectSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        project = serializer.save(profile=profile)
        return Response(
            CandidateProjectSerializer(project, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class CandidateProjectDetailView(APIView):
    permission_classes = [IsCandidate]

    def get_project(self, request, pk):
        return get_object_or_404(
            CandidateProject.objects.filter(profile__user=request.user),
            pk=pk,
        )

    def get(self, request, pk):
        project = self.get_project(request, pk)
        return Response(CandidateProjectSerializer(project, context={"request": request}).data)

    def put(self, request, pk):
        return self.update(request, pk, partial=False)

    def patch(self, request, pk):
        return self.update(request, pk, partial=True)

    def update(self, request, pk, partial):
        project = self.get_project(request, pk)
        serializer = CandidateProjectSerializer(
            project,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        return Response(CandidateProjectSerializer(project, context={"request": request}).data)

    def delete(self, request, pk):
        self.get_project(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublicCandidateProfileView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        profile = get_object_or_404(
            CandidateProfile.objects.select_related("user").prefetch_related("candidate_projects"),
            user_id=pk,
            is_public=True,
        )
        return Response(
            PublicCandidateProfileSerializer(profile, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# SUPER ADMIN - USERS
# ================================================================

class AdminUserListView(APIView):
    """
    GET /api/admin/users/
    POST /api/admin/users/
    """

    permission_classes = [IsSuperAdmin]

    def get(self, request):

        queryset = (
            User.objects
            .select_related("company")
            .all()
        )

        search = request.query_params.get(
            "search"
        )

        if search:

            queryset = queryset.filter(
                email__icontains=search
            ) | queryset.filter(
                first_name__icontains=search
            ) | queryset.filter(
                last_name__icontains=search
            )

        role = request.query_params.get(
            "role"
        )

        if role:

            queryset = queryset.filter(
                role=role
            )

        is_active = request.query_params.get(
            "is_active"
        )

        if is_active is not None:

            queryset = queryset.filter(
                is_active=is_active
            )

        company = request.query_params.get(
            "company"
        )

        if company:

            queryset = queryset.filter(
                company_id=company
            )

        ordering = request.query_params.get(
            "ordering"
        )

        allowed_ordering = [
            "date_joined",
            "email",
        ]

        if ordering:

            field = ordering.lstrip("-")

            if field in allowed_ordering:

                queryset = queryset.order_by(
                    ordering
                )

        else:

            queryset = queryset.order_by(
                "-date_joined"
            )

        return Response(
            UserSerializer(
                queryset,
                many=True
            ).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):

        serializer = AdminUserSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        log_action(
            request,
            "admin.user.created",
            "User",
            user.pk,
            user=request.user,
            company=user.company,
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class AdminUserDetailView(APIView):
    """
    GET /api/admin/users/<uuid:pk>/
    PUT /api/admin/users/<uuid:pk>/
    PATCH /api/admin/users/<uuid:pk>/
    DELETE /api/admin/users/<uuid:pk>/
    """

    permission_classes = [IsSuperAdmin]

    def get_user(self, pk):

        return get_object_or_404(
            User.objects.select_related(
                "company"
            ),
            pk=pk
        )

    def get(self, request, pk):

        user = self.get_user(pk)

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):

        user = self.get_user(pk)

        serializer = AdminUserSerializer(
            user,
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):

        user = self.get_user(pk)

        serializer = AdminUserSerializer(
            user,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):

        user = self.get_user(pk)

        if user.pk == request.user.pk:

            return Response(
                {
                    "detail": "You cannot deactivate yourself."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False

        user.save(
            update_fields=["is_active"]
        )

        log_action(
            request,
            "admin.user.deactivated",
            "User",
            user.pk,
            user=request.user,
            company=user.company,
        )

        return Response(
            {
                "detail": "User account deactivated."
            },
            status=status.HTTP_200_OK,
        )


class AdminUserActivateView(APIView):
    """
    POST /api/admin/users/<uuid:pk>/activate/
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):

        user = get_object_or_404(
            User,
            pk=pk
        )

        user.is_active = True

        user.save(
            update_fields=["is_active"]
        )

        log_action(
            request,
            "admin.user.activated",
            "User",
            user.pk,
            user=request.user,
            company=user.company,
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )


class AdminUserDeactivateView(APIView):
    """
    POST /api/admin/users/<uuid:pk>/deactivate/
    """

    permission_classes = [IsSuperAdmin]

    def post(self, request, pk):

        user = get_object_or_404(
            User,
            pk=pk
        )

        if user.pk == request.user.pk:

            return Response(
                {
                    "detail": "You cannot deactivate yourself."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False

        user.save(
            update_fields=["is_active"]
        )

        log_action(
            request,
            "admin.user.deactivated",
            "User",
            user.pk,
            user=request.user,
            company=user.company,
        )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK,
        )


# ================================================================
# AUDIT LOGS
# ================================================================

class AuditLogListView(APIView):
    """
    GET /api/audit-logs/
    """

    permission_classes = [IsCompanyAdmin]

    def get(self, request):

        user = request.user

        queryset = AuditLog.objects.select_related(
            "user",
            "company",
        )

        if user.role != User.Role.SUPER_ADMIN:

            queryset = queryset.filter(
                company_id=user.company_id
            )

        action = request.query_params.get(
            "action"
        )

        if action:

            queryset = queryset.filter(
                action=action
            )

        entity = request.query_params.get(
            "entity"
        )

        if entity:

            queryset = queryset.filter(
                entity=entity
            )

        audit_user = request.query_params.get(
            "user"
        )

        if audit_user:

            queryset = queryset.filter(
                user_id=audit_user
            )

        search = request.query_params.get(
            "search"
        )

        if search:

            queryset = queryset.filter(
                action__icontains=search
            ) | queryset.filter(
                entity__icontains=search
            ) | queryset.filter(
                user__email__icontains=search
            )

        ordering = request.query_params.get(
            "ordering"
        )

        allowed_ordering = [
            "created_at",
            "action",
            "entity",
        ]

        if ordering:

            field = ordering.lstrip("-")

            if field in allowed_ordering:

                queryset = queryset.order_by(
                    ordering
                )

        else:

            queryset = queryset.order_by(
                "-created_at"
            )

        return Response(
            AuditLogSerializer(
                queryset,
                many=True
            ).data,
            status=status.HTTP_200_OK,
        )


class AuditLogDetailView(APIView):
    """
    GET /api/audit-logs/<uuid:pk>/
    """

    permission_classes = [IsCompanyAdmin]

    def get(self, request, pk):

        queryset = AuditLog.objects.select_related(
            "user",
            "company",
        )

        if request.user.role != User.Role.SUPER_ADMIN:

            queryset = queryset.filter(
                company_id=request.user.company_id
            )

        audit_log = get_object_or_404(
            queryset,
            pk=pk
        )

        return Response(
            AuditLogSerializer(
                audit_log
            ).data,
            status=status.HTTP_200_OK,
        )