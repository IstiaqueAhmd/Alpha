from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from .models import User

_RESET_TOKEN_SALT = "accounts.password-reset"


class PasswordResetToken:
    """Short-lived signed token issued after a successful OTP verification.

    Embeds a fingerprint of the password hash so the token is automatically
    invalidated as soon as the password changes (mirrors Django's built-in
    PasswordResetTokenGenerator behavior).
    """

    @staticmethod
    def make(user: User) -> str:
        signer = TimestampSigner(salt=_RESET_TOKEN_SALT)
        return signer.sign(f"{user.pk}:{user.password[-12:]}")

    @staticmethod
    def verify(token: str, max_age_seconds: int = 600) -> User | None:
        signer = TimestampSigner(salt=_RESET_TOKEN_SALT)
        try:
            value = signer.unsign(token, max_age=max_age_seconds)
        except (BadSignature, SignatureExpired):
            return None
        try:
            user_id_str, fingerprint = value.split(":", 1)
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            return None

        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user and user.password[-12:] == fingerprint:
            return user
        return None
