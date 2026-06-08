from django.db import migrations, models


def backfill_line_warranty_from_product(apps, schema_editor):
    QuotationProduct = apps.get_model("ventas", "QuotationProduct")
    Product = apps.get_model("almacen", "Product")
    for qp in QuotationProduct.objects.all().iterator():
        if (qp.line_warranty or "").strip():
            continue
        try:
            p = Product.objects.get(pk=qp.product_id)
        except Product.DoesNotExist:
            continue
        QuotationProduct.objects.filter(pk=qp.pk).update(
            line_warranty=p.warranty or "",
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0016_quotationproduct_delivery_time"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE quotation "
                "ALTER COLUMN delivery_time TYPE varchar(100) "
                "USING delivery_time::text;"
            ),
            reverse_sql=(
                "ALTER TABLE quotation "
                "ALTER COLUMN delivery_time TYPE integer "
                "USING CASE "
                "WHEN delivery_time ~ '^[0-9]+$' THEN delivery_time::integer "
                "ELSE 0 END;"
            ),
        ),
        migrations.AlterField(
            model_name="quotation",
            name="delivery_time",
            field=models.CharField(db_column="delivery_time", max_length=100),
        ),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE quotation_product "
                "ALTER COLUMN delivery_time TYPE varchar(100) "
                "USING CASE "
                "WHEN delivery_time IS NULL THEN NULL "
                "ELSE delivery_time::text END;"
            ),
            reverse_sql=(
                "ALTER TABLE quotation_product "
                "ALTER COLUMN delivery_time TYPE integer "
                "USING CASE "
                "WHEN delivery_time IS NULL OR delivery_time = '' THEN NULL "
                "WHEN delivery_time ~ '^[0-9]+$' THEN delivery_time::integer "
                "ELSE 0 END;"
            ),
        ),
        migrations.AlterField(
            model_name="quotationproduct",
            name="delivery_time",
            field=models.CharField(
                blank=True,
                db_column="delivery_time",
                default="",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="quotationproduct",
            name="line_warranty",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.RunPython(backfill_line_warranty_from_product, noop_reverse),
    ]
