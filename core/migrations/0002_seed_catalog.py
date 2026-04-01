# Datos iniciales: tipos, categorías, subcategorías, marcas, unidades de medida

from django.db import migrations


def seed_catalog(apps, schema_editor):
    TypeProduct = apps.get_model("core", "TypeProduct")
    CategoryProduct = apps.get_model("core", "CategoryProduct")
    SubcategoryProduct = apps.get_model("core", "SubcategoryProduct")
    Brand = apps.get_model("core", "Brand")
    UnitMeasurement = apps.get_model("core", "UnitMeasurement")

    types_data = [
        (1, "ALMACENABLE"),
        (2, "CONSUMIBLE"),
        (3, "SERVICIO"),
    ]
    for pk, name in types_data:
        TypeProduct.objects.update_or_create(id=pk, defaults={"name": name})

    categories_data = [
        (1, "COMPRESOR"),
        (2, "SECADOR"),
        (3, "TANQUE"),
        (4, "SOPLADOR"),
    ]
    for pk, name in categories_data:
        CategoryProduct.objects.update_or_create(id=pk, defaults={"name": name})

    subcategories_data = [
        # COMPRESOR
        (1, 1, "COMPRESOR DE PISTON"),
        (2, 1, "COMPRESOR DE TORNILLO"),
        (3, 1, "COMPRESOR DIESEL"),
        # SECADOR
        (4, 2, "SECADOR REFRIGERATIVO"),
        (5, 2, "SECADOR DE ADSORCION"),
        # TANQUE
        (6, 3, "TANQUE DE PULMON"),
        # SOPLADOR
        (7, 4, "SOPLADOR CENTRIFUGO"),
    ]
    for pk, category_id, name in subcategories_data:
        SubcategoryProduct.objects.update_or_create(
            id=pk,
            defaults={"category_id": category_id, "name": name},
        )

    brands_data = [
        (1, "SCHULZ"),
        (2, "KOTECH"),
        (3, "EMAX"),
        (4, "CHIAPERINI"),
        (5, "INGERSOLL RAND"),
        (6, "ATLAS COPCO"),
    ]
    for pk, name in brands_data:
        Brand.objects.update_or_create(id=pk, defaults={"name": name})

    # abreviation max_length=3 en el modelo
    units_data = [
        (1, "Unidad", "UND"),
        (2, "Pieza", "PZA"),
        (3, "Juego", "JGO"),
        (4, "Par", "PAR"),
        (5, "Kilogramo", "KG"),
        (6, "Gramo", "GR"),
        (7, "Litro", "L"),
        (8, "Mililitro", "ML"),
        (9, "Metro", "M"),
        (10, "Centimetro", "CM"),
        (11, "Milimetro", "MM"),
        (12, "Metro cubico", "M3"),
        (13, "Bar", "BAR"),
        (14, "PSI", "PSI"),
        (15, "Hora", "HR"),
        (16, "Minuto", "MIN"),
        (17, "Segundo", "SEG"),
        (18, "Kilowatt", "KW"),
        (19, "Caballo de fuerza", "HP"),
        (20, "RPM", "RPM"),
    ]
    for pk, name, abbr in units_data:
        UnitMeasurement.objects.update_or_create(
            id=pk,
            defaults={"name": name, "abreviation": abbr},
        )


def unseed_catalog(apps, schema_editor):
    TypeProduct = apps.get_model("core", "TypeProduct")
    CategoryProduct = apps.get_model("core", "CategoryProduct")
    SubcategoryProduct = apps.get_model("core", "SubcategoryProduct")
    Brand = apps.get_model("core", "Brand")
    UnitMeasurement = apps.get_model("core", "UnitMeasurement")

    SubcategoryProduct.objects.filter(id__in=range(1, 8)).delete()
    CategoryProduct.objects.filter(id__in=range(1, 5)).delete()
    TypeProduct.objects.filter(id__in=range(1, 4)).delete()
    Brand.objects.filter(id__in=range(1, 7)).delete()
    UnitMeasurement.objects.filter(id__in=range(1, 21)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
