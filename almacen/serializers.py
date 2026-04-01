from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from rest_framework import serializers

from .models import Product, ProductImage, ProductSupplier, Warehouse, WarehouseMovements, WarehouseProduct


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = "__all__"


class ProductSupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSupplier
        fields = "__all__"


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = "__all__"


class WarehouseMovementsSerializer(serializers.ModelSerializer):
    @staticmethod
    def _delta(movement_type: str, quantity: Decimal) -> Decimal:
        return quantity if movement_type == WarehouseMovements.MovementType.ENTRADA else -quantity

    @staticmethod
    def _qty_to_int(quantity: Decimal) -> int:
        return int(Decimal(quantity).to_integral_value(rounding=ROUND_HALF_UP))

    @staticmethod
    def _apply_stock_change(warehouse, product, delta: Decimal):
        stock_row, _ = WarehouseProduct.objects.select_for_update().get_or_create(
            warehouse=warehouse,
            product=product,
            defaults={
                "stock": 0,
                "ubication": "SIN UBICACION",
            },
        )
        qty_delta = WarehouseMovementsSerializer._qty_to_int(delta)
        new_stock = stock_row.stock + qty_delta
        if new_stock < 0:
            raise serializers.ValidationError(
                "Stock insuficiente en el almacen para realizar la salida."
            )
        stock_row.stock = new_stock
        stock_row.save(update_fields=["stock"])

    def create(self, validated_data):
        with transaction.atomic():
            instance = super().create(validated_data)
            delta = self._delta(instance.movement_type, instance.cant)
            self._apply_stock_change(instance.warehouse, instance.product, delta)
            return instance

    def update(self, instance, validated_data):
        with transaction.atomic():
            old_warehouse = instance.warehouse
            old_product = instance.product
            old_delta = self._delta(instance.movement_type, instance.cant)

            new_warehouse = validated_data.get("warehouse", instance.warehouse)
            new_product = validated_data.get("product", instance.product)
            new_type = validated_data.get("movement_type", instance.movement_type)
            new_cant = validated_data.get("cant", instance.cant)
            new_delta = self._delta(new_type, new_cant)

            # Revertimos el movimiento anterior y aplicamos el nuevo.
            self._apply_stock_change(old_warehouse, old_product, -old_delta)
            self._apply_stock_change(new_warehouse, new_product, new_delta)
            return super().update(instance, validated_data)

    class Meta:
        model = WarehouseMovements
        fields = "__all__"


class WarehouseProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = WarehouseProduct
        fields = "__all__"
