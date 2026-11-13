from rest_framework.permissions import BasePermission

from .models import User

R = User.Role


class RolePermission(BasePermission):
    roles: tuple = ()

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_active and u.role in self.roles)


class IsSuperAdmin(RolePermission):
    roles = (R.SUPER_ADMIN,)


class IsCompanyAdmin(RolePermission):
    roles = (R.SUPER_ADMIN, R.COMPANY_ADMIN)


class IsHRStaff(RolePermission):
    """Super admin, company admin and HR/recruiters."""
    roles = (R.SUPER_ADMIN, R.COMPANY_ADMIN, R.HR)


class IsCompanyMember(RolePermission):
    """Any company-side user (admin, HR, interviewer) or super admin."""
    roles = (R.SUPER_ADMIN, R.COMPANY_ADMIN, R.HR, R.INTERVIEWER)


class IsCandidate(RolePermission):
    roles = (R.CANDIDATE,)
