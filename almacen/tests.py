from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company, UserProfile
from core.models import Brand, CategoryProduct, SubcategoryProduct, TypeProduct, UnitMeasurement

from .models import Product
from .serializers import MAX_BULK_PRODUCTS

User = get_user_model()

BULK_URL = "/api/almacen/products/bulk-upsert/"


class ProductBulkUpsertAPITests(APITestCase):
    def setUp(self) -> None:
        self.company = Company.objects.create(name="Bulk Co")
        self.almacen = User.objects.create_user(username="almacen_bulk", password="pass12345")
        UserProfile.objects.create(
            user=self.almacen,
            company=self.company,
            role=UserProfile.Role.ALMACEN,
        )
        self.ventas = User.objects.create_user(username="ventas_bulk", password="pass12345")
        UserProfile.objects.create(
            user=self.ventas,
            company=self.company,
            role=UserProfile.Role.VENTAS,
        )
        self.logistica = User.objects.create_user(username="logistica_bulk", password="pass12345")
        UserProfile.objects.create(
            user=self.logistica,
            company=self.company,
            role=UserProfile.Role.LOGISTICA,
        )

        # Maestros sembrados por core.0002_seed_catalog
        self.category = CategoryProduct.objects.get(pk=1)
        self.other_category = CategoryProduct.objects.get(pk=2)
        self.subcategory = SubcategoryProduct.objects.get(pk=1)  # pertenece a category 1
        self.type = TypeProduct.objects.get(pk=1)
        self.brand = Brand.objects.get(pk=1)
        self.unit = UnitMeasurement.objects.get(pk=1)

        self.existing = Product.objects.create(
            type=self.type,
            subcategory=self.subcategory,
            brand=self.brand,
            sku="EXIST-001",
            description="Producto existente",
            price=Decimal("50.00"),
            warranty="6 meses",
            unit_measurement=self.unit,
            status=Product.ProductStatus.ACTIVE,
            datasheet="ficha vieja",
        )

    def _base_create_item(self, sku: str, **overrides) -> dict:
        item = {
            "sku": sku,
            "description": f"Desc {sku}",
            "category": self.category.pk,
            "subcategory": self.subcategory.pk,
            "type": self.type.pk,
            "brand": self.brand.pk,
            "unit_measurement": self.unit.pk,
            "price": "99.90",
            "status": "ACTIVE",
        }
        item.update(overrides)
        return item

    def test_upsert_creates_and_updates(self) -> None:
        self.client.force_authenticate(self.almacen)
        res = self.client.post(
            BULK_URL,
            {
                "mode": "upsert",
                "partial_update": True,
                "items": [
                    self._base_create_item("NEW-001"),
                    {
                        "sku": "exist-001",
                        "price": "75.50",
                        "warranty": "12 meses",
                    },
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["created"], 1)
        self.assertEqual(res.data["updated"], 1)
        self.assertEqual(res.data["failed"], 0)
        self.assertEqual(res.data["errors"], [])

        created = Product.objects.get(sku="NEW-001")
        self.assertEqual(created.description, "Desc NEW-001")
        self.assertEqual(created.price, Decimal("99.90"))

        self.existing.refresh_from_db()
        self.assertEqual(self.existing.price, Decimal("75.50"))
        self.assertEqual(self.existing.warranty, "12 meses")
        self.assertEqual(self.existing.datasheet, "ficha vieja")
        self.assertEqual(self.existing.description, "Producto existente")

    def test_partial_update_preserves_omitted_fields(self) -> None:
        self.client.force_authenticate(self.almacen)
        res = self.client.post(
            BULK_URL,
            {
                "mode": "upsert",
                "partial_update": True,
                "items": [{"sku": "EXIST-001", "description": "Solo descripción"}],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["updated"], 1)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.description, "Solo descripción")
        self.assertEqual(self.existing.price, Decimal("50.00"))
        self.assertEqual(self.existing.warranty, "6 meses")

    def test_duplicate_sku_in_request(self) -> None:
        self.client.force_authenticate(self.almacen)
        res = self.client.post(
            BULK_URL,
            {
                "items": [
                    self._base_create_item("DUP-001"),
                    self._base_create_item("dup-001", description="Segundo"),
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["created"], 1)
        self.assertEqual(res.data["failed"], 1)
        self.assertEqual(res.data["errors"][0]["index"], 1)
        self.assertEqual(res.data["errors"][0]["message"], "SKU duplicado en el archivo")
        self.assertEqual(Product.objects.filter(sku__iexact="DUP-001").count(), 1)

    def test_invalid_fk_best_effort(self) -> None:
        self.client.force_authenticate(self.almacen)
        res = self.client.post(
            BULK_URL,
            {
                "items": [
                    self._base_create_item("OK-001"),
                    self._base_create_item("BAD-001", category=99999, subcategory=self.subcategory.pk),
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["created"], 1)
        self.assertEqual(res.data["failed"], 1)
        self.assertIn("category 99999", res.data["errors"][0]["message"])
        self.assertTrue(Product.objects.filter(sku="OK-001").exists())
        self.assertFalse(Product.objects.filter(sku="BAD-001").exists())

    def test_category_subcategory_mismatch(self) -> None:
        self.client.force_authenticate(self.almacen)
        res = self.client.post(
            BULK_URL,
            {
                "items": [
                    self._base_create_item(
                        "MISMATCH-001",
                        category=self.other_category.pk,
                        subcategory=self.subcategory.pk,
                    ),
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["failed"], 1)
        self.assertIn("no pertenece", res.data["errors"][0]["message"])

    def test_empty_items_and_too_many(self) -> None:
        self.client.force_authenticate(self.almacen)
        empty = self.client.post(BULK_URL, {"items": []}, format="json")
        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)

        oversized = self.client.post(
            BULK_URL,
            {"items": [self._base_create_item(f"SKU-{i}") for i in range(MAX_BULK_PRODUCTS + 1)]},
            format="json",
        )
        self.assertEqual(oversized.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_only_and_update_only(self) -> None:
        self.client.force_authenticate(self.almacen)

        create_only = self.client.post(
            BULK_URL,
            {
                "mode": "create_only",
                "items": [
                    self._base_create_item("ONLY-NEW"),
                    {"sku": "EXIST-001", "price": "1.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(create_only.status_code, status.HTTP_200_OK, create_only.data)
        self.assertEqual(create_only.data["created"], 1)
        self.assertEqual(create_only.data["failed"], 1)
        self.assertIn("create_only", create_only.data["errors"][0]["message"])

        update_only = self.client.post(
            BULK_URL,
            {
                "mode": "update_only",
                "items": [
                    {"sku": "EXIST-001", "price": "60.00"},
                    self._base_create_item("GHOST-001"),
                ],
            },
            format="json",
        )
        self.assertEqual(update_only.status_code, status.HTTP_200_OK, update_only.data)
        self.assertEqual(update_only.data["updated"], 1)
        self.assertEqual(update_only.data["failed"], 1)
        self.assertIn("update_only", update_only.data["errors"][0]["message"])
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.price, Decimal("60.00"))

    def test_default_description_on_create(self) -> None:
        self.client.force_authenticate(self.almacen)
        item = self._base_create_item("NO-DESC")
        del item["description"]
        res = self.client.post(BULK_URL, {"items": [item]}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["created"], 1)
        self.assertEqual(
            Product.objects.get(sku="NO-DESC").description,
            "(sin descripción)",
        )

    def test_warrannty_alias(self) -> None:
        self.client.force_authenticate(self.almacen)
        res = self.client.post(
            BULK_URL,
            {"items": [{"sku": "EXIST-001", "warrannty": "24 meses"}]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.warranty, "24 meses")

    def test_permissions(self) -> None:
        unauth = self.client.post(BULK_URL, {"items": [self._base_create_item("X")]}, format="json")
        self.assertIn(unauth.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

        self.client.force_authenticate(self.ventas)
        forbidden = self.client.post(
            BULK_URL, {"items": [self._base_create_item("X")]}, format="json"
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.logistica)
        allowed = self.client.post(
            BULK_URL, {"items": [self._base_create_item("LOG-001")]}, format="json"
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK, allowed.data)
        self.assertEqual(allowed.data["created"], 1)
