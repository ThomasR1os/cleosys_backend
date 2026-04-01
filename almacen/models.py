from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import (
    Brand,
    CategoryProduct,
    SubcategoryProduct,
    Supplier,
    TypeProduct,
    UnitMeasurement,
)


class Product(models.Model):
    class ProductStatus(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        INACTIVE = "INACTIVE", _("Inactive")

    id = models.AutoField(primary_key=True)
    type = models.ForeignKey(
        TypeProduct,
        db_column="type_id",
        on_delete=models.PROTECT,
        related_name="products",
    )
    subcategory = models.ForeignKey(
        SubcategoryProduct,
        db_column="subcategory_id",
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        db_column="brand_id",
        on_delete=models.PROTECT,
        related_name="products",
    )
    sku = models.CharField(max_length=100)
    description = models.CharField(max_length=250)
    datasheet = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    rental_price_without_operator = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, db_column="rental_price_without_operator"
    )
    rental_price_with_operator = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, db_column="rental_price_with_operator"
    )
    warrannty = models.CharField(max_length=20, db_column="warrannty")
    unit_measurement = models.ForeignKey(
        UnitMeasurement,
        db_column="unit_measurement_id",
        on_delete=models.PROTECT,
        related_name="products",
    )
    status = models.CharField(max_length=20, choices=ProductStatus.choices, db_column="status")
    dimensions = models.CharField(max_length=100, null=True, blank=True)
    gross_weight = models.CharField(max_length=100, null=True, blank=True)
    creation_date = models.DateTimeField(default=timezone.now, db_column="creation_date")
    update_date = models.DateTimeField(default=timezone.now, db_column="update_date")

    class Meta:
        managed = True
        db_table = "product"

    def __str__(self) -> str:
        return self.sku


class ProductImage(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    url = models.CharField(max_length=500)
    product = models.ForeignKey(Product, db_column="product_id", on_delete=models.PROTECT, related_name="images")
    primary = models.BooleanField(db_column="primary")

    class Meta:
        managed = True
        db_table = "product_image"

    def save(self, *args, **kwargs):
        # Un producto solo puede tener una imagen principal: al marcar primary=True, se quita en las demás.
        # Bloqueamos el Product para evitar carreras (p. ej. dos POST concurrentes con primary=True).
        with transaction.atomic():
            if self.primary and self.product_id is not None:
                Product.objects.select_for_update().filter(pk=self.product_id).first()
                qs = ProductImage.objects.filter(product_id=self.product_id)
                if self.pk is not None:
                    qs = qs.exclude(pk=self.pk)
                qs.update(primary=False)
            super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class ProductSupplier(models.Model):
    class ProductSupplierMoney(models.TextChoices):
        USD = "USD", _("USD")
        PEN = "PEN", _("PEN")

    id = models.AutoField(primary_key=True)
    money = models.CharField(max_length=5, choices=ProductSupplierMoney.choices, db_column="money")
    product = models.ForeignKey(Product, db_column="product_id", on_delete=models.PROTECT, related_name="suppliers")
    supplier = models.ForeignKey(Supplier, db_column="supplier_id", on_delete=models.PROTECT, related_name="products")
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    incoterm = models.CharField(max_length=3)
    creation_date = models.DateTimeField(default=timezone.now, db_column="creation_date")

    class Meta:
        managed = True
        db_table = "product_supplier"

    def __str__(self) -> str:
        return f"{self.product.sku} - {self.supplier.name}"


class Warehouse(models.Model):
    id = models.AutoField(primary_key=True)
    supplier = models.ForeignKey(Supplier, db_column="supplier_id", on_delete=models.PROTECT, related_name="warehouses")
    address = models.CharField(max_length=100)

    class Meta:
        managed = True
        db_table = "warehouse"

    def __str__(self) -> str:
        return f"Warehouse #{self.id}"


class WarehouseMovements(models.Model):
    class MovementType(models.TextChoices):
        ENTRADA = "ENTRADA", _("Entrada")
        SALIDA = "SALIDA", _("Salida")

    id = models.AutoField(primary_key=True)
    warehouse = models.ForeignKey(Warehouse, db_column="warehouse_id", on_delete=models.PROTECT, related_name="movements")
    product = models.ForeignKey(
        Product,
        db_column="product_id",
        on_delete=models.PROTECT,
        related_name="warehouse_movements",
    )
    cant = models.DecimalField(max_digits=10, decimal_places=2)
    movement_type = models.CharField(max_length=20, choices=MovementType.choices, db_column="type")
    observation = models.IntegerField()
    creation_date = models.DateTimeField(default=timezone.now, db_column="creation_date")

    class Meta:
        managed = True
        db_table = "warehouse_movements"

    def __str__(self) -> str:
        return f"{self.movement_type} - {self.product.sku}"


class WarehouseProduct(models.Model):
    id = models.AutoField(primary_key=True)
    warehouse = models.ForeignKey(Warehouse, db_column="warehouse_id", on_delete=models.PROTECT, related_name="warehouse_products")
    product = models.ForeignKey(
        Product,
        db_column="product_id",
        on_delete=models.PROTECT,
        related_name="warehouse_stocks",
    )
    stock = models.IntegerField(default=0)
    ubication = models.CharField(max_length=250)
    creation_date = models.DateTimeField(default=timezone.now, db_column="creation_date")

    class Meta:
        managed = True
        db_table = "warehouse_product"
        constraints = [
            models.UniqueConstraint(
                fields=["warehouse", "product"],
                name="uq_warehouse_product_stock",
            )
        ]

    def __str__(self) -> str:
        return f"{self.warehouse_id} - stock:{self.stock}"
