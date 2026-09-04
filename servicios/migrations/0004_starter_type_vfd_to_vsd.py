from django.db import migrations, models


def forwards_vfd_to_vsd(apps, schema_editor):
    MachineElectricalEvaluation = apps.get_model("servicios", "MachineElectricalEvaluation")
    MachineElectricalEvaluation.objects.filter(starter_type="VFD").update(starter_type="VSD")


def backwards_vsd_to_vfd(apps, schema_editor):
    MachineElectricalEvaluation = apps.get_model("servicios", "MachineElectricalEvaluation")
    MachineElectricalEvaluation.objects.filter(starter_type="VSD").update(starter_type="VFD")


class Migration(migrations.Migration):

    dependencies = [
        ("servicios", "0003_electrical_evaluation_and_remove_voltage"),
    ]

    operations = [
        migrations.RunPython(forwards_vfd_to_vsd, backwards_vsd_to_vfd),
        migrations.AlterField(
            model_name="machineelectricalevaluation",
            name="starter_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("DIRECT", "Directo"),
                    ("STAR_DELTA", "Estrella-triángulo"),
                    ("VSD", "VSD"),
                    ("SOFT", "SOFT"),
                ],
                default="",
                max_length=20,
            ),
        ),
    ]
