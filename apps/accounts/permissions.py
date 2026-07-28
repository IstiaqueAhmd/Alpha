from rest_framework.permissions import SAFE_METHODS, BasePermission


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


class IsAdmin(BasePermission):
    """Allow only authenticated, active users with the admin role."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_admin)


class IsAdminOrReadOnly(IsAdmin):
    """Like ``IsAdmin``, but safe methods (GET/HEAD/OPTIONS) are always allowed."""

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return super().has_permission(request, view)
