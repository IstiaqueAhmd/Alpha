from django.contrib.auth import get_user_model

from apps.notifications.services import NotificationService

User = get_user_model()


def notify_share_received(*, share) -> None:
    """In-app notification for an invitee who already has a platform account."""
    if not share.shared_with:
        return

    avail_list = share.avail_list
    NotificationService.notify(
        recipient=share.shared_with,
        notification_type="avail.share_received",
        title=f"A list has been shared with you",
        message=f"{share.shared_by.name} shared the list '{avail_list.name}' with you.",
        data={
            "share_id": share.id,
            "list_id": avail_list.id,
            "list_name": avail_list.name,
            "shared_by": share.shared_by.name,
        },
    )
