import logging

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    ChangePasswordSerializer,
    GoogleAuthSerializer,
    LoginSerializer,
    LogoutSerializer,
    NotificationPreferencesSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetVerifySerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    RegisterVerifySerializer,
    ResendVerificationSerializer,
    TokenRefreshInputSerializer,
    UserSerializer,
)
from .services import (
    AuthService,
    GoogleAuthService,
    PasswordResetService,
    ProfileService,
    RegistrationService,
)
from .throttling import (
    GoogleAuthThrottle,
    LoginThrottle,
    OTPVerifyThrottle,
    PasswordResetThrottle,
    RegisterThrottle,
)

logger = logging.getLogger(__name__)


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# --------------------------------------------------------------------------- #
# Registration                                                                #
# --------------------------------------------------------------------------- #


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, otp = RegistrationService.register(
            **serializer.validated_data,
            ip_address=_client_ip(request),
        )
        return Response(
            {
                "success": True,
                "message": "Account created. Check your email for a 6-digit verification code.",
                "email": user.email
            },
            status=status.HTTP_201_CREATED,
        )


class RegisterVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle]

    def post(self, request):
        serializer = RegisterVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = RegistrationService.verify_email(**serializer.validated_data)
        tokens = AuthService.issue_tokens(user)
        return Response(
            {
                "success": True,
                "message": "Email verified.",
                "user": UserSerializer(user).data,
                **tokens,
            },
            status=status.HTTP_200_OK,
        )


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        RegistrationService.resend_verification(
            email=serializer.validated_data["email"],
            ip_address=_client_ip(request),
        )
        return Response(
            {"success": True, "message": "If the account exists and is unverified, a code has been sent."},
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------------------- #
# Login / token / logout / me                                                 #
# --------------------------------------------------------------------------- #


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = AuthService.authenticate(email=data["email"], password=data["password"])
        tokens = AuthService.issue_tokens(user, remember_me=data.get("remember_me", False))
        return Response(
            {"success": True, "user": UserSerializer(user).data, **tokens},
            status=status.HTTP_200_OK,
        )


class GoogleAuthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [GoogleAuthThrottle]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = GoogleAuthService.authenticate(id_token_str=serializer.validated_data["id_token"])
        tokens = AuthService.issue_tokens(user)
        return Response(
            {"success": True, "user": UserSerializer(user).data, **tokens},
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TokenRefreshInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refresh = RefreshToken(serializer.validated_data["refresh"])
            data = {"access": str(refresh.access_token)}
            if jwt_settings.ROTATE_REFRESH_TOKENS:
                if jwt_settings.BLACKLIST_AFTER_ROTATION:
                    try:
                        refresh.blacklist()
                    except AttributeError:
                        pass
                refresh.set_jti()
                refresh.set_exp()
                refresh.set_iat()
                data["refresh"] = str(refresh)
        except TokenError as exc:
            raise InvalidToken(str(exc))
        return Response({"success": True, **data}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.logout(serializer.validated_data["refresh"])
        return Response({"success": True}, status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"success": True, "user": UserSerializer(request.user).data},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = ProfileService.update_profile(request.user, **serializer.validated_data)
        return Response(
            {"success": True, "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ProfileService.change_password(
            request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response(
            {"success": True, "message": "Password updated. Please log in again."},
            status=status.HTTP_200_OK,
        )


class NotificationPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs = ProfileService.get_notification_preferences(request.user)
        return Response(
            {"success": True, "preferences": NotificationPreferencesSerializer(prefs).data},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        serializer = NotificationPreferencesSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prefs = ProfileService.update_notification_preferences(
            request.user, **serializer.validated_data
        )
        return Response(
            {"success": True, "preferences": NotificationPreferencesSerializer(prefs).data},
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------------------- #
# Password reset                                                              #
# --------------------------------------------------------------------------- #


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordResetService.request_reset(
            email=serializer.validated_data["email"],
            ip_address=_client_ip(request),
        )
        return Response(
            {
                "success": True,
                "message": "If that email exists, a verification code has been sent.",
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_token = PasswordResetService.verify_otp(**serializer.validated_data)
        return Response(
            {"success": True, "reset_token": reset_token},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordResetService.confirm_reset(
            reset_token=serializer.validated_data["reset_token"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response(
            {"success": True, "message": "Password reset successfully."},
            status=status.HTTP_200_OK,
        )
