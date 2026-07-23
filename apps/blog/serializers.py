from rest_framework import serializers

from .models import Category, Post


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "created_at", "updated_at")
        read_only_fields = ("id", "slug", "created_at", "updated_at")


class PostSerializer(serializers.ModelSerializer):
    author = serializers.StringRelatedField(read_only=True)
    category_detail = CategorySerializer(source="category", read_only=True)

    class Meta:
        model = Post
        fields = (
            "id",
            "title",
            "slug",
            "content",
            "image",
            "category",
            "category_detail",
            "author",
            "is_published",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "author", "created_at", "updated_at")
