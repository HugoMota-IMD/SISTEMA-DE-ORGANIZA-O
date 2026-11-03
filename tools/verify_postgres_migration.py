"""Local-only fictitious SQLite→PostgreSQL rehearsal and encrypted restore.

Requires a disposable loopback PostgreSQL server with CREATEDB and age tools.
Never accepts a remote PostgreSQL host or the official SQLite source. Temporary
databases are uniquely named organiza_test_* and retained for local inspection.
"""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid
from urllib.parse import unquote, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.postgres_common import binary, direct_url, load_env_file, management_error


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)


def sha(value):
    return hashlib.sha256(stable(value).encode()).hexdigest()


def worker_environment(base, url=None, source=None):
    env = dict(base, APP_LOCAL_MODE='true', APP_ENVIRONMENT='local', APP_DEBUG='false',
               APP_ALLOWED_HOSTS='localhost,127.0.0.1,testserver', APP_REGISTRATION_MODE='open')
    if url:
        env.update(DATABASE_URL=url, DATABASE_URL_UNPOOLED=url)
    else:
        env.pop('DATABASE_URL', None)
        env.pop('DATABASE_URL_UNPOOLED', None)
    if source:
        env['APP_DB_PATH'] = str(source)
    return env


def child_call(arguments, env, *, expected=0):
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), *arguments], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=180)
    if result.returncode != expected:
        # Suppress traceback/connection detail: it might contain a DSN or row.
        raise RuntimeError('Um subprocesso do ensaio falhou. Etapa: ' + arguments[1] + '; nenhum dado sensível foi emitido.')
    lines = [line for line in result.stdout.splitlines() if line.startswith('{')]
    return json.loads(lines[-1]) if lines else {}


