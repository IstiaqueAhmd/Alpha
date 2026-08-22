from django.conf import settings
from django.core.mail import send_mail


def send_share_email(*, share) -> None:
    """Notify a user by email that an avail list has been shared with them."""
    list_id = share.avail_list_id
    list_name = share.avail_list.name
    sharer_name = share.shared_by.name
    
    # Target email could be from the linked user or the explicit shared_email
    target_email = share.shared_with.email if share.shared_with else share.shared_email
    
    if not target_email:
        return

    # Use the public viewing URL format
    view_url = f"{settings.FRONTEND_URL}/avails/public/{list_id}"
    
    subject = f"{sharer_name} shared an Avail List with you on GetAvails"
    
    message_part = f'\n\nMessage: "{share.message}"' if share.message else ""
    
    body = (
        f"{sharer_name} shared the list \"{list_name}\" with you.{message_part}\n\n"
        f"View the list here:\n\n    {view_url}\n\n"
    )

    # If it's a non-platform user, maybe add a hint to sign up
    if not share.shared_with:
        body += (
            f"If you don't have a GetAvails account yet, you can sign up with this email "
            f"address ({target_email}) to track all lists shared with you.\n\n"
        )

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[target_email],
        fail_silently=False,
    )
