# En PostgreSQL, RenameField(0011) puede dejar la columna como "celular"; el modelo usa db_column="cellphone".

from django.db import migrations


def rename_celular_to_cellphone(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'accounts_userprofile'
              AND column_name = 'celular'
            """
        )
        if cursor.fetchone():
            cursor.execute(
                'ALTER TABLE accounts_userprofile RENAME COLUMN celular TO cellphone'
            )


def reverse_rename(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'accounts_userprofile'
              AND column_name = 'cellphone'
            """
        )
        if cursor.fetchone():
            cursor.execute(
                'ALTER TABLE accounts_userprofile RENAME COLUMN cellphone TO celular'
            )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0014_company_bank_accounts"),
    ]

    operations = [
        migrations.RunPython(rename_celular_to_cellphone, reverse_rename),
    ]
