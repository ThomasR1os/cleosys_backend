# Generated manually for removing client.owner_id

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_brand_id_alter_categoryproduct_id_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="client",
            name="owner",
        ),
    ]
