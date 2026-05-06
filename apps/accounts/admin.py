from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import EmailOTP, NotificationPreferences, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "email",
        "name",
        "role",
        "is_staff",
        "is_active",
        "email_verified_at",
        "created_at",
    )
    list_filter = ("role", "is_staff", "is_active", "is_superuser")
    search_fields = ("email", "name")
    readonly_fields = ("created_at", "updated_at", "last_login", "last_seen_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "role", "image", "phone", "email_verified_at", "last_seen_at", "google_sub")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Audit", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "name", "role", "is_staff", "is_active"),
            },
        ),
    )


@admin.register(NotificationPreferences)
class NotificationPreferencesAdmin(admin.ModelAdmin):
    list_display = ("user", "new_booking_requests", "offer_responses", "email_delivery_updates", "updated_at")
    search_fields = ("user__email",)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "expires_at", "used_at", "attempts", "ip_address", "created_at")
    list_filter = ("purpose", "used_at")
    search_fields = ("user__email",)
    readonly_fields = (
        "user",
        "purpose",
        "otp_hash",
        "expires_at",
        "used_at",
        "attempts",
        "ip_address",
        "created_at",
        "updated_at",
    )
