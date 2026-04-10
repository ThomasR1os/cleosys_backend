# Generated manually: delete quotation line items when the parent quotation is deleted.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0009_quotation_conditions_works_nullable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quotationproduct",
            name="quotation",
            field=models.ForeignKey(
                db_column="quotation_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="items",
                to="ventas.quotation",
            ),
        ),
    ]
