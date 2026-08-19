from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Prefetch, Q, QuerySet

from . import exceptions as exc
from .models import AvailDate, AvailEntry, AvailList, AvailShare, Visibility

User = get_user_model()


class AvailListService:
    """Avail list lifecycle and access control."""

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _can_view(user, avail_list: AvailList) -> bool:
        """Check if a user is allowed to view a list."""
        if avail_list.owner_id == user.id:
            return True
        if avail_list.visibility == Visibility.PUBLIC:
            return True
        # Private -- only if explicitly shared.
        return AvailShare.objects.filter(
            avail_list=avail_list, shared_with=user
        ).exists()

    @staticmethod
    def _assert_owner(user, avail_list: AvailList) -> None:
        if avail_list.owner_id != user.id:
            raise exc.NotAvailListOwner()

    @staticmethod
    def _base_qs() -> QuerySet[AvailList]:
        return AvailList.objects.select_related("owner").annotate(
            _entry_count=Count("entries")
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def create(*, owner, name: str, description: str = "", visibility: str = Visibility.PRIVATE) -> AvailList:
        avail_list = AvailList.objects.create(
            owner=owner,
            name=name,
            description=description,
            visibility=visibility,
        )
        return avail_list

    @staticmethod
    def list_owned(user, search: str | None = None) -> QuerySet[AvailList]:
        """Lists the user owns."""
        qs = AvailListService._base_qs().filter(owner=user).order_by("-created_at")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @staticmethod
    def list_shared_with(user, search: str | None = None) -> QuerySet[AvailList]:
        """Lists shared with the user by someone else."""
        qs = (
            AvailListService._base_qs()
            .filter(shares__shared_with=user)
            .exclude(owner=user)
            .distinct()
            .order_by("-updated_at")
        )
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @staticmethod
    def list_sent(user, search: str | None = None) -> QuerySet[AvailList]:
        """Lists the user has shared out (owns + has share records)."""
        qs = (
            AvailListService._base_qs()
            .filter(owner=user, shares__isnull=False)
            .distinct()
            .order_by("-updated_at")
        )
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @staticmethod
    def list_public(search: str | None = None) -> QuerySet[AvailList]:
        """All public lists."""
        qs = (
            AvailListService._base_qs()
            .filter(visibility=Visibility.PUBLIC)
            .order_by("-created_at")
        )
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @staticmethod
    def get(user, list_id: int) -> AvailList:
        """Fetch a list with access check."""
        try:
            avail_list = AvailListService._base_qs().get(pk=list_id)
        except AvailList.DoesNotExist:
            raise exc.AvailListNotFound()

        if not AvailListService._can_view(user, avail_list):
            raise exc.AvailListAccessDenied()
        return avail_list

    @staticmethod
    def get_with_entries(user, list_id: int) -> AvailList:
        """Fetch a list with all entries and their dates prefetched."""
        try:
            avail_list = (
                AvailList.objects.select_related("owner")
                .prefetch_related(
                    Prefetch(
                        "entries",
                        queryset=AvailEntry.objects.select_related("artist")
                        .prefetch_related("dates")
                        .order_by("position", "created_at"),
                    )
                )
                .annotate(_entry_count=Count("entries"))
                .get(pk=list_id)
            )
        except AvailList.DoesNotExist:
            raise exc.AvailListNotFound()

        if not AvailListService._can_view(user, avail_list):
            raise exc.AvailListAccessDenied()
        return avail_list

    @staticmethod
    def update(user, list_id: int, **fields) -> AvailList:
        """Update list fields. Owner only."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        allowed = {"name", "description", "visibility"}
        update_fields = []
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(avail_list, key, value)
                update_fields.append(key)

        if update_fields:
            update_fields.append("updated_at")
            avail_list.save(update_fields=update_fields)
        return avail_list

    @staticmethod
    def delete(user, list_id: int) -> None:
        """Delete a list. Owner only."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)
        avail_list.delete()


class AvailEntryService:
    """Managing artists inside an avail list."""

    @staticmethod
    @transaction.atomic
    def add_entry(
        *,
        user,
        list_id: int,
        artist_id: int,
        genre: str = "",
        location: str = "",
        note: str = "",
        dates: list | None = None,
    ) -> AvailEntry:
        """Add an artist to a list with optional dates."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        try:
            artist = User.objects.get(pk=artist_id, is_active=True)
        except User.DoesNotExist:
            raise exc.AvailEntryNotFound(detail="No active user with that id.")

        # Auto-assign position at the end.
        max_pos = avail_list.entries.aggregate(
            max_pos=models.Max("position")
        )["max_pos"]
        next_pos = (max_pos or 0) + 1

        try:
            entry = AvailEntry.objects.create(
                avail_list=avail_list,
                artist=artist,
                genre=genre,
                location=location,
                note=note,
                position=next_pos,
            )
        except IntegrityError:
            raise exc.DuplicateAvailEntry()

        if dates:
            AvailDate.objects.bulk_create(
                [AvailDate(entry=entry, date=d) for d in set(dates)],
                ignore_conflicts=True,
            )

        return entry

    @staticmethod
    def remove_entry(*, user, list_id: int, entry_id: int) -> None:
        """Remove an artist from a list. Owner only."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        deleted, _ = AvailEntry.objects.filter(
            pk=entry_id, avail_list=avail_list
        ).delete()
        if not deleted:
            raise exc.AvailEntryNotFound()

    @staticmethod
    def update_entry(*, user, list_id: int, entry_id: int, **fields) -> AvailEntry:
        """Update an entry's display fields. Owner only."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        try:
            entry = AvailEntry.objects.select_related("artist").get(
                pk=entry_id, avail_list=avail_list
            )
        except AvailEntry.DoesNotExist:
            raise exc.AvailEntryNotFound()

        allowed = {"genre", "location", "note", "position"}
        update_fields = []
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(entry, key, value)
                update_fields.append(key)

        if update_fields:
            update_fields.append("updated_at")
            entry.save(update_fields=update_fields)
        return entry

    @staticmethod
    @transaction.atomic
    def update_dates(*, user, list_id: int, entry_id: int, dates: list) -> AvailEntry:
        """Bulk-replace all dates for an entry."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        try:
            entry = AvailEntry.objects.get(pk=entry_id, avail_list=avail_list)
        except AvailEntry.DoesNotExist:
            raise exc.AvailEntryNotFound()

        # Delete all existing, then bulk-create the new set.
        entry.dates.all().delete()
        if dates:
            AvailDate.objects.bulk_create(
                [AvailDate(entry=entry, date=d) for d in set(dates)],
                ignore_conflicts=True,
            )
        return entry

    @staticmethod
    def list_entries(
        user, list_id: int, search: str | None = None
    ) -> QuerySet[AvailEntry]:
        """Entries in a list (with access check on the list)."""
        avail_list = AvailListService.get(user, list_id)

        qs = (
            AvailEntry.objects.filter(avail_list=avail_list)
            .select_related("artist")
            .prefetch_related("dates")
            .order_by("position", "created_at")
        )
        if search:
            qs = qs.filter(
                Q(artist__name__icontains=search) | Q(genre__icontains=search)
            )
        return qs


