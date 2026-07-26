from rest_framework import status, viewsets
from rest_framework.response import Response

from .models import StaticPage
from .permissions import IsSuperUserOrReadOnly
from .serializers import StaticPageSerializer


class StaticPageViewSet(viewsets.ModelViewSet):
    serializer_class = StaticPageSerializer
    permission_classes = [IsSuperUserOrReadOnly]
    pagination_class = None
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and user.is_superuser:
            return StaticPage.objects.all()
        return StaticPage.objects.filter(is_published=True)

    def list(self, request, *args, **kwargs):
        pages = self.get_queryset()
        return Response({"success": True, "results": StaticPageSerializer(pages, many=True).data})

    def retrieve(self, request, *args, **kwargs):
        page = self.get_object()
        return Response({"success": True, "page": StaticPageSerializer(page).data})

    def create(self, request, *args, **kwargs):
        serializer = StaticPageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = serializer.save()
        return Response(
            {"success": True, "page": StaticPageSerializer(page).data},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        page = self.get_object()
        serializer = StaticPageSerializer(page, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "page": serializer.data})

    def destroy(self, request, *args, **kwargs):
        page = self.get_object()
        page.delete()
        return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)
