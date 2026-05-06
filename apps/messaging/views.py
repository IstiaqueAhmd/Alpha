from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination

from .serializers import (
    ConversationCreateSerializer,
    ConversationSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from .services import ConversationService, MessageService


class ConversationListCreateView(APIView):
    permission_classes = [IsAuthenticated]
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
        conversation = ConversationService.get_or_create_with(
            viewer=request.user, other_user_id=serializer.validated_data["user_id"],
        )
        return Response(
            {
                "success": True,
                "conversation": ConversationSerializer(conversation, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        return Response(
            {
                "success": True,
                "conversation": ConversationSerializer(conversation, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )


class MessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        qs = MessageService.list_for_conversation(request.user, conversation)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(MessageSerializer(page, many=True).data)

    def post(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)

        files = request.FILES.getlist("files")
        data = {"body": request.data.get("body", ""), "files": files}
        serializer = MessageCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        message = MessageService.send(
            viewer=request.user,
            conversation=conversation,
            body=serializer.validated_data.get("body", ""),
            files=serializer.validated_data.get("files", []),
        )
        return Response(
            {"success": True, "message": MessageSerializer(message).data},
            status=status.HTTP_201_CREATED,
        )


class MarkConversationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id: int):
        conversation = ConversationService.get_for_viewer(request.user, conversation_id)
        updated = MessageService.mark_read(request.user, conversation)
        return Response({"success": True, "marked_read": updated}, status=status.HTTP_200_OK)
