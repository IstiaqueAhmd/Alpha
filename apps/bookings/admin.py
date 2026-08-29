from django.contrib import admin

from .models import Activity, AvailabilitySlot, BookingOffer


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "status", "note", "created_at")
    list_filter = ("status",)
    search_fields = ("user__email", "note")
    autocomplete_fields = ("user",)


@admin.register(BookingOffer)
class BookingOfferAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "target_user",
        "target_email",
        "requester",
        "event_date",
        "amount_cents",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = (
        "title",
        "target_user__email",
        "target_email",
        "requester__email",
        "venue_name",
    )
    autocomplete_fields = ("target_user", "requester")
    readonly_fields = ("created_at", "updated_at", "decided_at")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "verb", "summary", "created_at")
    list_filter = ("verb",)
    search_fields = ("user__email", "summary", "detail")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
