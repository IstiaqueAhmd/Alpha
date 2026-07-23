from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsSuperUserOrReadOnly(BasePermission):
    message = "Superuser privileges are required to modify blog posts."

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
