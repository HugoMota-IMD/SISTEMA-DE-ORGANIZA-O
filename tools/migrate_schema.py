"""Serialize schema migrations on a direct PostgreSQL connection, without data import."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(*, render_roles=False):
    if render_roles:
        from config.database import database_configuration
        from tools.render_roles import APP_ROLE, MIGRATION_ROLE, check_guards, check_identity, check_urls, grant_runtime
        import psycopg
        check_urls(os.environ['DATABASE_URL'], os.environ['DATABASE_URL_UNPOOLED'])
        options = database_configuration(ROOT, hosted=True)['default']['OPTIONS']
        tls = dict(sslmode='verify-full', sslrootcert=options['sslrootcert'], connect_timeout=15)
        with psycopg.connect(os.environ['DATABASE_URL'], **tls) as app:
            with app.cursor() as runtime_cursor:
                check_identity(runtime_cursor, APP_ROLE, migration=False)
    os.environ['APP_USE_DIRECT_DATABASE'] = 'true'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection, transaction
    if connection.vendor != 'postgresql':
        raise RuntimeError('O iniciador hospedado exige PostgreSQL; nenhum SQLite será criado.')
    key = 0x4F5247414E495A41
    with connection.cursor() as cursor:
        if render_roles:
            check_identity(cursor, MIGRATION_ROLE, migration=True)
        cursor.execute('SELECT pg_advisory_lock(%s)', [key])
    try:
        call_command('migrate', interactive=False, verbosity=1)
        if render_roles:
            with transaction.atomic(), connection.cursor() as cursor:
                grant_runtime(cursor)
            with psycopg.connect(os.environ['DATABASE_URL'], **tls) as app, app.cursor() as cursor:
                check_guards(cursor)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [key])


if __name__ == '__main__':
    try:
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--render-roles', action='store_true')
        main(render_roles=parser.parse_args().render_roles)
    except Exception:
        print('Falha ao preparar o esquema PostgreSQL. Confira as roles, as URLs pooled e direta da mesma branch, TLS e privilégios no ambiente seguro.', file=sys.stderr)
        raise SystemExit(1)
