from django.core.validators import MinValueValidator
from django.db import migrations, models


def backfill_delivery_time_from_quotation(apps, schema_editor):
    QuotationProduct = apps.get_model("ventas", "QuotationProduct")
    for qp in QuotationProduct.objects.select_related("quotation").iterator():
        if qp.delivery_time is not None:
            continue
        QuotationProduct.objects.filter(pk=qp.pk).update(
            delivery_time=qp.quotation.delivery_time,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0015_proforma_request_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotationproduct",
            name="delivery_time",
            field=models.IntegerField(
                blank=True,
                db_column="delivery_time",
                null=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.RunPython(backfill_delivery_time_from_quotation, noop_reverse),
    ]
