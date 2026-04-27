from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0017_company_ruc"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'accounts_userprofile'
                              AND column_name = 'celular'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'accounts_userprofile'
                              AND column_name = 'cellphone'
                        ) THEN
                            EXECUTE 'ALTER TABLE accounts_userprofile RENAME COLUMN celular TO cellphone';
                        END IF;
                    END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="userprofile",
                    name="cellphone",
                    field=models.CharField(
                        blank=True,
                        db_column="cellphone",
                        default="",
                        max_length=20,
                        verbose_name="Cellphone",
                    ),
                ),
            ],
        ),
    ]

