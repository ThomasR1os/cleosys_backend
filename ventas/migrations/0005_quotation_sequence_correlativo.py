# Generated manually for QuotationSequence + correlativo

import re

from django.db import migrations, models


def seed_correlativos_and_sequences(apps, schema_editor):
    Quotation = apps.get_model("ventas", "Quotation")
    UserProfile = apps.get_model("accounts", "UserProfile")
    QuotationSequence = apps.get_model("ventas", "QuotationSequence")

    for q in Quotation.objects.all():
        if q.correlativo:
            continue
        prof = UserProfile.objects.filter(user_id=q.user_id).first()
        prefix = (getattr(prof, "quotation_prefix", None) or "").strip().upper() if prof else ""
        if not prefix:
            prefix = "UNKN"
        q.correlativo = f"{prefix}-{int(q.pk):06d}"
        q.save(update_fields=["correlativo"])

    by_prefix = {}
    for row in Quotation.objects.exclude(correlativo__isnull=True).exclude(correlativo=""):
        c = row.correlativo.strip().upper()
        m = re.match(r"^([A-Z]+)-(\d+)$", c)
        if m:
            p, n = m.group(1), int(m.group(2))
            by_prefix[p] = max(by_prefix.get(p, 0), n)
    for prefix, n in by_prefix.items():
        QuotationSequence.objects.update_or_create(prefix=prefix, defaults={"last_number": n})


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_userprofile_quotation_prefix"),
        ("ventas", "0004_clientcontact_phone"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuotationSequence",
            fields=[
                ("prefix", models.CharField(max_length=10, primary_key=True, serialize=False)),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
            options={
                "db_table": "quotation_sequence",
                "managed": True,
            },
        ),
        migrations.AddField(
            model_name="quotation",
            name="correlativo",
            field=models.CharField(
                blank=True,
                db_column="correlativo",
                max_length=32,
                null=True,
                unique=True,
                verbose_name="Correlativo",
            ),
        ),
        migrations.RunPython(seed_correlativos_and_sequences, noop_reverse),
        migrations.AlterField(
            model_name="quotation",
            name="correlativo",
            field=models.CharField(
                db_column="correlativo",
                max_length=32,
                unique=True,
                verbose_name="Correlativo",
            ),
        ),
    ]
