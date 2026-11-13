
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views


urlpatterns = [
    # ============================================================
    # AUTHENTICATION
    # ============================================================

    path(
        "auth/register/candidate/",
        views.CandidateRegisterView.as_view(),
        name="register-candidate",
    ),

    path(
        "auth/register/company/",
        views.CompanyRegisterView.as_view(),
        name="register-company",
    ),

    path(
        "auth/login/",
        views.LoginView.as_view(),
        name="login",
    ),

    path(
        "auth/refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),

    path(
        "auth/logout/",
        views.LogoutView.as_view(),
        name="logout",
    ),

    path(
        "auth/me/",
        views.MeView.as_view(),
        name="me",
    ),

    path(
        "auth/change-password/",
        views.ChangePasswordView.as_view(),
        name="change-password",
    ),

    # ============================================================
    # CANDIDATE PROFILE
    # ============================================================

    # GET    /api/candidate-profile/
    # PUT    /api/candidate-profile/
    # PATCH  /api/candidate-profile/
    path(
        "candidate-profile/",
        views.CandidateProfileView.as_view(),
        name="candidate-profile",
    ),
    path(
        "candidate-projects/",
        views.CandidateProjectListView.as_view(),
        name="candidate-project-list",
    ),
    path(
        "candidate-projects/<int:pk>/",
        views.CandidateProjectDetailView.as_view(),
        name="candidate-project-detail",
    ),
    path(
        "public/candidates/<uuid:pk>/",
        views.PublicCandidateProfileView.as_view(),
        name="public-candidate-profile",
    ),

    # ============================================================
    # COMPANIES
    # ============================================================

    path(
        "companies/",
        views.CompanyListView.as_view(),
        name="company-list",
    ),

    path(
        "companies/create/",
        views.CompanyCreateView.as_view(),
        name="company-create",
    ),

    # Static route before the UUID route
    path(
        "companies/me/",
        views.MyCompanyView.as_view(),
        name="my-company",
    ),

    path(
        "companies/<uuid:pk>/",
        views.CompanyDetailView.as_view(),
        name="company-detail",
    ),

    # ============================================================
    # STAFF
    # ============================================================

    path(
        "staff/",
        views.StaffListView.as_view(),
        name="staff-list",
    ),

    path(
        "staff/create/",
        views.StaffCreateView.as_view(),
        name="staff-create",
    ),

    path(
        "staff/<uuid:pk>/",
        views.StaffDetailView.as_view(),
        name="staff-detail",
    ),

    # ============================================================
    # SUPER ADMIN - USERS
    # ============================================================

    path(
        "admin/users/",
        views.AdminUserListView.as_view(),
        name="admin-user-list",
    ),

    path(
        "admin/users/<uuid:pk>/activate/",
        views.AdminUserActivateView.as_view(),
        name="admin-user-activate",
    ),

    path(
        "admin/users/<uuid:pk>/deactivate/",
        views.AdminUserDeactivateView.as_view(),
        name="admin-user-deactivate",
    ),

    path(
        "admin/users/<uuid:pk>/",
        views.AdminUserDetailView.as_view(),
        name="admin-user-detail",
    ),

    # ============================================================
    # AUDIT LOGS
    # ============================================================

    path(
        "audit-logs/",
        views.AuditLogListView.as_view(),
        name="audit-log-list",
    ),

    path(
        "audit-logs/<uuid:pk>/",
        views.AuditLogDetailView.as_view(),
        name="audit-log-detail",
    ),
]
