"""Exercise two fresh local WSGI releases against a unique, fictitious PostgreSQL DB."""
import argparse
from contextlib import contextmanager
from datetime import datetime
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from time import monotonic, sleep
from urllib import request
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.postgres_common import direct_url, load_env_file
from tools.render_roles import check_guards, check_identity, grant_runtime


@contextmanager
def release(directory, env):
    directory.mkdir()
    for folder in ('config', 'finance', 'templates', 'static'):
        shutil.copytree(ROOT / folder, directory / folder, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'manage.py', directory)
    (directory / 'tools').mkdir()
    shutil.copy2(ROOT / 'tools/migrate_schema.py', directory / 'tools')
    for command in (['tools/migrate_schema.py'], ['manage.py', 'collectstatic', '--noinput']):
        subprocess.run([sys.executable, *command], cwd=directory, env=env, check=True,
                       capture_output=True, timeout=60)
    app_name = urlsplit(env['DATABASE_URL']).username
    manager_url = env['DATABASE_URL_UNPOOLED']
    with psycopg.connect(manager_url) as manager, manager.cursor() as cursor:
        check_identity(cursor, urlsplit(manager_url).username, migration=True)
        grant_runtime(cursor, app_name)
    with psycopg.connect(env['DATABASE_URL']) as app, app.cursor() as cursor:
        check_identity(cursor, app_name, migration=False)
        check_guards(cursor)
        cursor.execute("SELECT set_config('organiza.import_mode','on',true)")
        cursor.execute("SELECT public.finance_import_mode()")
        assert cursor.fetchone() == (False,)
        for operation in ('CREATE TABLE public.unauthorized (id int)',
                          'ALTER TABLE finance_auditevent DISABLE TRIGGER USER',
                          'TRUNCATE finance_auditevent', 'DELETE FROM finance_auditevent',
                          'UPDATE auth_user SET is_superuser=true', 'SELECT * FROM django_migrations',
                          sql.SQL('SET ROLE {}').format(sql.Identifier(urlsplit(manager_url).username))):
            try:
                with app.transaction():
                    cursor.execute(operation)
                    raise AssertionError('A role web recebeu um privilégio indevido.')
            except psycopg.errors.InsufficientPrivilege:
                pass
    assert (directory / 'staticfiles/app.js').is_file()
    entrypoint = """
from waitress import create_server
from config.wsgi import application
server = create_server(application, host='127.0.0.1', port=0)
print(server.effective_port, flush=True)
server.run()
"""
    port_file = directory / 'test-port.txt'
    with port_file.open('w') as port_output:
        runtime_env = {key: value for key, value in env.items() if key != 'DATABASE_URL_UNPOOLED'}
        process = subprocess.Popen([sys.executable, '-c', entrypoint], cwd=directory, env=runtime_env,
                                   stdin=subprocess.DEVNULL, stdout=port_output, stderr=subprocess.DEVNULL)
        try:
            deadline = monotonic() + 20
            while not port_file.read_text().strip():
                if process.poll() is not None or monotonic() >= deadline:
                    raise RuntimeError('A versão fictícia não iniciou em loopback.')
                sleep(0.1)
            yield 'http://127.0.0.1:' + str(int(port_file.read_text().strip()))
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=15)


