from rest_framework import serializers
from .models import Performers

class PerformerSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Performers
        fields = ["id", "name", "image"]
