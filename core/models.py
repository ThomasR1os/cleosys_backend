from django.db import models
from django.utils.translation import gettext_lazy as _


class Supplier(models.Model):
    class SupplierType(models.TextChoices):
        EXTRANJERO = "EXTRANJERO", _("Extranjero")
        NACIONAL = "NACIONAL", _("Nacional")

    id = models.AutoField(primary_key=True)
    type = models.CharField(max_length=20, choices=SupplierType.choices, db_column="type")
    ruc = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    adress = models.CharField(max_length=100)
    contact = models.CharField(max_length=100)
    email = models.CharField(max_length=250)
    phone = models.CharField(max_length=100)
    bank_accounts = models.TextField(db_column="bank_accounts")

    class Meta:
        managed = True
        db_table = "supplier"

    def __str__(self) -> str:
        return self.name


class Brand(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        managed = True
        db_table = "brand"

    def __str__(self) -> str:
        return self.name


class CategoryProduct(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        managed = True
        db_table = "category_product"

    def __str__(self) -> str:
        return self.name


class SubcategoryProduct(models.Model):
    id = models.AutoField(primary_key=True)
    category = models.ForeignKey(
        CategoryProduct,
        db_column="category_id",
        on_delete=models.PROTECT,
        related_name="subcategories",
    )
    name = models.CharField(max_length=100)

    class Meta:
        managed = True
        db_table = "subcategory_product"

    def __str__(self) -> str:
        return self.name


class TypeProduct(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        managed = True
        db_table = "type_product"

    def __str__(self) -> str:
        return self.name


class UnitMeasurement(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    abreviation = models.CharField(max_length=3, db_column="abreviation")

    class Meta:
        managed = True
        db_table = "unit_measurement"

    def __str__(self) -> str:
        return f"{self.name} ({self.abreviation})"


class Client(models.Model):
    id = models.AutoField(primary_key=True)
    ruc = models.CharField(max_length=100)
    name = models.CharField(max_length=100)

    class Meta:
        managed = True
        db_table = "client"

    def __str__(self) -> str:
        return self.name


class PaymentMethods(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        managed = True
        db_table = "payment_methods"

    def __str__(self) -> str:
        return self.name
