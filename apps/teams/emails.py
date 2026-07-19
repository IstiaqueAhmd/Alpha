from django.conf import settings
from django.core.mail import send_mail

from .roles import ROLE_CHOICES

_ROLE_LABELS = dict(ROLE_CHOICES)


def send_invitation_email(*, invitation) -> None:
    """Notify an invitee by email. Mirrors apps.accounts.emails.send_otp_email:
    plain send_mail, DEFAULT_FROM_EMAIL, console backend in dev.
    """
    accept_url = f"{settings.FRONTEND_URL}/teams-invitations-accept?token={invitation.token}"
    role_label = _ROLE_LABELS.get(invitation.role, invitation.role)
    inviter_name = invitation.invited_by.name

    subject = f"You've been invited to join {invitation.team.name} on GetAvails"
    body = (
        f"{inviter_name} invited you to join \"{invitation.team.name}\" "
        f"as {role_label}.\n\n"
        f"Accept the invitation:\n\n    {accept_url}\n\n"
        f"If you don't have a GetAvails account yet, sign up with this email "
        f"address ({invitation.email}) and you'll be added automatically once "
        f"you verify it.\n\n"
        f"This invitation expires on {invitation.expires_at:%Y-%m-%d %H:%M} UTC."
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        fail_silently=False,
    )
