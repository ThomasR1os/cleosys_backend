from rest_framework import permissions, status, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.permissions import ServiciosWritePermission, company_id_for_user
from almacen.cloudinary_upload import upload_product_image

from .models import Machine, MachineElectricalEvaluation, MachineReport, MachineReportPhoto
from .serializers import (
    MachineElectricalEvaluationSerializer,
    MachineReportPhotoSerializer,
    MachineReportSerializer,
    MachineSerializer,
)


class MachineViewSet(viewsets.ModelViewSet):
    queryset = Machine.objects.select_related(
        "company", "client", "brand", "category", "subcategory", "electrical_evaluation"
    ).order_by("id")
    serializer_class = MachineSerializer
    permission_classes = [permissions.IsAuthenticated, ServiciosWritePermission]

    def get_queryset(self):
        qs = Machine.objects.select_related(
            "company", "client", "brand", "category", "subcategory", "electrical_evaluation"
        ).order_by("id")
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
            serializer.save()
            return
        raise ValidationError(
            {
                "company": "Su usuario no tiene empresa asignada; no puede crear máquinas."
            }
        )

    @action(
        detail=True,
        methods=["get", "put", "patch"],
        url_path="electrical-evaluation",
    )
    def electrical_evaluation(self, request, pk=None):
        machine = self.get_object()

        if request.method == "GET":
            try:
                evaluation = machine.electrical_evaluation
            except MachineElectricalEvaluation.DoesNotExist:
                return Response(None)
            return Response(MachineElectricalEvaluationSerializer(evaluation).data)

        serializer = MachineElectricalEvaluationSerializer(
            data=request.data,
            partial=(request.method == "PATCH"),
        )
        serializer.is_valid(raise_exception=True)
        evaluation, _ = MachineElectricalEvaluation.objects.update_or_create(
            machine=machine,
            defaults=serializer.validated_data,
        )
        return Response(
            MachineElectricalEvaluationSerializer(evaluation).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="reports")
    def reports(self, request, pk=None):
        machine = self.get_object()
        qs = (
            MachineReport.objects.filter(machine=machine)
            .select_related("machine", "origin_report", "created_by", "electrical_evaluation")
            .prefetch_related("part_checks__recommended_part", "photos")
            .order_by("-intervention_date", "-id")
        )
        serializer = MachineReportSerializer(qs, many=True, context=self.get_serializer_context())
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path="upload_plate",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_plate(self, request, pk=None):
        """
        Sube foto de placa a Cloudinary y actualiza plate_image_url.
        multipart: file (requerido)
        """
        machine = self.get_object()
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": ["Falta el campo file (multipart)."]})

        try:
            result = upload_product_image(upload, folder="cleosys/machine-plates")
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response(
                {"detail": f"Error al subir a Cloudinary: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        secure_url = result.get("secure_url") or result.get("url")
        if not secure_url:
            return Response(
                {"detail": "Cloudinary no devolvió URL."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        machine.plate_image_url = secure_url[:500]
        machine.save(update_fields=["plate_image_url", "updated_at"])
        return Response(
            MachineSerializer(machine, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )


class MachineReportViewSet(viewsets.ModelViewSet):
    queryset = (
        MachineReport.objects.select_related(
            "machine", "origin_report", "created_by", "electrical_evaluation"
        )
        .prefetch_related("part_checks__recommended_part", "photos")
        .order_by("-intervention_date", "-id")
    )
    serializer_class = MachineReportSerializer
    permission_classes = [permissions.IsAuthenticated, ServiciosWritePermission]

    def get_queryset(self):
        qs = (
            MachineReport.objects.select_related(
                "machine", "origin_report", "created_by", "electrical_evaluation"
            )
            .prefetch_related("part_checks__recommended_part", "photos")
            .order_by("-intervention_date", "-id")
        )
        user = self.request.user
        if not user.is_superuser:
            cid = company_id_for_user(user)
            if cid is None:
                return qs.none()
            qs = qs.filter(machine__company_id=cid)

        machine_id = self.request.query_params.get("machine_id")
        if machine_id:
            qs = qs.filter(machine_id=machine_id)

        report_type = self.request.query_params.get("type")
        if report_type:
            qs = qs.filter(type=report_type)

        date_from = self.request.query_params.get("intervention_date_from")
        if date_from:
            qs = qs.filter(intervention_date__gte=date_from)

        date_to = self.request.query_params.get("intervention_date_to")
        if date_to:
            qs = qs.filter(intervention_date__lte=date_to)

        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["company_id"] = company_id_for_user(self.request.user)
        return ctx

    @action(detail=True, methods=["get", "post"], url_path="photos")
    def photos(self, request, pk=None):
        report = self.get_object()
        if request.method == "GET":
            qs = report.photos.all().order_by("sort_order", "id")
            return Response(MachineReportPhotoSerializer(qs, many=True).data)

        serializer = MachineReportPhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = MachineReportPhoto.objects.create(report=report, **serializer.validated_data)
        return Response(
            MachineReportPhotoSerializer(photo).data,
            status=status.HTTP_201_CREATED,
        )


class ReportPhotoUploadView(views.APIView):
    """
    Sube imagen a Cloudinary y crea MachineReportPhoto.
    multipart: file (requerido), report_id, label, note (opcional), sort_order (opcional).
    """

    permission_classes = [permissions.IsAuthenticated, ServiciosWritePermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": ["Falta el campo file (multipart)."]})

        report_id = request.data.get("report_id")
        if report_id in (None, ""):
            raise ValidationError({"report_id": ["Falta report_id."]})
        try:
            report_id = int(report_id)
        except (TypeError, ValueError):
            raise ValidationError({"report_id": ["report_id debe ser un entero."]})

        qs = MachineReport.objects.select_related("machine")
        if not request.user.is_superuser:
            cid = company_id_for_user(request.user)
            if cid is None:
                return Response(
                    {"detail": "Usuario sin empresa asignada."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            qs = qs.filter(machine__company_id=cid)
        report = qs.filter(pk=report_id).first()
        if report is None:
            return Response(
                {"detail": "Informe no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        label = (request.data.get("label") or "").strip().upper()
        if label not in MachineReportPhoto.Label.values:
            raise ValidationError(
                {
                    "label": [
                        f"Debe ser uno de: {', '.join(MachineReportPhoto.Label.values)}"
                    ]
                }
            )

        note = request.data.get("note") or ""
        sort_raw = request.data.get("sort_order", 0)
        try:
            sort_order = int(sort_raw or 0)
        except (TypeError, ValueError):
            raise ValidationError({"sort_order": ["Debe ser un entero."]})

        try:
            result = upload_product_image(upload, folder="cleosys/report-photos")
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response(
                {"detail": f"Error al subir a Cloudinary: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        secure_url = result.get("secure_url") or result.get("url")
        if not secure_url:
            return Response(
                {"detail": "Cloudinary no devolvió URL."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        photo = MachineReportPhoto.objects.create(
            report=report,
            photo_url=secure_url[:500],
            label=label,
            note=str(note)[:5000] if note else "",
            sort_order=sort_order,
        )
        return Response(
            MachineReportPhotoSerializer(photo).data,
            status=status.HTTP_201_CREATED,
        )
