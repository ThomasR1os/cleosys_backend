from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_remove_client_owner"),
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
                              AND table_name = 'supplier'
                              AND column_name = 'adress'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'supplier'
                              AND column_name = 'address'
                        ) THEN
                            EXECUTE 'ALTER TABLE supplier RENAME COLUMN adress TO address';
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'unit_measurement'
                              AND column_name = 'abreviation'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'unit_measurement'
                              AND column_name = 'abbreviation'
                        ) THEN
                            EXECUTE 'ALTER TABLE unit_measurement RENAME COLUMN abreviation TO abbreviation';
                        END IF;
                    END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.RenameField(
                    model_name="supplier",
                    old_name="adress",
                    new_name="address",
                ),
                migrations.AlterField(
                    model_name="supplier",
                    name="address",
                    field=models.CharField(max_length=100, db_column="address"),
                ),
                migrations.RenameField(
                    model_name="unitmeasurement",
                    old_name="abreviation",
                    new_name="abbreviation",
                ),
                migrations.AlterField(
                    model_name="unitmeasurement",
                    name="abbreviation",
                    field=models.CharField(max_length=3, db_column="abbreviation"),
                ),
            ],
        ),
    ]

