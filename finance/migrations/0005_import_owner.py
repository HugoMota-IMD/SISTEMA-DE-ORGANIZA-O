from django.db import migrations


def configure_import_flag(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute("""
            CREATE OR REPLACE FUNCTION public.finance_import_mode() RETURNS boolean
            LANGUAGE sql STABLE AS $$
                SELECT COALESCE(current_setting('organiza.import_mode', true) = 'on', false)
                   AND current_user = pg_catalog.pg_get_userbyid(relowner)
                FROM pg_catalog.pg_class
                WHERE oid = 'public.finance_financialstate'::regclass
            $$;
        """)


def revert_import_flag(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute("""
            CREATE OR REPLACE FUNCTION public.finance_import_mode() RETURNS boolean
            LANGUAGE sql STABLE AS $$
                SELECT COALESCE(current_setting('organiza.import_mode', true) = 'on', false)
            $$;
        """)


class Migration(migrations.Migration):
    dependencies = [('finance', '0004_pilot_access')]
    operations = [migrations.RunPython(configure_import_flag, revert_import_flag)]
