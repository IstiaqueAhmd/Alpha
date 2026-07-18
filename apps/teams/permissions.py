from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
    message = "Superuser privileges are required to review team requests."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
