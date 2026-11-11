"""Checks for the two Neon credentials and grants for Django's HTTP runtime."""
from urllib.parse import unquote, urlsplit

from psycopg import sql

APP_ROLE = 'organiza_app'
MIGRATION_ROLE = 'organiza_migrator'


def check_urls(app_url, migration_url):
    app = urlsplit(app_url)
    manager = urlsplit(migration_url)
    host = app.hostname or ''
    node, _, domain = host.partition('.')
    if (not domain or not node.endswith('-pooler')
            or manager.hostname != node.removesuffix('-pooler') + '.' + domain
            or (app.port or 5432) != (manager.port or 5432)
            or unquote(app.path) != unquote(manager.path)
            or unquote(app.username or '') != APP_ROLE
            or unquote(manager.username or '') != MIGRATION_ROLE):
        raise RuntimeError('Confira as duas roles, o endpoint pooled/direto da mesma branch e o banco do Organiza.')


def check_identity(cursor, expected, *, migration):
    cursor.execute("""
        SELECT current_user, session_user, current_schema(), r.rolsuper OR r.rolcreaterole
               OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls,
               EXISTS(SELECT FROM pg_auth_members WHERE member=r.oid),
               has_database_privilege(current_database(),'CREATE'),
               has_database_privilege(current_database(),'TEMPORARY'),
               has_schema_privilege('public','CREATE'),
               EXISTS(SELECT FROM pg_class c WHERE c.relowner=r.oid),
               EXISTS(SELECT FROM pg_namespace n WHERE n.nspowner=r.oid)
        FROM pg_roles r WHERE r.rolname=current_user
    """)
    user, session, schema, admin, member, db_create, temp, create, owns_table, owns_schema = cursor.fetchone()
    if (user != expected or session != expected or schema != 'public' or admin or member
            or db_create or create != migration or (not migration and (temp or owns_table or owns_schema))):
        raise RuntimeError('Privilégios efetivos incompatíveis com a divisão de roles do Organiza.')


def grant_runtime(cursor, role=APP_ROLE):
    # SELECT FOR UPDATE in the membership guard also requires UPDATE on at
    # least one workspace column. All new tables require explicit review.
    grants = {
        'auth_user': 'SELECT, INSERT, UPDATE (last_login, password, is_active)',
        'django_session': 'SELECT, INSERT, UPDATE, DELETE',
        'finance_loginattempt': 'SELECT, INSERT, UPDATE, DELETE',
        'finance_workspace': 'SELECT, INSERT, UPDATE (name)',
        'finance_membership': 'SELECT, INSERT, UPDATE (role), DELETE',
        'finance_financialstate': 'SELECT, INSERT, UPDATE (revision, document, updated_at)',
        'finance_operation': 'SELECT, INSERT',
        'finance_auditevent': 'SELECT, INSERT',
        'finance_useraccessevent': 'SELECT, INSERT',
    }
    for table, privileges in grants.items():
        cursor.execute(sql.SQL('GRANT {} ON TABLE {} TO {}').format(
            sql.SQL(privileges), sql.Identifier('public', table), sql.Identifier(role)))
    for table in ('auth_user', 'finance_loginattempt', 'finance_membership', 'finance_operation',
                  'finance_auditevent', 'finance_useraccessevent'):
        cursor.execute(sql.SQL('GRANT USAGE ON SEQUENCE {} TO {}').format(
            sql.Identifier('public', table + '_id_seq'), sql.Identifier(role)))


def check_guards(cursor):
    # Effective grants can also come from PUBLIC or an old default ACL.
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p') AND
                (has_table_privilege(c.oid,'TRUNCATE,TRIGGER')
                OR (c.relname IN ('finance_operation','finance_auditevent','finance_useraccessevent')
                    AND (has_any_column_privilege(c.oid,'UPDATE') OR has_table_privilege(c.oid,'DELETE')))
                OR (c.relname NOT IN ('django_session','finance_loginattempt','finance_membership')
                    AND has_table_privilege(c.oid,'DELETE'))
                OR (c.relname NOT IN ('auth_user','django_session','finance_loginattempt','finance_workspace',
                                      'finance_membership','finance_financialstate','finance_operation',
                                      'finance_auditevent','finance_useraccessevent')
                    AND has_any_column_privilege(c.oid,'INSERT,UPDATE'))))
            OR has_column_privilege('public.auth_user','is_superuser','UPDATE')
            OR has_column_privilege('public.auth_user','is_staff','UPDATE')
            OR has_table_privilege('public.django_migrations','SELECT')
    """)
    if cursor.fetchone()[0]:
        raise RuntimeError('A role web recebeu privilégios incompatíveis com o histórico ou a administração do esquema.')
