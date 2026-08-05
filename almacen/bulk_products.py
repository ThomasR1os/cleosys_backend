from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import Brand, CategoryProduct, SubcategoryProduct, TypeProduct, UnitMeasurement

from .models import Product

DEFAULT_DESCRIPTION = "(sin descripción)"
CREATE_REQUIRED_FKS = ("type", "subcategory", "brand", "unit_measurement")
NULLABLE_UPDATE_FIELDS = (
    "datasheet",
    "rental_price_without_operator",
    "rental_price_with_operator",
    "warranty",
    "dimensions",
    "gross_weight",
)
BULK_UPDATE_FIELDS = [
    "description",
    "type",
    "subcategory",
    "brand",
    "unit_measurement",
    "datasheet",
    "price",
    "rental_price_without_operator",
    "rental_price_with_operator",
    "warranty",
    "status",
    "dimensions",
    "gross_weight",
    "update_date",
]


def _error(index: int, sku: str, message: str) -> dict[str, Any]:
    return {"index": index, "sku": sku, "message": message}


def _collect_fk_ids(items: list[dict]) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    types: set[int] = set()
    subcats: set[int] = set()
    brands: set[int] = set()
    units: set[int] = set()
    categories: set[int] = set()
    for item in items:
        if item.get("type") is not None:
            types.add(item["type"])
        if item.get("subcategory") is not None:
            subcats.add(item["subcategory"])
        if item.get("brand") is not None:
            brands.add(item["brand"])
        if item.get("unit_measurement") is not None:
            units.add(item["unit_measurement"])
        if item.get("category") is not None:
            categories.add(item["category"])
    return types, subcats, brands, units, categories


def _validate_row_fks(
    item: dict,
    *,
    valid_types: set[int],
    valid_subcats: set[int],
    valid_brands: set[int],
    valid_units: set[int],
    valid_categories: set[int],
    subcat_to_category: dict[int, int],
) -> str | None:
    if "type" in item and item["type"] is not None and item["type"] not in valid_types:
        return f"type {item['type']} no existe"
    if (
        "subcategory" in item
        and item["subcategory"] is not None
        and item["subcategory"] not in valid_subcats
    ):
        return f"subcategory {item['subcategory']} no existe"
    if "brand" in item and item["brand"] is not None and item["brand"] not in valid_brands:
        return f"brand {item['brand']} no existe"
    if (
        "unit_measurement" in item
        and item["unit_measurement"] is not None
        and item["unit_measurement"] not in valid_units
    ):
        return f"unit_measurement {item['unit_measurement']} no existe"
    if (
        "category" in item
        and item["category"] is not None
        and item["category"] not in valid_categories
    ):
        return f"category {item['category']} no existe"
    if (
        item.get("category") is not None
        and item.get("subcategory") is not None
        and item["subcategory"] in subcat_to_category
        and subcat_to_category[item["subcategory"]] != item["category"]
    ):
        return (
            f"subcategory {item['subcategory']} no pertenece a category {item['category']}"
        )
    return None


def _apply_update(product: Product, item: dict, *, partial_update: bool) -> None:
    # Con partial_update=True (default) solo se tocan claves presentes en el item.
    # Con partial_update=False se aplican las mismas claves presentes; null explícito limpia
    # campos nullable (los FK/price no se vacían si vienen null).
    for key, value in item.items():
        if key in ("sku", "category"):
            continue
        if key == "type":
            if value is not None:
                product.type_id = value
        elif key == "subcategory":
            if value is not None:
                product.subcategory_id = value
        elif key == "brand":
            if value is not None:
                product.brand_id = value
        elif key == "unit_measurement":
            if value is not None:
                product.unit_measurement_id = value
        elif key == "description":
            if not partial_update or value is not None:
                product.description = value if value else DEFAULT_DESCRIPTION
        elif key == "price":
            if value is not None:
                product.price = value
        elif key == "status":
            if value is not None:
                product.status = value
        elif key in NULLABLE_UPDATE_FIELDS:
            setattr(product, key, value)
    product.update_date = timezone.now()


