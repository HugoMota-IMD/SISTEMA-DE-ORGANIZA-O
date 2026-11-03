"""Serialize schema migrations on a direct PostgreSQL connection, without data import."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    os.environ['APP_USE_DIRECT_DATABASE'] = 'true'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    if connection.vendor != 'postgresql':
        raise RuntimeError('O iniciador hospedado exige PostgreSQL; nenhum SQLite será criado.')
    key = 0x4F5247414E495A41
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_lock(%s)', [key])
    try:
        call_command('migrate', interactive=False, verbosity=1)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [key])


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Falha ao preparar o esquema PostgreSQL. Confira conexão direta, TLS e permissões no ambiente seguro; detalhes sensíveis omitidos.', file=sys.stderr)
        raise SystemExit(1)
