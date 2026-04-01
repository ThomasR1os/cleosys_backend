from rest_framework import serializers

from .models import LogisticTask


class LogisticTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogisticTask
        fields = "__all__"