def _build_create(item: dict) -> tuple[Product | None, str | None]:
    for fk in CREATE_REQUIRED_FKS:
        if item.get(fk) is None:
            return None, f"{fk} es obligatorio al crear"
    if item.get("price") is None:
        return None, "price es obligatorio al crear"

    now = timezone.now()
    return (
        Product(
            sku=item["sku"],
            description=item.get("description") or DEFAULT_DESCRIPTION,
            type_id=item["type"],
            subcategory_id=item["subcategory"],
            brand_id=item["brand"],
            unit_measurement_id=item["unit_measurement"],
            datasheet=item.get("datasheet"),
            price=item["price"],
            rental_price_without_operator=item.get("rental_price_without_operator"),
            rental_price_with_operator=item.get("rental_price_with_operator"),
            warranty=item.get("warranty"),
            status=item.get("status") or Product.ProductStatus.ACTIVE,
            dimensions=item.get("dimensions"),
            gross_weight=item.get("gross_weight"),
            creation_date=now,
            update_date=now,
        ),
        None,
    )


def bulk_upsert_products(*, mode: str, partial_update: bool, items: list[dict]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    skip_indexes: set[int] = set()

    seen_sku_lower: dict[str, int] = {}
    for index, item in enumerate(items):
        sku = item["sku"]
        key = sku.lower()
        if key in seen_sku_lower:
            errors.append(_error(index, sku, "SKU duplicado en el archivo"))
            skip_indexes.add(index)
        else:
            seen_sku_lower[key] = index

    sku_lowers = list(seen_sku_lower.keys())
    existing_qs = Product.objects.annotate(sku_l=Lower("sku")).filter(sku_l__in=sku_lowers)
    existing_by_lower: dict[str, Product] = {p.sku_l: p for p in existing_qs}

    type_ids, subcat_ids, brand_ids, unit_ids, category_ids = _collect_fk_ids(items)
    valid_types = set(TypeProduct.objects.filter(id__in=type_ids).values_list("id", flat=True))
    valid_brands = set(Brand.objects.filter(id__in=brand_ids).values_list("id", flat=True))
    valid_units = set(
        UnitMeasurement.objects.filter(id__in=unit_ids).values_list("id", flat=True)
    )
    valid_categories = set(
        CategoryProduct.objects.filter(id__in=category_ids).values_list("id", flat=True)
    )
    subcat_rows = SubcategoryProduct.objects.filter(id__in=subcat_ids).values_list(
        "id", "category_id"
    )
    valid_subcats = {row[0] for row in subcat_rows}
    subcat_to_category = {row[0]: row[1] for row in subcat_rows}

    to_create: list[Product] = []
    to_update: list[Product] = []

    for index, item in enumerate(items):
        if index in skip_indexes:
            continue

        sku = item["sku"]
        existing = existing_by_lower.get(sku.lower())

        fk_error = _validate_row_fks(
            item,
            valid_types=valid_types,
            valid_subcats=valid_subcats,
            valid_brands=valid_brands,
            valid_units=valid_units,
            valid_categories=valid_categories,
            subcat_to_category=subcat_to_category,
        )
        if fk_error:
            errors.append(_error(index, sku, fk_error))
            continue

        if existing is None:
            if mode == "update_only":
                errors.append(_error(index, sku, "SKU no existe (mode=update_only)"))
                continue
            product, create_error = _build_create(item)
            if create_error:
                errors.append(_error(index, sku, create_error))
                continue
            to_create.append(product)
        else:
            if mode == "create_only":
                errors.append(_error(index, sku, "SKU ya existe (mode=create_only)"))
                continue
            _apply_update(existing, item, partial_update=partial_update)
            to_update.append(existing)

    with transaction.atomic():
        if to_create:
            Product.objects.bulk_create(to_create, batch_size=500)
        if to_update:
            Product.objects.bulk_update(to_update, BULK_UPDATE_FIELDS, batch_size=500)

    return {
        "created": len(to_create),
        "updated": len(to_update),
        "failed": len(errors),
        "errors": errors,
    }
