from django.urls import path

from .views import (
    ConversationDetailView,
    ConversationLeaveView,
    ConversationListCreateView,
    ConversationMemberDetailView,
    ConversationMemberListCreateView,
    ConversationReadView,
    MessageDetailView,
    MessageListCreateView,
    UserSearchView,
)

app_name = "messaging"

urlpatterns = [
    path("conversations/", ConversationListCreateView.as_view(), name="conversations"),
    path("conversations/<int:conversation_id>/", ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<int:conversation_id>/read/", ConversationReadView.as_view(), name="conversation-read"),
    path("conversations/<int:conversation_id>/leave/", ConversationLeaveView.as_view(), name="conversation-leave"),
    path(
        "conversations/<int:conversation_id>/members/",
        ConversationMemberListCreateView.as_view(),
        name="conversation-members",
    ),
    path(
        "conversations/<int:conversation_id>/members/<int:user_id>/",
        ConversationMemberDetailView.as_view(),
        name="conversation-member-detail",
    ),
    path("conversations/<int:conversation_id>/messages/", MessageListCreateView.as_view(), name="messages"),
    path("messages/<int:message_id>/", MessageDetailView.as_view(), name="message-detail"),
    path("users/search/", UserSearchView.as_view(), name="user-search"),
]
