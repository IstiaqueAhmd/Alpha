from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from apps.notifications.services import NotificationService

from .models import Inquiry

User = get_user_model()


class InquiryService:
    @staticmethod
    def list_for(user: User, *, status: str | None = None) -> QuerySet[Inquiry]:
        qs = (
            Inquiry.objects
            .select_related("sender", "receiver")
            .filter(Q(sender=user) | Q(receiver=user))
        )
        if status:
            qs = qs.filter(status=status)
        return qs

    @staticmethod
    def create(*, sender: User, receiver_email: str, **fields) -> Inquiry:
        receiver = User.objects.filter(email__iexact=receiver_email, is_active=True).first()
        inquiry = Inquiry.objects.create(
            sender=sender,
            receiver_email=receiver_email,
            receiver=receiver,
            **fields,
        )

        if receiver is not None:
            NotificationService.notify(
                recipient=receiver,
                notification_type="inquiry.received",
                title=f"New inquiry from {sender.name or sender.email}",
                message=inquiry.event_title,
                data={"inquiry_id": inquiry.id, "inquiry_uid": inquiry.uid},
            )

        return inquiry
