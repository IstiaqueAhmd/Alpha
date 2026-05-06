from django.conf import settings
from django.core.mail import send_mail

from .models import EmailOTP


def send_otp_email(*, email: str, otp: str, purpose: str) -> None:
    minutes = int(settings.OTP_TTL.total_seconds() // 60)

    if purpose == EmailOTP.Purpose.EMAIL_VERIFICATION:
        subject = "Verify your GetAvails account"
        body = (
            "Welcome to GetAvails!\n\n"
            f"Your 6-digit verification code is:\n\n    {otp}\n\n"
            f"This code expires in {minutes} minutes."
        )
    else:
        subject = "Your GetAvails password reset code"
        body = (
            "Use this 6-digit verification code to reset your password:\n\n"
            f"    {otp}\n\n"
            f"This code expires in {minutes} minutes. "
            "If you didn't request this, you can safely ignore this email."
        )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
