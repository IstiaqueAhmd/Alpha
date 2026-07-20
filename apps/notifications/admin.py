from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient", "notification_type", "title", "read_at", "created_at")
    list_filter = ("notification_type",)
    search_fields = ("title", "message", "recipient__email")
    readonly_fields = ("created_at", "updated_at")
