import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0010_quotationproduct_cascade_delete"),
    ]

    operations = [
        migrations.AddField(
            model_name="quotation",
            name="client_contact",
            field=models.ForeignKey(
                blank=True,
                db_column="client_contact_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="quotations",
                to="ventas.clientcontact",
            ),
        ),
    ]