def fixture(path, directory):
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    from django.apps import apps
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from django.core.management import call_command
    from django.test import Client
    from django.utils import timezone
    from finance.domain import add_months
    call_command('migrate', verbosity=0, stdout=StringIO())
    User = get_user_model()
    password = os.environ['ORGANIZA_TEST_PASSWORD']
    admin = User.objects.create_user(username='migration_fictitious_admin', password=password, is_staff=True, is_superuser=True)
    collaborator = User.objects.create_user(username='migration_fictitious_collab', password=password)
    reader = User.objects.create_user(username='migration_fictitious_reader', password=password)
    other = User.objects.create_user(username='migration_fictitious_other', password=password)
    group = Group.objects.create(name='Fictitious migration group')
    permission = Permission.objects.order_by('pk').first()
    group.permissions.add(permission)
    collaborator.groups.add(group)
    reader.user_permissions.add(permission)
    clients = {}
    for name, user in [('admin', admin), ('collaborator', collaborator), ('reader', reader), ('other', other)]:
        client = Client()
        client.force_login(user)
        clients[name] = client

    def post(client, url, data, expected=200):
        response = client.post(url, data=json.dumps(data), content_type='application/json')
        if response.status_code != expected:
            raise RuntimeError('Falha na preparação fictícia: HTTP ' + str(response.status_code))
        return response.json()

    space = post(clients['admin'], '/api/spaces', {'name': 'Fictitious migration household'}, 201)['space']['id']
    other_space = post(clients['other'], '/api/spaces', {'name': 'Other fictitious isolated space'}, 201)['space']['id']
    post(clients['admin'], f'/api/spaces/{space}/members', {'username': collaborator.username, 'role': 'collaborator'})
    post(clients['admin'], f'/api/spaces/{space}/members', {'username': reader.username, 'role': 'reader'})

    def state():
        response = clients['admin'].get(f'/api/spaces/{space}/state')
        if response.status_code != 200:
            raise RuntimeError('Estado fictício indisponível.')
        return response.json()

    def action(name, data):
        return post(clients['admin'], f'/api/spaces/{space}/actions', {
            'action': name, 'data': data, 'request_id': str(uuid.uuid4()), 'expected_revision': state()['revision']})

    today = timezone.localdate()
    account = action('account.create', {'name': 'Fictitious migration bank', 'opening_balance_cents': 500000, 'reference_date': today.isoformat()})['result']['id']
    wallet = action('account.create', {'name': 'Fictitious wallet', 'reference_date': today.isoformat()})['result']['id']
    card = action('card.create', {'name': 'Fictitious migration card', 'account_id': account, 'closing_day': 10, 'due_day': 25, 'limit_cents': 500000})['result']['id']
    category = state()['categories'][0]['id']
    action('entry.create', {'kind': 'income', 'description': 'Fictitious received income', 'amount_cents': 50000, 'method': 'pix', 'account_id': account, 'paid': True, 'paid_on': today.isoformat()})
    purchase = action('entry.create', {'kind': 'expense', 'description': 'Fictitious previous installment debt', 'merchant': 'Fictitious merchant', 'person_id': admin.pk,
                                     'amount_cents': 100000, 'method': 'pix', 'account_id': account, 'category_id': category,
                                     'installments': 3, 'paid_installments': 1, 'due_date': add_months(today, -1).isoformat()})
    obligations = sorted((row for row in purchase['state']['obligations'] if row['entry_id'] == purchase['result']['id']), key=lambda row: row['installment'])
    pending = obligations[1]
    action('obligation.pay', {'obligation_id': pending['id'], 'account_id': account, 'mode': 'partial', 'amount_cents': 15000})
    paid = action('obligation.pay', {'obligation_id': pending['id'], 'account_id': account, 'mode': 'full'})
    action('payment.reverse', {'payment_id': paid['result']['payment']['id'], 'reason': 'Fictitious reversal preserved by migration', 'occurred_on': today.isoformat()})
    action('obligation.adjust', {'obligation_id': pending['id'], 'kind': 'fee', 'amount_cents': 1000, 'reason': 'Fictitious adjustment'})
    credit = action('entry.create', {'kind': 'expense', 'description': 'Fictitious credit purchase', 'amount_cents': 90000,
                                   'method': 'credit', 'card_id': card, 'category_id': category, 'installments': 3, 'due_date': today.isoformat()})
    first_credit = next(row for row in credit['state']['obligations'] if row['entry_id'] == credit['result']['id'])
    action('invoice.pay', {'invoice_id': first_credit['invoice_id'], 'mode': 'partial', 'amount_cents': 12000, 'account_id': account})
    action('invoice.pay', {'invoice_id': first_credit['invoice_id'], 'mode': 'full', 'account_id': account})
    action('entry.create', {'kind': 'transfer', 'description': 'Fictitious own transfer', 'amount_cents': 5000, 'account_id': account, 'destination_account_id': wallet, 'paid_on': today.isoformat()})
    action('entry.create', {'kind': 'expense', 'description': 'Fictitious recurrence', 'amount_cents': 2000, 'account_id': account,
                          'due_date': today.isoformat(), 'recurrence': {'frequency': 'monthly', 'end_date': add_months(today, 3).isoformat()}})
    action('budget.set', {'category_id': category, 'month': today.strftime('%Y-%m'), 'amount_cents': 100000})
    try:
        Access = apps.get_model('finance', 'UserAccessEvent')
    except LookupError:
        Access = None
    if Access:
        Access.objects.create(actor=admin, subject=reader, before_active=False, after_active=True)
    # Exercise real password login, preserving its session and throttle records.
    client = Client()
    login = post(client, '/api/auth/login', {'username': admin.username, 'password': password})
    failed = Client().post('/api/auth/login', data=json.dumps({
        'username': 'migration_fictitious_missing', 'password': password,
    }), content_type='application/json')
    assert failed.status_code == 401
    snapshot = client.get(f'/api/spaces/{space}/state').json()
    metadata = {'space': space, 'other_space': other_space, 'admin_id': admin.pk,
                'account': account, 'obligation': pending['id'], 'max_user_id': User.objects.order_by('-pk').first().pk,
                'session_key': client.cookies[settings.SESSION_COOKIE_NAME].value,
                'api_state_digest': sha(snapshot), 'as_of': today.isoformat()}
    (directory / 'fixture-private.json').write_text(json.dumps(metadata), encoding='utf-8')
    (directory / 'fictitious-source-marker.json').write_text(json.dumps({
        'kind': 'organiza-fictitious-rehearsal', 'source': path.name,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    }), encoding='utf-8')
    print(json.dumps({'prepared': True, 'users': User.objects.count(), 'spaces': 2, 'api_state_digest': metadata['api_state_digest']}))


