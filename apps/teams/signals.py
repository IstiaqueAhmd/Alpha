"""Auto-enroll a newly verified user into invitations awaiting their email.

This is the referral path. Someone is invited by email before they have an
account; they sign up through the normal accounts flow; the moment they verify
that email, any approved invitation addressed to it becomes a membership.

Deliberately a signal rather than a call inside the accounts app: it keeps the
teams feature self-contained and leaves the live auth flow untouched. The
receiver is defensive - it guards cheaply, defers work to after commit, and
swallows its own errors so it can never break a signup.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import InvitationService

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="teams_auto_enroll")
def auto_enroll_on_email_verification(sender, instance, created, update_fields=None, **kwargs):
    # This fires on every User save. Bail cheaply on the common cases before
    # touching the database.
    #
    # The last-seen middleware uses queryset .update(), which does not emit
    # post_save, so ordinary requests never reach here.
    if not instance.is_email_verified:
        return

    # Run only at the verification moment: a save that explicitly wrote
    # email_verified_at (OTP verify, Google link), or a create that arrived
    # already verified (Google sign-up). A normal save on an already-verified
    # user - profile edit, password change - names other fields and is skipped,
    # so existing members are not re-scanned on every save.
    touched_verification = update_fields is None or "email_verified_at" in update_fields
    if not (created or touched_verification):
        return

    user_pk = instance.pk

    def _claim():
        try:
            InvitationService.claim_all_for_user(instance)
        except Exception:  # pragma: no cover - defensive; claim is best-effort
            logger.exception("Team auto-enroll failed for user %s", user_pk)

    # After commit: the user row is durable, and a claim failure cannot roll
    # back the verification that triggered it.
    transaction.on_commit(_claim)
