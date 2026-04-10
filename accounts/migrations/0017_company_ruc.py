# Company.ruc (TextField, before name in model)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0016_company_branding"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="ruc",
            field=models.TextField(blank=True, default="", verbose_name="RUC"),
        ),
    ]