def main(env_file):
    load_env_file(env_file)
    parsed = urlsplit(direct_url())
    if parsed.hostname != '127.0.0.1' or parsed.username != 'organiza_test_admin':
        raise RuntimeError('O ensaio exige o administrador fictício do cluster de loopback.')
    tag = uuid.uuid4().hex[:12]
    name = 'organiza_test_web_' + tag
    roles = {'app': 'organiza_test_app_' + tag, 'manager': 'organiza_test_mgr_' + tag}
    urls = {}
    with psycopg.connect(parsed.geturl(), autocommit=True, connect_timeout=10) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        for kind, role in roles.items():
            credential = secrets.token_urlsafe(32)
            admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(credential)))
            urls[kind] = parsed._replace(netloc=f'{role}:{credential}@127.0.0.1:{parsed.port}', path='/'+name).geturl()
    with psycopg.connect(parsed._replace(path='/'+name).geturl()) as owner:
        owner.execute(sql.SQL('REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
        owner.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        owner.execute(sql.SQL('GRANT CREATE, USAGE ON SCHEMA public TO {}').format(sql.Identifier(roles['manager'])))
        owner.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(roles['app'])))
    directory = ROOT / 'test-results' / ('web-redeploy-' + tag)
    directory.mkdir()
    password = secrets.token_urlsafe(32)
    env = dict(os.environ, DATABASE_URL=urls['app'], DATABASE_URL_UNPOOLED=urls['manager'], APP_ENVIRONMENT='test',
               APP_DEBUG='false', APP_LOCAL_MODE='true', APP_REGISTRATION_MODE='approval',
               APP_PRIVATE_HTTPS_ORIGIN='', APP_READ_ONLY='false', APP_ALLOWED_HOSTS='127.0.0.1',
               APP_SECRET_KEY=secrets.token_urlsafe(64), DJANGO_SETTINGS_MODULE='config.settings')
    browser = request.build_opener(request.ProxyHandler({}), request.HTTPCookieProcessor(CookieJar()))
    csrf = None

    def api(path, payload=None, expected=200):
        headers = {'Accept': 'application/json'}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers.update({'X-CSRFToken': csrf, 'Content-Type': 'application/json', 'Origin': address})
        with browser.open(request.Request(address + path, data=body, headers=headers), timeout=15) as response:
            assert response.status == expected, (path, response.status)
            return json.load(response)

    with release(directory / 'first', env) as address:
        schema = [sys.executable, 'manage.py', 'createsuperuser', '--noinput', '--username', 'fictitious_admin',
                  '--email', 'fixture@example.invalid']
        subprocess.run(schema, cwd=directory / 'first', env={**env, 'DATABASE_URL': urls['manager'], 'DJANGO_SUPERUSER_PASSWORD': password},
                       capture_output=True, check=True, timeout=30)
        first_instance = api('/api/health')['instance_id']
        csrf = api('/api/session')['csrf_token']
        pending = api('/api/auth/register', {'username': 'fictitious_pending', 'password': password}, 202)
        assert pending['registration_pending'] and api('/api/session')['user'] is None
        csrf = api('/api/auth/login', {'username': 'fictitious_admin', 'password': password})['csrf_token']
        space = api('/api/spaces', {'name': 'Fictitious redeploy'}, 201)['space']['id']
        base = '/api/spaces/' + space
        user = next(row for row in api('/api/technical/users')['users'] if row['username'] == 'fictitious_pending')
        assert api('/api/technical/users/' + str(user['id']) + '/status', {'is_active': True})['changed']
        api(base + '/members', {'username': user['username'], 'role': 'reader'})

        def action(kind, data):
            revision = api(base + '/state')['revision']
            return api(base + '/actions', {'action': kind, 'data': data, 'expected_revision': revision,
                                          'request_id': str(uuid.uuid4())})

        today = datetime.now(ZoneInfo('America/Manaus')).date().isoformat()
        account = action('account.create', {'name': 'Fictitious bank', 'opening_balance_cents': 100000,
                                             'reference_date': today})['result']['id']
        purchase = action('entry.create', {'kind': 'expense', 'description': 'Fictitious purchase',
                                          'amount_cents': 15000, 'installments': 3, 'method': 'pix',
                                          'account_id': account, 'due_date': today})
        first = next(item for item in purchase['state']['obligations'] if item['installment'] == 1)
        action('obligation.pay', {'mode': 'full', 'obligation_id': first['id'], 'account_id': account})
        snapshot = api(base + '/state?months=60')
        assert snapshot['balance_cents'] == 95000 and snapshot['debt_cents'] == 10000
    with release(directory / 'second', env) as address:
        assert api('/api/health')['instance_id'] != first_instance
        assert api('/api/session')['user']['username'] == 'fictitious_admin'
        assert api(base + '/state?months=60') == snapshot
    assert not list(directory.rglob('*.sqlite3')) and not list(directory.rglob('.env'))
    evidence = {'two_distinct_local_releases': True, 'engine': 'PostgreSQL', 'http_server': 'Waitress',
                'distinct_nonowner_login_roles': True, 'runtime_ddl_and_history_changes_denied': True,
                'runtime_import_flag_denied': True, 'technical_approval_and_membership_with_runtime_role': True,
                'fresh_static_builds': 2, 'schema_startup_runs': 2, 'approval_202_without_session': True,
                'real_http_csrf_login': True, 'authenticated_session_retained': True,
                'full_snapshot_equal_including_audit_and_60_months': True,
                'balance_cents': 95000, 'debt_cents': 10000, 'fixture_only': True,
                'render_or_neon_contacted': False, 'tls_or_cold_start_measured': False}
    (ROOT / 'test-results/postgres-web-redeploy-evidence.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    main(parser.parse_args().env_file)
