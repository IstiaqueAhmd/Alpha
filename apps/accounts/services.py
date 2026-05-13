import hashlib
import logging
import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import (
    AuthenticationFailed,
    Throttled,
    ValidationError,
)
from rest_framework_simplejwt.tokens import OutstandingToken, RefreshToken

from .emails import send_otp_email
from .exceptions import (
    EmailNotVerified,
    GoogleAccountNotFound,
    GoogleConfigError,
)
from .models import EmailOTP, NotificationPreferences, User
from .tokens import PasswordResetToken

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# OTP                                                                         #
# --------------------------------------------------------------------------- #


class OTPService:
    """Issue, send, and verify single-use 6-digit email OTPs."""

    @classmethod
    def issue_and_send(cls, *, user: User, purpose: str, ip_address: str | None = None) -> str:
        latest = (
            EmailOTP.objects.filter(user=user, purpose=purpose)
            .order_by("-created_at")
            .first()
        )
        if latest and (timezone.now() - latest.created_at) < settings.OTP_RESEND_COOLDOWN:
            wait = int((latest.created_at + settings.OTP_RESEND_COOLDOWN - timezone.now()).total_seconds())
            raise Throttled(wait=max(wait, 1), detail="Please wait before requesting another code.")

        otp_plain = cls._generate()
        with transaction.atomic():
            EmailOTP.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
                used_at=timezone.now()
            )
            EmailOTP.objects.create(
                user=user,
                purpose=purpose,
                otp_hash=cls._hash(otp_plain),
                expires_at=timezone.now() + settings.OTP_TTL,
                ip_address=ip_address,
            )
        send_otp_email(email=user.email, otp=otp_plain, purpose=purpose)
        return otp_plain

    @classmethod
    def verify(cls, *, user: User, otp: str, purpose: str) -> EmailOTP:
        record = (
            EmailOTP.objects.filter(user=user, purpose=purpose, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if not record or not record.is_valid(settings.OTP_MAX_ATTEMPTS):
            raise ValidationError({"otp": "Invalid or expired code."})

        record.attempts += 1
        if cls._hash(otp) != record.otp_hash:
            record.save(update_fields=["attempts", "updated_at"])
            raise ValidationError({"otp": "Invalid or expired code."})

        record.used_at = timezone.now()
        record.save(update_fields=["attempts", "used_at", "updated_at"])
        return record

    @staticmethod
    def _generate() -> str:
        return f"{secrets.randbelow(10 ** 6):06d}"

    @staticmethod
    def _hash(otp: str) -> str:
        return hashlib.sha256(otp.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Authentication                                                              #
# --------------------------------------------------------------------------- #


class AuthService:
    @staticmethod
    def authenticate(email: str, password: str) -> User:
        user = User.objects.filter(email__iexact=email).first()
        if not user or not user.has_usable_password() or not user.check_password(password):
            raise AuthenticationFailed("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationFailed("Your account has been disabled.")
        if not user.is_email_verified:
            raise EmailNotVerified()
        return user

    @staticmethod
    def issue_tokens(user: User, *, remember_me: bool = False) -> dict:
        refresh = RefreshToken.for_user(user)
        if remember_me:
            refresh.set_exp(lifetime=settings.JWT_REMEMBER_ME_REFRESH_TTL)
            access = refresh.access_token
            return {"access": str(access), "refresh": str(refresh)}
        return {"access": str(refresh.access_token), "refresh": str(refresh)}

    @staticmethod
    def logout(refresh_token: str) -> None:
        try:
            RefreshToken(refresh_token).blacklist()
        except Exception as exc:
            logger.warning("Logout failed to blacklist token: %s", exc)
            raise ValidationError({"refresh": "Invalid refresh token."})


# --------------------------------------------------------------------------- #
# Registration / email verification                                           #
# --------------------------------------------------------------------------- #


class RegistrationService:
    @classmethod
    def register(
        cls,
        *,
        name: str,
        email: str,
        password: str,
        role: str,
        ip_address: str | None = None,
    ) -> tuple[User, str]:
        email_normalized = email.lower().strip()
        if User.objects.filter(email__iexact=email_normalized).exists():
            raise ValidationError({"email": "An account with this email already exists."})

        user = User.objects.create_user(
            email=email_normalized,
            password=password,
            name=name.strip(),
            role=role,
            is_active=True,
        )
        otp = OTPService.issue_and_send(
            user=user,
            purpose=EmailOTP.Purpose.EMAIL_VERIFICATION,
            ip_address=ip_address,
        )
        return user, otp

    @classmethod
    def verify_email(cls, *, email: str, otp: str) -> User:
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise ValidationError({"otp": "Invalid or expired code."})

        OTPService.verify(
            user=user,
            otp=otp,
            purpose=EmailOTP.Purpose.EMAIL_VERIFICATION,
        )
        user.mark_email_verified()
        return user

    @classmethod
    def resend_verification(cls, *, email: str, ip_address: str | None = None) -> None:
        user = User.objects.filter(email__iexact=email).first()
        if not user or user.is_email_verified:
            return
        OTPService.issue_and_send(
            user=user,
            purpose=EmailOTP.Purpose.EMAIL_VERIFICATION,
            ip_address=ip_address,
        )


# --------------------------------------------------------------------------- #
# Password reset                                                              #
# --------------------------------------------------------------------------- #


class PasswordResetService:
    @classmethod
    def request_reset(cls, *, email: str, ip_address: str | None = None) -> None:
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            logger.info("Password reset for non-existent or inactive email: %s", email)
            return
        OTPService.issue_and_send(
            user=user,
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
            ip_address=ip_address,
        )

    @classmethod
    def verify_otp(cls, *, email: str, otp: str) -> str:
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            raise ValidationError({"otp": "Invalid or expired code."})

        OTPService.verify(user=user, otp=otp, purpose=EmailOTP.Purpose.PASSWORD_RESET)
        return PasswordResetToken.make(user)

    @classmethod
    def confirm_reset(cls, *, reset_token: str, new_password: str) -> User:
        user = PasswordResetToken.verify(reset_token)
        if not user:
            raise ValidationError({"reset_token": "Reset token is invalid or expired."})

        validate_password(new_password, user)
        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=["password", "updated_at"])
            cls._blacklist_user_tokens(user)
        return user

    @staticmethod
    def _blacklist_user_tokens(user: User) -> None:
        for token in OutstandingToken.objects.filter(user=user):
            try:
                RefreshToken(token.token).blacklist()
            except Exception:
                continue


# --------------------------------------------------------------------------- #
# Google OAuth                                                                #
# --------------------------------------------------------------------------- #


class GoogleAuthService:
    """Verify a Google ID token and resolve it to an existing user.

    New accounts cannot be created via Google: per spec, an unrecognized Google
    identity is rejected with ACCOUNT_NOT_FOUND so the frontend can route to
    the Sign-Up page (where the user picks a role).
    """

    @classmethod
    def authenticate(cls, *, id_token_str: str) -> User:
        client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
        if not client_id:
            raise GoogleConfigError()

        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token as google_id_token
        except ImportError as exc:  # pragma: no cover
            logger.error("google-auth not installed: %s", exc)
            raise GoogleConfigError()

        try:
            payload = google_id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                client_id,
            )
        except ValueError as exc:
            logger.info("Google token verification failed: %s", exc)
            raise AuthenticationFailed("Invalid Google token.")

        if payload.get("aud") != client_id:
            raise AuthenticationFailed("Invalid Google token audience.")
        if not payload.get("email_verified"):
            raise AuthenticationFailed("Google account email is not verified.")

        google_sub = payload.get("sub")
        email = (payload.get("email") or "").lower().strip()
        if not google_sub or not email:
            raise AuthenticationFailed("Google token missing required claims.")

        user = User.objects.filter(google_sub=google_sub).first()
        if user is None:
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                raise GoogleAccountNotFound()
            user.google_sub = google_sub
            update_fields = ["google_sub", "updated_at"]
            if user.email_verified_at is None:
                user.email_verified_at = timezone.now()
                update_fields.append("email_verified_at")
            user.save(update_fields=update_fields)
        elif user.email_verified_at is None:
            user.mark_email_verified()

        if not user.is_active:
            raise AuthenticationFailed("Your account has been disabled.")
        return user


class ProfileService:
    @staticmethod
    def update_profile(user: User, **fields) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        user.save(update_fields=list(fields.keys()) + ["updated_at"])
        return user

    @staticmethod
    def change_password(user: User, *, current_password: str, new_password: str) -> None:
        if not user.check_password(current_password):
            raise ValidationError({"current_password": "Current password is incorrect."})
        validate_password(new_password, user)
        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=["password", "updated_at"])
            for token in OutstandingToken.objects.filter(user=user):
                try:
                    RefreshToken(token.token).blacklist()
                except Exception:
                    continue

    @staticmethod
    def get_notification_preferences(user: User) -> NotificationPreferences:
        prefs, _ = NotificationPreferences.objects.get_or_create(user=user)
        return prefs

    @staticmethod
    def update_notification_preferences(user: User, **fields) -> NotificationPreferences:
        prefs, _ = NotificationPreferences.objects.get_or_create(user=user)
        for key, value in fields.items():
            setattr(prefs, key, value)
        prefs.save(update_fields=list(fields.keys()) + ["updated_at"])
        return prefs
