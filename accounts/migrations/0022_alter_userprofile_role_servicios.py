from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0021_userprofile_signature_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("ALMACEN", "Almacén"),
                    ("VENTAS", "Ventas"),
                    ("LOGISTICA", "Logística"),
                    ("SERVICIOS", "Servicios"),
                    ("ADMIN", "Administrador"),
                ],
                db_column="role",
                default="VENTAS",
                max_length=20,
                verbose_name="Rol",
            ),
        ),
    ]
