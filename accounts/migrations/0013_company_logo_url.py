# Generated manually for Company.logo_url (Cloudinary / CDN)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_sqlite_rename_celular_column"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="logo_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Enlace público al logo en Cloudinary u otro CDN.",
                max_length=500,
                verbose_name="URL del logo (Cloudinary)",
            ),
        ),
    ]
