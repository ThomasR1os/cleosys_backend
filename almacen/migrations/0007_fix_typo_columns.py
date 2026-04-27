from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("almacen", "0006_product_datasheet_nullable"),
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
                              AND table_name = 'product'
                              AND column_name = 'warrannty'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'product'
                              AND column_name = 'warranty'
                        ) THEN
                            EXECUTE 'ALTER TABLE product RENAME COLUMN warrannty TO warranty';
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'warehouse_product'
                              AND column_name = 'ubication'
                        ) AND NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'warehouse_product'
                              AND column_name = 'location'
                        ) THEN
                            EXECUTE 'ALTER TABLE warehouse_product RENAME COLUMN ubication TO location';
                        END IF;
                    END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.RenameField(
                    model_name="product",
                    old_name="warrannty",
                    new_name="warranty",
                ),
                migrations.AlterField(
                    model_name="product",
                    name="warranty",
                    field=models.CharField(blank=True, db_column="warranty", max_length=20, null=True),
                ),
                migrations.RenameField(
                    model_name="warehouseproduct",
                    old_name="ubication",
                    new_name="location",
                ),
                migrations.AlterField(
                    model_name="warehouseproduct",
                    name="location",
                    field=models.CharField(db_column="location", max_length=250),
                ),
            ],
        ),
    ]

