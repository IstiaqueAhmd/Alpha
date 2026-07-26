from rest_framework import serializers

from .models import StaticPage


class StaticPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaticPage
        fields = ("id", "slug", "title", "content", "is_published", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
