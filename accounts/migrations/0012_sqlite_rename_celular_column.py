# La migración 0011 puede figurar aplicada sin que SQLite haya renombrado la columna.
# Corrige BD locales que aún tienen `celular` en lugar de `cellphone`.

from django.db import migrations


def rename_celular_to_cellphone_if_needed(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts_userprofile'"
        )
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(accounts_userprofile)")
        cols = [row[1] for row in cursor.fetchall()]
        if "celular" in cols and "cellphone" not in cols:
            cursor.execute(
                "ALTER TABLE accounts_userprofile RENAME COLUMN celular TO cellphone"
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_rename_celular_to_cellphone"),
    ]

    operations = [
        migrations.RunPython(rename_celular_to_cellphone_if_needed, noop_reverse),
    ]