class AvailShareService:
    """Sharing avail lists with other users."""

    @staticmethod
    def share(
        *,
        user,
        list_id: int,
        shared_with_id: int | None = None,
        email: str | None = None,
        message: str = "",
    ) -> AvailShare:
        """Share a list. Owner only."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        shared_with = None
        shared_email = ""

        if shared_with_id:
            try:
                shared_with = User.objects.get(pk=shared_with_id, is_active=True)
            except User.DoesNotExist:
                raise exc.AvailShareNotFound(detail="No active user with that id.")
        elif email:
            shared_email = email.lower().strip()
            # Try to resolve email to a platform user.
            shared_with = User.objects.filter(
                email__iexact=shared_email, is_active=True
            ).first()

        try:
            share = AvailShare.objects.create(
                avail_list=avail_list,
                shared_by=user,
                shared_with=shared_with,
                shared_email=shared_email,
                message=message,
            )
        except IntegrityError:
            raise exc.DuplicateAvailShare()
        return share

    @staticmethod
    def unshare(*, user, list_id: int, share_id: int) -> None:
        """Remove a share. Owner only."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        deleted, _ = AvailShare.objects.filter(
            pk=share_id, avail_list=avail_list
        ).delete()
        if not deleted:
            raise exc.AvailShareNotFound()

    @staticmethod
    def list_shares(user, list_id: int) -> QuerySet[AvailShare]:
        """All share records for a list. Owner only."""
        avail_list = AvailListService.get(user, list_id)
        AvailListService._assert_owner(user, avail_list)

        return (
            AvailShare.objects.filter(avail_list=avail_list)
            .select_related("shared_by", "shared_with")
            .order_by("-created_at")
        )