def read_pg(directory, exercise=False):
    from tools.postgres_common import prepare_django
    prepare_django()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db import connections
    from django.test import Client
    metadata = json.loads((directory / 'fixture-private.json').read_text())
    User = get_user_model()
    password = os.environ['ORGANIZA_TEST_PASSWORD']
    old_session = Client()
    old_session.cookies[settings.SESSION_COOKIE_NAME] = metadata['session_key']
    assert old_session.get('/api/session').json()['user']['id'] == metadata['admin_id']
    original_state = old_session.get(f"/api/spaces/{metadata['space']}/state").json()
    if not exercise:
        print(json.dumps({'old_session_preserved': True, 'api_state_digest': sha(original_state)}))
        return
    assert sha(original_state) == metadata['api_state_digest']
    assert old_session.login(username='migration_fictitious_admin', password=password)
    new_user = User.objects.create_user(username='migration_fictitious_sequence_check', password=password)
    assert new_user.pk > metadata['max_user_id']
    collab, reader, other = Client(), Client(), Client()
    assert collab.login(username='migration_fictitious_collab', password=password)
    assert reader.login(username='migration_fictitious_reader', password=password)
    assert other.login(username='migration_fictitious_other', password=password)
    path = f"/api/spaces/{metadata['space']}/actions"
    assert reader.post(path, data=json.dumps({'action': 'account.create', 'data': {'name': 'Rejected'}, 'request_id': str(uuid.uuid4()), 'expected_revision': original_state['revision']}), content_type='application/json').status_code == 403
    assert other.get(f"/api/spaces/{metadata['space']}/state").status_code == 404
    import concurrent.futures
    import threading
    barrier = threading.Barrier(2)
    payloads = [{'action': 'obligation.pay', 'data': {'obligation_id': metadata['obligation'], 'account_id': metadata['account'], 'mode': 'full'},
                 'expected_revision': original_state['revision'], 'request_id': str(uuid.uuid4())} for _ in range(2)]
    def simultaneous(index):
        try:
            client = Client()
            client.cookies.update((old_session if index == 0 else collab).cookies)
            barrier.wait(timeout=10)
            response = client.post(path, data=json.dumps(payloads[index]), content_type='application/json')
            return response.status_code, response.json()
        finally:
            connections.close_all()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(simultaneous, range(2)))
    statuses = [value[0] for value in responses]
    assert sorted(statuses) == [200, 409], statuses
    winner = statuses.index(200)
    winner_client = old_session if winner == 0 else collab
    replay = winner_client.post(path, data=json.dumps(payloads[winner]), content_type='application/json')
    assert replay.status_code == 200 and replay.json()['duplicate']
    # Retain the imported source session for a cross-process restore check.
    final = old_session.get(f"/api/spaces/{metadata['space']}/state").json()
    print(json.dumps({'old_session_preserved': True, 'password_login_preserved': True, 'sequences_valid': True,
                      'roles_and_isolation': True, 'concurrent_statuses': statuses, 'idempotent_retry': True,
                      'api_state_digest': sha(final)}))


