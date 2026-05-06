from django.contrib import admin

from .models import Conversation, Message, MessageAttachment


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    readonly_fields = ("kind", "name", "size_bytes", "content_type", "file")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "last_message_at", "created_at")
    search_fields = ("id", "participants__email", "participants__name")
    filter_horizontal = ("participants",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "read_at", "created_at")
    search_fields = ("body", "sender__email")
    autocomplete_fields = ("sender", "conversation")
    readonly_fields = ("created_at", "updated_at")
    inlines = [MessageAttachmentInline]


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "kind", "name", "size_bytes")
    list_filter = ("kind",)
