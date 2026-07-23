from rest_framework import status, viewsets
from rest_framework.response import Response
from apps.common.pagination import StandardPagination
from .models import Category, Post
from .permissions import IsSuperUserOrReadOnly
from .serializers import CategorySerializer, PostSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsSuperUserOrReadOnly]
    pagination_class = StandardPagination
    lookup_field = "slug"
    queryset = Category.objects.all()

    def retrieve(self, request, *args, **kwargs):
        category = self.get_object()
        return Response({"success": True, "category": CategorySerializer(category).data})

    def create(self, request, *args, **kwargs):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(
            {"success": True, "category": CategorySerializer(category).data},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        category = self.get_object()
        serializer = CategorySerializer(category, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "category": serializer.data})

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        category.delete()
        return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsSuperUserOrReadOnly]
    pagination_class = StandardPagination
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and user.is_superuser:
            return Post.objects.all()
        return Post.objects.filter(is_published=True)

    def retrieve(self, request, *args, **kwargs):
        post = self.get_object()
        return Response({"success": True, "post": PostSerializer(post).data})

    def create(self, request, *args, **kwargs):
        serializer = PostSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = serializer.save(author=request.user)
        return Response(
            {"success": True, "post": PostSerializer(post).data},
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        post = self.get_object()
        serializer = PostSerializer(post, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "post": serializer.data})

    def destroy(self, request, *args, **kwargs):
        post = self.get_object()
        post.delete()
        return Response({"success": True}, status=status.HTTP_204_NO_CONTENT)