def worker(args):
    source = Path(args.source).resolve() if args.source else None
    directory = Path(args.directory).resolve()
    if args.worker == 'prepare':
        fixture(source, directory)
    elif args.worker == 'schema':
        from tools.postgres_common import prepare_django
        prepare_django()
        from django.core.management import call_command
        call_command('migrate', verbosity=0, stdout=StringIO())
        print(json.dumps({'schema_ready': True}))
    elif args.worker in ('import', 'failure'):
        from tools.migrate_sqlite_postgres import migrate
        def fail(table):
            if table == 'finance_operation':
                raise RuntimeError('Fictitious injected import failure')
        if args.worker == 'failure':
            try:
                migrate(source, after_table=fail)
            except RuntimeError:
                from django.db import connection
                with connection.cursor() as cursor:
                    for table in ('auth_user', 'finance_workspace', 'finance_financialstate', 'finance_auditevent', 'finance_operation'):
                        cursor.execute('SELECT COUNT(*) FROM ' + table)
                        assert cursor.fetchone()[0] == 0
                print(json.dumps({'atomic_failure_no_partial_records': True}))
            else:
                raise RuntimeError('Injected failure did not occur')
        else:
            metadata = json.loads((directory / 'fixture-private.json').read_text())
            print(json.dumps(migrate(source, as_of=metadata['as_of'])))
    elif args.worker == 'exercise':
        read_pg(directory, exercise=True)
    elif args.worker == 'read':
        read_pg(directory)


def complete_postgres_digest(url):
    import psycopg
    from psycopg import sql
    with psycopg.connect(url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TIME ZONE 'UTC'")
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")
            tables = [row[0] for row in cursor.fetchall()]
            result = {}
            for table in tables:
                cursor.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table)))
                columns = [column[0] for column in cursor.description]
                result[table] = sorted([dict(zip(columns, row)) for row in cursor.fetchall()], key=stable)
            cursor.execute("SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema='public' ORDER BY sequence_name")
            sequences = [row[0] for row in cursor.fetchall()]
            for name in sequences:
                cursor.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier(name)))
                result['sequence:' + name] = cursor.fetchone()
    return sha(result)


