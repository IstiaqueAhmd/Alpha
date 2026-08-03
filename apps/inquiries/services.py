from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.notifications.services import NotificationService

from .models import Inquiry

User = get_user_model()


class InquiryService:
    @staticmethod
    def list_for(user: User, *, status: str | None = None, email: str | None = None) -> QuerySet[Inquiry]:
        qs = (
            Inquiry.objects
            .select_related("sender", "receiver")
            .filter(Q(sender=user) | Q(receiver=user))
        )
        if status:
            qs = qs.filter(status=status)
        if email:
            qs = qs.filter(
                Q(receiver_email__icontains=email)
                | Q(email__icontains=email)
                | Q(sender__email__icontains=email)
                | Q(receiver__email__icontains=email)
            ).distinct()
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

    @staticmethod
    def get_for_viewer(viewer: User, inquiry_id: int) -> Inquiry:
        inquiry = (
            Inquiry.objects
            .select_related("sender", "receiver")
            .filter(pk=inquiry_id)
            .filter(Q(sender=viewer) | Q(receiver=viewer))
            .first()
        )
        if not inquiry:
            raise NotFound("Inquiry not found.")
        return inquiry

    @classmethod
    def respond(cls, *, viewer: User, inquiry_id: int, decision: str) -> Inquiry:
        inquiry = cls.get_for_viewer(viewer, inquiry_id)
        if inquiry.receiver_id != viewer.pk:
            raise PermissionDenied("Only the receiver can respond to this inquiry.")
        if inquiry.status != Inquiry.Status.PENDING:
            raise ValidationError("This inquiry has already been responded to.")

        inquiry.status = decision
        inquiry.save(update_fields=["status", "updated_at"])

        NotificationService.notify(
            recipient=inquiry.sender,
            notification_type=f"inquiry.{decision}",
            title=f"Your inquiry was {decision}",
            message=inquiry.event_title,
            data={"inquiry_id": inquiry.id, "inquiry_uid": inquiry.uid},
        )
        return inquiry
