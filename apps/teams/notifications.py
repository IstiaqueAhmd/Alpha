from django.contrib.auth import get_user_model

from apps.notifications.services import NotificationService

User = get_user_model()


def notify_invitation_received(*, invitation) -> None:
    """In-app notification for an invitee who already has a platform account.

    Mirrors apps.teams.emails.send_invitation_email in shape, but this one is
    skippable: someone invited by email who hasn't signed up yet has no user
    row to attach a Notification to, so they only get the email.
    """
    recipient = User.objects.filter(email__iexact=invitation.email, is_active=True).first()
    if recipient is None:
        return

    team = invitation.team
    NotificationService.notify(
        recipient=recipient,
        notification_type="team.invitation_received",
        title=f"You've been invited to join {team.name}",
        message=f"You've been invited to join {team.name} as {invitation.get_role_display()}.",
        data={
            "invitation_id": invitation.id,
            "team_id": team.id,
            "team_name": team.name,
            "role": invitation.role,
        },
    )
