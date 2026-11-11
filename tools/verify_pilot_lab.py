"""Disposable Linux PG18/PgBouncer lab. Run only in deploy/pilot-lab.Dockerfile.

The build context must contain source only, without .env, data or backups. The
container has no external network or host mounts. All credentials are invented
inside it. This runner never accepts an external database URL.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'test-results'


def run(name, args, env=None, timeout=300):
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, timeout=timeout)
    (OUT / (name + '.log')).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Lab stage failed: ' + name)
    print('PASS ' + name, flush=True)
    return result.stdout.decode().strip()


def worker(kind):
    import django
    django.setup()
    from django.contrib.auth import get_user_model
    from django.db import connection, connections, transaction, IntegrityError
    from django.test import Client
    from django.test.utils import override_settings
    from finance.models import Workspace, Membership, FinancialState
    from finance.domain import new_state
    from finance.security import actor_context

    fixtures = OUT / 'pool-fixtures.json'
    if kind == 'seed':
        users = {name: get_user_model().objects.create_user(username='pool_' + name)
                 for name in ('admin', 'collaborator', 'reader', 'foreign')}
        with actor_context(users['admin'].pk):
            space = Workspace.objects.create(name='Pool A ficticio', created_by=users['admin'])
            for name in ('admin', 'collaborator', 'reader'):
                Membership.objects.create(workspace=space, user=users[name], role=name)
            FinancialState.objects.create(workspace=space, document=new_state())
        with actor_context(users['foreign'].pk):
            other = Workspace.objects.create(name='Pool B ficticio', created_by=users['foreign'])
            Membership.objects.create(workspace=other, user=users['foreign'], role='admin')
            FinancialState.objects.create(workspace=other, document=new_state())
        fixtures.write_text(json.dumps({'users': {k: v.pk for k, v in users.items()},
                                       'space': str(space.pk), 'other': str(other.pk)}))
        return

    f = json.loads(fixtures.read_text())
    ids, space, other = f['users'], f['space'], f['other']
    import psycopg
    pids = []
    for mode in ('commit', 'rollback', 'commit', 'rollback'):
        with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as client:
            assert client.execute('SELECT finance_actor(), finance_import_mode()').fetchone() == (0, False)
            try:
                with client.transaction():
                    pids.append(client.execute('SELECT pg_backend_pid()').fetchone()[0])
                    client.execute("SELECT set_config('organiza.actor_id', %s, true)", [str(ids['admin'])])
                    client.execute("SELECT set_config('organiza.import_mode', 'on', true)")
                    assert client.execute('SELECT finance_actor(), finance_import_mode()').fetchone() == (ids['admin'], False)
                    if mode == 'rollback':
                        raise ValueError('fictional rollback')
            except ValueError:
                pass
            assert client.execute('SELECT finance_actor(), finance_import_mode()').fetchone() == (0, False)
    assert len(set(pids)) == 1, 'Backend reuse must be proved, not assumed'

    def current():
        with connection.cursor() as cursor:
            cursor.execute('SELECT finance_actor(), finance_import_mode()')
            return cursor.fetchone()

    with actor_context(ids['admin']):
        try:
            with actor_context(ids['reader']):
                assert current() == (ids['reader'], False)
                raise ValueError('fictional nested failure')
        except ValueError:
            pass
        assert current() == (ids['admin'], False)
    assert current() == (0, False)
    for name in (None, 'reader', 'foreign'):
        try:
            with actor_context(ids[name] if name else 0):
                FinancialState.objects.filter(workspace_id=space).update(revision=1)
        except IntegrityError:
            pass
        else:
            raise AssertionError('Unauthorized SQL write accepted')
        assert current() == (0, False)

    def browser(name):
        client = Client()
        client.force_login(get_user_model().objects.get(pk=ids[name]))
        return client

    with override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
                           READ_ONLY_MODE=False, STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage'):
        clients = {name: browser(name) for name in ids}
        def action(client, target, revision):
            return client.post(f'/api/spaces/{target}/actions', data=json.dumps({
                'action': 'account.create', 'data': {'name': 'Conta pool ficticia', 'opening_balance_cents': 10000},
                'expected_revision': revision, 'request_id': str(uuid.uuid4())}), content_type='application/json')
        assert action(clients['admin'], space, 0).status_code == 200
        connection.close()
        assert action(clients['collaborator'], space, 1).status_code == 200
        connection.close()
        assert action(clients['reader'], space, 2).status_code == 403
        assert action(clients['foreign'], space, 2).status_code == 404
        assert clients['foreign'].get(f'/api/spaces/{space}/state').status_code == 404
        assert clients['admin'].get(f'/api/spaces/{other}/state').status_code == 404
        assert clients['reader'].get(f'/api/spaces/{space}/state').json()['revision'] == 2

        def concurrent_client(name):
            try:
                client = browser(name)
                for _ in range(4):
                    response = client.get(f'/api/spaces/{space}/state')
                    assert response.status_code == (404 if name == 'foreign' else 200)
                    assert current() == (0, False)
                    connection.close()
                # Both writers race with the same revision. A reused backend
                # must not grant its preceding actor's rights to the reader.
                return action(client, space, 2).status_code
            finally:
                connections.close_all()
        connection.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = dict(zip(ids, executor.map(concurrent_client, ids)))
        assert sorted(outcomes[name] for name in ('admin', 'collaborator')) == [200, 409]
        assert outcomes['reader'] == 403 and outcomes['foreign'] == 404

    from tools.render_roles import check_guards, check_identity
    with connection.cursor() as cursor:
        check_identity(cursor, 'organiza_app', migration=False)
        check_guards(cursor)
    for statement in ('CREATE TABLE forbidden_pool_test(id integer)',
                      'SET ROLE organiza_migrator', 'TRUNCATE finance_financialstate',
                      'UPDATE finance_auditevent SET action=action',
                      'UPDATE auth_user SET is_superuser=true'):
        with psycopg.connect(os.environ['DATABASE_URL'], autocommit=True) as client:
            try:
                client.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError('Runtime excess privilege accepted')
    assert FinancialState.objects.get(workspace_id=space).revision == 3
    assert FinancialState.objects.get(workspace_id=other).revision == 0
    evidence = {'transaction_pool': True, 'pool_size': 1, 'independent_clients': len(pids),
                'distinct_backend_pids': len(set(pids)), 'context_cleared_commit_rollback_savepoint': True,
                'admin_collaborator_reader_foreign_http': True, 'concurrent_http_clients': 4,
                'concurrent_http_reads': 16, 'unauthorized_sql_write_refused': True,
                'concurrent_http_writes_by_role': outcomes,
                'ddl_escalation_truncate_history_superuser_refused': True,
                'runtime_import_bypass_refused': True, 'two_spaces_isolated': True,
                'read_isolation_enforced_by_application_not_database_rls': True,
                'neon_contacted': False}
    (OUT / 'pilot-pooling-evidence.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence))


def main():
    if ROOT != Path('/work') or not Path('/.dockerenv').exists():
        raise RuntimeError('Use the isolated Docker lab; do not run on the operational host.')
    if (ROOT / '.env').exists() or (ROOT / 'data/finance.sqlite3').exists():
        raise RuntimeError('Operational files are forbidden in the lab build context.')
    if any(os.getenv(k) for k in ('DATABASE_URL', 'DATABASE_URL_UNPOOLED', 'APP_DB_PATH')):
        raise RuntimeError('Do not pass host database settings to this disposable lab.')
    import psycopg
    from psycopg import sql
    OUT.mkdir(exist_ok=True)
    lab = OUT / ('pilot18-' + uuid.uuid4().hex[:10])
    lab.mkdir(mode=0o700)
    pg_bin = Path('/usr/lib/postgresql/18/bin')
    admin_password, app_password, migration_password = [secrets.token_urlsafe(32) for _ in range(3)]
    pwfile = lab / 'init-password'
    pwfile.write_text(admin_password)
    pwfile.chmod(0o600)
    data = lab / 'cluster'
    run('initdb18', [str(pg_bin / 'initdb'), '-D', str(data), '-U', 'organiza_test_admin',
                     '-A', 'scram-sha-256', '--pwfile=' + str(pwfile)])
    cert, key = lab / 'lab-ca.crt', lab / 'lab.key'
    run('lab-tls', ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-subj', '/CN=organiza-disposable-lab', '-addext',
                    'subjectAltName=DNS:lab.local,DNS:lab-pooler.local,IP:127.0.0.1,IP:127.0.0.2',
                    '-keyout', str(key), '-out', str(cert)])
    key.chmod(0o600)
    with (data / 'postgresql.conf').open('a') as config:
        config.write(f"\nlisten_addresses='127.0.0.1'\nport=55439\nssl=on\nssl_cert_file='{cert}'\nssl_key_file='{key}'\n")
    run('pg-start', [str(pg_bin / 'pg_ctl'), '-D', str(data), '-l', str(lab / 'postgres.log'), '-w', 'start'])
    pool = web = None
    try:
        def url(role, password, db, host='127.0.0.1'):
            return f'postgresql://{role}:{password}@{host}:55439/{db}?sslmode=verify-full&sslrootcert={cert}'
        admin_url = url('organiza_test_admin', admin_password, 'postgres')
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute('CREATE DATABASE organiza_test_lab')
        lab_url = url('organiza_test_admin', admin_password, 'organiza_test_lab')
        env = dict(os.environ, DATABASE_URL=lab_url, DATABASE_URL_UNPOOLED=lab_url,
                   APP_ENVIRONMENT='test', APP_LOCAL_MODE='true', APP_DEBUG='false', APP_READ_ONLY='false',
                   APP_REGISTRATION_MODE='open', APP_SECRET_KEY=secrets.token_urlsafe(64),
                   DJANGO_SETTINGS_MODULE='config.settings', APP_TEST_DATABASE_NAME='organiza_test_suite18',
                   APP_DATABASE_SSLROOTCERT=str(cert), PG_BIN_DIR=str(pg_bin), AGE_BIN_DIR='/usr/bin')
        envfile = lab / 'fixture-environment.json'
        envfile.write_text(json.dumps({k: env[k] for k in ('DATABASE_URL', 'DATABASE_URL_UNPOOLED',
                                                         'PG_BIN_DIR', 'AGE_BIN_DIR')}))
        envfile.chmod(0o600)
        run('django-postgres18', [sys.executable, 'manage.py', 'test', 'finance', '--noinput', '-v', '1'], env, 600)
        run('tools-unit18', [sys.executable, '-m', 'unittest', 'tools.test_postgres_tools',
                            'tools.test_neon_role_passwords', '-v'], env)
        run('migration18-current', [sys.executable, 'tools/verify_postgres_migration.py', '--env-file', str(envfile)], env, 600)
        run('migration18-legacy', [sys.executable, 'tools/verify_postgres_migration.py', '--env-file', str(envfile), '--legacy-source'], env, 600)
        run('web18-redeploy', [sys.executable, 'tools/verify_postgres_web.py', '--env-file', str(envfile)], env, 300)
        with psycopg.connect(admin_url, autocommit=True) as admin:
            for role, password in (('organiza_app', app_password), ('organiza_migrator', migration_password)):
                admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
            admin.execute('CREATE DATABASE organiza_test_pool18')
        with psycopg.connect(url('organiza_test_admin', admin_password, 'organiza_test_pool18')) as admin:
            admin.execute('REVOKE CREATE, TEMPORARY ON DATABASE organiza_test_pool18 FROM PUBLIC')
            admin.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
            admin.execute('GRANT USAGE ON SCHEMA public TO organiza_app, organiza_migrator')
            admin.execute('GRANT CREATE ON SCHEMA public TO organiza_migrator')
        auth = lab / 'pool-users.txt'
        auth.write_text(f'"organiza_app" "{app_password}"\n')
        auth.chmod(0o600)
        conf = lab / 'pgbouncer.ini'
        conf.write_text(f'''[databases]
organiza_test_pool18 = host=127.0.0.1 port=55439 dbname=organiza_test_pool18
[pgbouncer]
listen_addr = 127.0.0.2
listen_port = 55439
unix_socket_dir = {lab}
auth_type = scram-sha-256
auth_file = {auth}
pool_mode = transaction
default_pool_size = 1
reserve_pool_size = 0
max_client_conn = 40
server_reset_query_always = 0
client_tls_sslmode = require
client_tls_ca_file = {cert}
client_tls_cert_file = {cert}
client_tls_key_file = {key}
server_tls_sslmode = verify-full
server_tls_ca_file = {cert}
logfile = {lab / 'pool.log'}
pidfile = {lab / 'pool.pid'}
''')
        pool = subprocess.Popen(['pgbouncer', str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pooled_url = url('organiza_app', app_password, 'organiza_test_pool18', 'lab-pooler.local')
        direct_url = url('organiza_migrator', migration_password, 'organiza_test_pool18', 'lab.local')
        for _ in range(40):
            try:
                with psycopg.connect(pooled_url, connect_timeout=1):
                    break
            except psycopg.OperationalError:
                time.sleep(.25)
        else:
            raise RuntimeError('Isolated PgBouncer did not start')
        maintenance = dict(env, DATABASE_URL=pooled_url, DATABASE_URL_UNPOOLED=direct_url)
        run('explicit-maintenance18', [sys.executable, 'tools/migrate_schema.py', '--render-roles'], maintenance)
        run('pool-seed', [sys.executable, __file__, 'seed'], dict(maintenance, APP_USE_DIRECT_DATABASE='true'))
        runtime = dict(env, DATABASE_URL=pooled_url)
        runtime.pop('DATABASE_URL_UNPOOLED')
        run('pool-isolation18', [sys.executable, __file__, 'pool'], runtime)
        production = dict(runtime, APP_ENVIRONMENT='production', APP_LOCAL_MODE='false',
                          APP_REGISTRATION_MODE='approval', APP_READ_ONLY='true',
                          APP_ALLOWED_HOSTS='127.0.0.1', PORT='58080', PIP_DISABLE_PIP_VERSION_CHECK='1')
        run('runtime-readiness18', [sys.executable, 'tools/check_runtime_database.py'], production)
        run('deployment-package18', [sys.executable, 'tools/verify_deployment_preparation.py'], production)
        run('linux-build18', ['bash', 'build.sh'], production)
        with psycopg.connect(direct_url) as manager:
            before = manager.execute('SELECT count(*) FROM django_migrations').fetchone()
        logfile = (OUT / 'gunicorn18.log').open('wb')
        web = subprocess.Popen(['bash', 'start-render.sh'], cwd=ROOT,
                               env=dict(production, DATABASE_URL_UNPOOLED='fictional-secret-must-be-removed'),
                               stdout=logfile, stderr=logfile)
        for _ in range(80):
            try:
                with urlopen(Request('http://127.0.0.1:58080/api/health', headers={'X-Forwarded-Proto': 'https'}), timeout=1) as response:
                    assert response.status == 200 and json.load(response)['application'] == 'organiza'
                break
            except OSError:
                if web.poll() is not None:
                    raise RuntimeError('Gunicorn startup failed')
                time.sleep(.25)
        else:
            raise RuntimeError('Gunicorn health timeout')
        time.sleep(.5)
        process_ids = [web.pid]
        for entry in Path('/proc').iterdir():
            if entry.name.isdigit():
                try:
                    if f'PPid:\t{web.pid}\n' in (entry / 'status').read_text():
                        process_ids.append(int(entry.name))
                except (FileNotFoundError, PermissionError):
                    pass
        assert len(process_ids) >= 2
        for pid in process_ids:
            process_env = Path(f'/proc/{pid}/environ').read_bytes()
            assert b'DATABASE_URL_UNPOOLED=' not in process_env and b'fictional-secret-must-be-removed' not in process_env
        with psycopg.connect(direct_url) as manager:
            assert manager.execute('SELECT count(*) FROM django_migrations').fetchone() == before
        versions = {name: subprocess.check_output(args, text=True).splitlines()[0] for name, args in {
            'postgres': [str(pg_bin / 'postgres'), '--version'], 'pg_dump': [str(pg_bin / 'pg_dump'), '--version'],
            'pgbouncer': ['pgbouncer', '--version'], 'python': [sys.executable, '--version']}.items()}
        evidence = {'versions': versions, 'full_django_suite_passed': True, 'fixture_import_current_and_legacy': True,
                    'encrypted_restore_pg18': True, 'transaction_pool_passed': True, 'linux_build_and_gunicorn_health': True,
                    'runtime_master_and_workers_without_migration_secret': len(process_ids),
                    'start_does_not_run_migrations': True, 'no_host_mounts_or_external_network': True,
                    'neon_tested': False, 'render_tested': False, 'production_data_used': False}
        (OUT / 'pilot18-evidence.json').write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2), flush=True)
    finally:
        for process in (web, pool):
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=20)
        run('pg-stop', [str(pg_bin / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'])


if __name__ == '__main__':
    if ROOT != Path('/work') or not Path('/.dockerenv').exists():
        raise SystemExit('Only the isolated Docker lab may run these workers.')
    worker(sys.argv[1]) if len(sys.argv) > 1 else main()
