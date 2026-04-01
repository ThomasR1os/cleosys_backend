from django.db.models import Max
from django.db.models.deletion import ProtectedError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import AlmacenWritePermission

from .cloudinary_upload import upload_product_image
from .models import Product, ProductImage, ProductSupplier, Warehouse, WarehouseMovements, WarehouseProduct
from .serializers import (
    ProductImageSerializer,
    ProductSerializer,
    ProductSupplierSerializer,
    WarehouseMovementsSerializer,
    WarehouseProductSerializer,
    WarehouseSerializer,
)


class BaseAlmacenViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, AlmacenWritePermission]


class ProductViewSet(BaseAlmacenViewSet):
    queryset = Product.objects.all().order_by("id")
    serializer_class = ProductSerializer

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "No se puede eliminar el producto porque tiene registros asociados "
                        "(imágenes, proveedores, movimientos o stock en almacén, líneas de cotización, etc.). "
                        "Elimine o reasigne esas dependencias antes de borrar el producto."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class ProductImageViewSet(BaseAlmacenViewSet):
    queryset = ProductImage.objects.all().order_by("id")
    serializer_class = ProductImageSerializer


class ProductImageUploadView(APIView):
    """
    POST multipart/form-data:
    - file: archivo imagen (requerido)
    - product_id: id del producto (requerido)
    - name: nombre legible (opcional; por defecto nombre del archivo)
    - primary: true/false (opcional; default false)
    """

    permission_classes = [permissions.IsAuthenticated, AlmacenWritePermission]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "Falta el campo file (multipart)."}, status=status.HTTP_400_BAD_REQUEST)

        product_id = request.data.get("product_id")
        if product_id in (None, ""):
            return Response({"detail": "Falta product_id."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            return Response({"detail": "product_id debe ser un entero."}, status=status.HTTP_400_BAD_REQUEST)

        if not Product.objects.filter(pk=product_id).exists():
            return Response({"detail": "Producto no existe."}, status=status.HTTP_400_BAD_REQUEST)

        name = request.data.get("name") or getattr(upload, "name", "imagen")[:100]
        primary_raw = request.data.get("primary", False)
        if isinstance(primary_raw, str):
            primary = primary_raw.lower() in ("1", "true", "yes", "on")
        else:
            primary = bool(primary_raw)

        try:
            result = upload_product_image(upload)
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response({"detail": f"Error al subir a Cloudinary: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        secure_url = result.get("secure_url") or result.get("url")
        if not secure_url:
            return Response({"detail": "Cloudinary no devolvió URL."}, status=status.HTTP_502_BAD_GATEWAY)

        next_id = (ProductImage.objects.aggregate(m=Max("id"))["m"] or 0) + 1
        image = ProductImage.objects.create(
            id=next_id,
            name=name,
            url=secure_url[:500],
            product_id=product_id,
            primary=primary,
        )
        return Response(ProductImageSerializer(image).data, status=status.HTTP_201_CREATED)


class ProductSupplierViewSet(BaseAlmacenViewSet):
    queryset = ProductSupplier.objects.all().order_by("id")
    serializer_class = ProductSupplierSerializer


class WarehouseViewSet(BaseAlmacenViewSet):
    queryset = Warehouse.objects.all().order_by("id")
    serializer_class = WarehouseSerializer

    @action(detail=True, methods=["get"], url_path="products")
    def products(self, request, pk=None):
        """Lista filas de stock (warehouse_product) de este almacén: producto, stock, ubicación."""
        warehouse = self.get_object()
        qs = (
            WarehouseProduct.objects.filter(warehouse=warehouse)
            .select_related("warehouse", "product")
            .order_by("id")
        )
        serializer = WarehouseProductSerializer(qs, many=True)
        return Response(serializer.data)


class WarehouseMovementsViewSet(BaseAlmacenViewSet):
    queryset = WarehouseMovements.objects.all().order_by("id")
    serializer_class = WarehouseMovementsSerializer

    def perform_destroy(self, instance):
        # Al eliminar, revertimos el efecto del movimiento en stock.
        serializer = self.get_serializer()
        delta = serializer._delta(instance.movement_type, instance.cant)
        serializer._apply_stock_change(instance.warehouse, instance.product, -delta)
        instance.delete()


class WarehouseProductViewSet(BaseAlmacenViewSet):
    queryset = WarehouseProduct.objects.all().order_by("id")
    serializer_class = WarehouseProductSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("warehouse", "product")
        wid = self.request.query_params.get("warehouse") or self.request.query_params.get("warehouse_id")
        if wid not in (None, ""):
            try:
                wid_int = int(wid)
            except (TypeError, ValueError):
                raise ValidationError(
                    {"warehouse": "warehouse / warehouse_id debe ser un entero válido."}
                )
            qs = qs.filter(warehouse_id=wid_int)
        return qs
