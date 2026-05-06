from django.urls import path

from .views import (
    ConversationDetailView,
    ConversationListCreateView,
    MarkConversationReadView,
    MessageListCreateView,
)

app_name = "messaging"

urlpatterns = [
    path("conversations/", ConversationListCreateView.as_view(), name="conversations"),
    path("conversations/<int:conversation_id>/", ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<int:conversation_id>/messages/", MessageListCreateView.as_view(), name="messages"),
    path("conversations/<int:conversation_id>/read/", MarkConversationReadView.as_view(), name="conversation-read"),
]
