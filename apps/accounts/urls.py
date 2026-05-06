from django.urls import path

from .views import (
    ChangePasswordView,
    GoogleAuthView,
    LoginView,
    LogoutView,
    MeView,
    NotificationPreferencesView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    RegisterVerifyView,
    RegisterView,
    ResendVerificationView,
    TokenRefreshView,
)

app_name = "accounts"

urlpatterns = [
    # Registration
    path("register/", RegisterView.as_view(), name="register"),
    path("register/verify/", RegisterVerifyView.as_view(), name="register-verify"),
    path("register/resend/", ResendVerificationView.as_view(), name="register-resend"),

    # Login
    path("login/", LoginView.as_view(), name="login"),
    path("google/", GoogleAuthView.as_view(), name="google-auth"),

    # Tokens
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("me/notifications/", NotificationPreferencesView.as_view(), name="notification-preferences"),

    # Password reset
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/verify/", PasswordResetVerifyView.as_view(), name="password-reset-verify"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
