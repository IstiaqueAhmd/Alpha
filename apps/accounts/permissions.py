from rest_framework.permissions import BasePermission


class IsActiveStaff(BasePermission):
    """Active users with staff/admin privileges."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
        )


class HasRole(BasePermission):
    """Allow only authenticated users whose role is in ``view.allowed_roles``."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        allowed = getattr(view, "allowed_roles", None)
        if not allowed:
            return True
        return user.role in allowed
