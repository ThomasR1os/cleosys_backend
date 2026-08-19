from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError

from accounts.permissions import ServiciosWritePermission, company_id_for_user

from .models import Machine
from .serializers import MachineSerializer


class MachineViewSet(viewsets.ModelViewSet):
    queryset = Machine.objects.select_related("company", "client", "brand").order_by("id")
    serializer_class = MachineSerializer
    permission_classes = [permissions.IsAuthenticated, ServiciosWritePermission]

    def get_queryset(self):
        qs = Machine.objects.select_related("company", "client", "brand").order_by("id")
        user = self.request.user
        if not user.is_superuser:
            cid = company_id_for_user(user)
            if cid is None:
                return qs.none()
            qs = qs.filter(company_id=cid)

        client_id = self.request.query_params.get("client_id")
        if client_id:
            qs = qs.filter(client_id=client_id)

        brand_id = self.request.query_params.get("brand_id")
        if brand_id:
            qs = qs.filter(brand_id=brand_id)

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["company_id"] = company_id_for_user(self.request.user)
        return ctx

    def perform_create(self, serializer):
        cid = company_id_for_user(self.request.user)
        if cid is not None:
            serializer.save(company_id=cid)
            return
        if self.request.user.is_superuser:
            # company_id resolved inside serializer.validate / create
            serializer.save()
            return
        raise ValidationError(
            {
                "company": "Su usuario no tiene empresa asignada; no puede crear máquinas."
            }
        )
