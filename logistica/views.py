from rest_framework import permissions, viewsets

from accounts.permissions import LogisticaWritePermission

from .models import LogisticTask
from .serializers import LogisticTaskSerializer


class LogisticTaskViewSet(viewsets.ModelViewSet):
    queryset = LogisticTask.objects.all().order_by("id")
    serializer_class = LogisticTaskSerializer
    permission_classes = [permissions.IsAuthenticated, LogisticaWritePermission]
