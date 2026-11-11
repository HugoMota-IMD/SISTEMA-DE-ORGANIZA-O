"""Read-only readiness/least-privilege check, without a migration credential."""
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    if os.environ.get('DATABASE_URL_UNPOOLED') or os.environ.get('APP_USE_DIRECT_DATABASE', '').lower() == 'true':
        raise RuntimeError('A credencial de migracao nao pertence ao processo web.')
    parsed = urlsplit(os.environ.get('DATABASE_URL', ''))
    from tools.render_roles import APP_ROLE, check_identity, check_guards
    if unquote(parsed.username or '') != APP_ROLE or not (parsed.hostname or '').split('.')[0].endswith('-pooler'):
        raise RuntimeError('Use a conexao pooled da role organiza_app no processo web.')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.db import connection, transaction
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION READ ONLY')
        check_identity(cursor, APP_ROLE, migration=False)
        check_guards(cursor)
        # No access to django_migrations is granted to the web role. Check the
        # owner gate on import and essential runtime relations instead.
        cursor.execute("SELECT set_config('organiza.import_mode', 'on', true)")
        cursor.execute('SELECT public.finance_import_mode()')
        if cursor.fetchone() != (False,):
            raise RuntimeError('A protecao do modo de importacao esta ausente.')
        for table in ('auth_user', 'django_session', 'finance_workspace', 'finance_membership',
                      'finance_financialstate', 'finance_operation', 'finance_auditevent',
                      'finance_useraccessevent', 'finance_loginattempt'):
            cursor.execute(f'SELECT 1 FROM {table} LIMIT 0')
    connection.close()
    print('Conexao web e privilegios conferidos sem executar migracoes.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Falha na verificacao web. Confira DATABASE_URL pooled, TLS, privilegios e esquema previamente migrado; nenhum esquema foi alterado.', file=sys.stderr)
        raise SystemExit(1)
