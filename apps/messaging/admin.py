from django.contrib import admin

from .models import Conversation, ConversationMember, Message, MessageAttachment


class ConversationMemberInline(admin.TabularInline):
    model = ConversationMember
    extra = 0
    autocomplete_fields = ("user",)


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    extra = 0
    readonly_fields = ("kind", "name", "size_bytes", "content_type", "file")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "is_group", "name", "last_message_at", "created_at")
    list_filter = ("is_group",)
    search_fields = ("id", "name", "memberships__user__email", "memberships__user__name")
    inlines = [ConversationMemberInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "is_edited", "is_deleted", "created_at")
    list_filter = ("is_edited", "is_deleted")
    search_fields = ("body", "sender__email")
    autocomplete_fields = ("sender", "conversation", "reply_to")
    readonly_fields = ("created_at", "updated_at")
    inlines = [MessageAttachmentInline]


@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "kind", "name", "size_bytes")
    list_filter = ("kind",)
