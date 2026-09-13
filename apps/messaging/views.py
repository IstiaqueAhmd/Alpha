from django.db.models import Q
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.common.pagination import StandardPagination

from .serializers import (
    ConversationCreateSerializer,
    ConversationMemberAddSerializer,
    ConversationRenameSerializer,
    ConversationSerializer,
    MessageCreateSerializer,
    MessageSerializer,
    MessageUpdateSerializer,
)
from .services import ConversationService, MessageService


class ConversationListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer
    pagination_class = StandardPagination

    def get(self, request):
        qs = ConversationService.list_for(request.user, query=request.query_params.get("q") or None)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            ConversationSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request):
        serializer = ConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("is_group"):
            conversation = ConversationService.create_group(
                viewer=request.user, name=data["name"], member_ids=data["member_ids"],
            )
        else:
            conversation, _ = ConversationService.get_or_create_direct(
                viewer=request.user, other_user_id=data["user_id"],
            )

        return Response(
            {
                "success": True,
                "conversation": ConversationSerializer(conversation, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def get(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        return Response(
            {
                "success": True,
                "conversation": ConversationSerializer(conversation, context={"request": request}).data,
            },
        )

    def patch(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        serializer = ConversationRenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = ConversationService.rename(
            viewer=request.user, conversation=conversation, name=serializer.validated_data["name"],
        )
        return Response(
            {
                "success": True,
                "conversation": ConversationSerializer(conversation, context={"request": request}).data,
            },
        )


class ConversationReadView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def post(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        last_read_message_id = ConversationService.mark_read(viewer=request.user, conversation=conversation)
        return Response({"success": True, "last_read_message_id": last_read_message_id})


class ConversationLeaveView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def post(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        ConversationService.leave(viewer=request.user, conversation=conversation)
        return Response({"success": True})


class ConversationMemberListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def post(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        serializer = ConversationMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = ConversationService.add_members(
            viewer=request.user, conversation=conversation, member_ids=serializer.validated_data["member_ids"],
        )
        return Response(
            {
                "success": True,
                "conversation": ConversationSerializer(conversation, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ConversationMemberDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def delete(self, request, conversation_id: int, user_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        conversation = ConversationService.remove_member(
            viewer=request.user, conversation=conversation, target_user_id=user_id,
        )
        if conversation is None:
            return Response({"success": True, "conversation": None})
        return Response(
            {
                "success": True,
                "conversation": ConversationSerializer(conversation, context={"request": request}).data,
            },
        )


class MessageListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    pagination_class = StandardPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        qs = MessageService.list_for_conversation(request.user, conversation)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            MessageSerializer(page, many=True, context={"request": request}).data
        )

    def post(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)

        data = {
            "body": request.data.get("body", ""),
            "files": request.FILES.getlist("files"),
        }
        reply_to_id = request.data.get("reply_to_id")
        if reply_to_id not in (None, ""):
            data["reply_to_id"] = reply_to_id

        serializer = MessageCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        message = MessageService.send(
            viewer=request.user,
            conversation=conversation,
            body=serializer.validated_data.get("body", ""),
            files=serializer.validated_data.get("files", []),
            reply_to_id=serializer.validated_data.get("reply_to_id"),
        )
        return Response(
            {"success": True, "message": MessageSerializer(message, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )


class MessageDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def patch(self, request, message_id: int):
        message = MessageService.get_for_viewer(request.user, message_id)
        serializer = MessageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = MessageService.edit(viewer=request.user, message=message, body=serializer.validated_data["body"])
        return Response({"success": True, "message": MessageSerializer(message, context={"request": request}).data})

    def delete(self, request, message_id: int):
        message = MessageService.get_for_viewer(request.user, message_id)
        message = MessageService.delete(viewer=request.user, message=message)
        return Response({"success": True, "message": MessageSerializer(message, context={"request": request}).data})


class UserSearchView(GenericAPIView):
    """Search users to start a conversation with - platform-wide, mirrors
    `apps.teams.views.PublicUserSearchView`.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    pagination_class = StandardPagination

    def get(self, request):
        search = request.query_params.get("search") or request.query_params.get("q")
        qs = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by("name")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(email__icontains=search))
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(UserSerializer(page, many=True, context={"request": request}).data)