def main(args):
    load_env_file(args.env_file)
    original_url = direct_url()
    parsed = urlsplit(original_url)
    if parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('O ensaio só pode criar bancos fictícios em PostgreSQL loopback; nenhuma nuvem será acessada.')
    import psycopg
    from psycopg import sql
    tag = uuid.uuid4().hex[:12]
    directory = ROOT / 'test-results' / ('postgres-migration-' + tag)
    directory.mkdir(parents=True)
    source = directory / 'source-fictitious.sqlite3'
    names = {kind: f'organiza_test_{tag}_{kind}' for kind in ('import', 'fail', 'restore')}
    urls = {kind: urlunsplit((parsed.scheme, parsed.netloc, '/' + name, parsed.query, '')) for kind, name in names.items()}
    with psycopg.connect(original_url, autocommit=True, connect_timeout=10) as admin:
        for name in names.values():
            assert name.startswith('organiza_test_' + tag)
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    common = dict(os.environ, APP_SECRET_KEY=secrets.token_urlsafe(64), ORGANIZA_TEST_PASSWORD=secrets.token_urlsafe(30))
    local_env = worker_environment(common, source=source)
    source_result = child_call(['--worker', 'prepare', '--source', str(source), '--directory', str(directory)], local_env)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    envs = {kind: worker_environment(common, url=url) for kind, url in urls.items()}
    for kind in ('import', 'fail'):
        child_call(['--worker', 'schema', '--directory', str(directory)], envs[kind])
    fail_result = child_call(['--worker', 'failure', '--source', str(source), '--directory', str(directory)], envs['fail'])
    imported = child_call(['--worker', 'import', '--source', str(source), '--directory', str(directory)], envs['import'])
    replay = child_call(['--worker', 'import', '--source', str(source), '--directory', str(directory)], envs['import'])
    assert replay['result'] == 'already_imported' and replay['duplicate_prevented']
    exercised = child_call(['--worker', 'exercise', '--directory', str(directory)], envs['import'])
    # Generate a disposable age identity. Never print private key material.
    identity = directory / 'test-age-identity.txt'
    generated = subprocess.run([binary('age-keygen'), '--output', str(identity)], capture_output=True, text=True, check=True)
    recipient = subprocess.check_output([binary('age-keygen'), '-y', str(identity)], text=True).strip()
    from tools.postgres_backup import backup, empty_database, restore
    os.environ.update(envs['import'], AGE_RECIPIENT=recipient, AGE_IDENTITY_FILE=str(identity))
    encrypted = directory / 'fictitious-postgres.dump.age'
    complete_before_backup = complete_postgres_digest(urls['import'])
    backup_result = backup(encrypted)
    overwrite_refused = False
    try:
        backup(encrypted)
    except RuntimeError:
        overwrite_refused = True
    assert overwrite_refused
    os.environ.update(envs['restore'], AGE_IDENTITY_FILE=str(identity))
    # Wrong key and corrupted ciphertext must not create even partial tables.
    wrong_identity = directory / 'test-wrong-age-identity.txt'
    subprocess.run([binary('age-keygen'), '--output', str(wrong_identity)], capture_output=True, text=True, check=True)
    try:
        restore(encrypted, confirm_empty=True, identity=str(wrong_identity))
    except RuntimeError:
        wrong_key_refused = True
    else:
        raise RuntimeError('Wrong age identity unexpectedly accepted')
    empty_database(urls['restore'])
    damaged = directory / 'fictitious-corrupted.dump.age'
    content = bytearray(encrypted.read_bytes())
    content[-1] ^= 1
    damaged.write_bytes(content)
    damaged.with_name(damaged.name + '.json').write_bytes(encrypted.with_name(encrypted.name + '.json').read_bytes())
    try:
        restore(damaged, confirm_empty=True)
    except RuntimeError:
        corrupted_backup_refused = True
    else:
        raise RuntimeError('Corrupted backup unexpectedly accepted')
    empty_database(urls['restore'])
    restored = restore(encrypted, confirm_empty=True)
    assert complete_postgres_digest(urls['restore']) == complete_before_backup
    restored_read = child_call(['--worker', 'read', '--directory', str(directory)], envs['restore'])
    assert restored_read['api_state_digest'] == exercised['api_state_digest']
    restore_nonempty_refused = False
    try:
        restore(encrypted, confirm_empty=True)
    except RuntimeError:
        restore_nonempty_refused = True
    assert restore_nonempty_refused
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    evidence = {'sqlite_to_postgres_reconciled': imported['records_equal'],
                'model_counts': imported['model_counts'], 'financial_snapshots_and_60_month_projection_equal': imported['financial_snapshots_and_60_month_projection_equal'],
                'password_hashes_preserved': imported['password_hashes_preserved'], 'existing_session_preserved': exercised['old_session_preserved'],
                'password_login': exercised['password_login_preserved'], 'identifier_sequences': exercised['sequences_valid'],
                'idempotent_import_replay': replay['duplicate_prevented'], 'atomic_failure_no_partial_records': fail_result['atomic_failure_no_partial_records'],
                'permissions_and_isolation': exercised['roles_and_isolation'], 'concurrent_statuses': exercised['concurrent_statuses'],
                'idempotent_payment_retry': exercised['idempotent_retry'], 'encrypted_dump_created': backup_result['format'] == 'postgres-custom+age',
                'encrypted_backup_restored_in_separate_database': restored['single_transaction'],
                'restored_financial_state_and_session_equal': True, 'backup_overwrite_refused': overwrite_refused,
                'complete_postgres_tables_and_sequences_restored_equal': True,
                'wrong_decryption_key_refused_without_partial_schema': wrong_key_refused,
                'corrupted_encrypted_backup_refused_without_partial_schema': corrupted_backup_refused,
                'restore_into_nonempty_refused': restore_nonempty_refused, 'source_sqlite_unchanged': True,
                'fictitious_data_only': True, 'official_database_accessed': False, 'external_resources_created': False,
                'local_databases_retained_for_inspection': list(names.values())}
    (ROOT / 'test-results' / 'postgres-migration-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file')
    parser.add_argument('--worker', choices=['prepare', 'schema', 'import', 'failure', 'exercise', 'read'])
    parser.add_argument('--source')
    parser.add_argument('--directory')
    args = parser.parse_args()
    try:
        worker(args) if args.worker else main(args)
    except Exception as error:
        print(json.dumps({'error': management_error(error)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)
