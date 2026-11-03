"""Exercise real HTTP/HTTPS transport with an isolated fictitious SQLite database.

For HTTPS, configure only the designated temporary Tailscale Serve handler before
running this script. This script never changes Serve, Funnel or the official DB.
Certificates are validated normally. No passwords, tokens or financial rows are
printed. The temporary backend is stopped on exit.
"""
import argparse
import concurrent.futures
import http.cookiejar
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


class Session:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None
        self.headers = None

    def call(self, path, payload=None, *, token=True, origin=None, extra_headers=None):
        headers = {'Accept': 'application/json'}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
            if token:
                headers['X-CSRFToken'] = self.csrf or ''
            headers['Origin'] = origin or self.base
        headers.update(extra_headers or {})
        request = urllib.request.Request(self.base + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.headers = response.headers
            content = response.read()
            try:
                body = json.loads(content)
            except (ValueError, UnicodeDecodeError):
                body = {'non_json_response': True}
            if 'csrf_token' in body:
                self.csrf = body['csrf_token']
            return response.status, body


def expect(status_and_body, status=200):
    actual, body = status_and_body
    if actual != status:
        # Never include a response with account details, cookies or credentials.
        raise AssertionError(f'Expected HTTP {status}, received HTTP {actual}')
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8771')
    parser.add_argument('--port', type=int, default=8771)
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.base_url)
    private = parsed.scheme == 'https'
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        parser.error('Use only an origin without credentials, path, query or fragment.')
    if private:
        if not (parsed.hostname or '').endswith('.ts.net'):
            parser.error('HTTPS verification is restricted to the explicitly configured Tailscale hostname.')
    elif parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        parser.error('HTTP verification is restricted to localhost.')
    if not 1024 <= args.port <= 65535 or args.port == 8765:
        parser.error('Use a separate unprivileged test port, never the official port 8765.')
    local = f'http://127.0.0.1:{args.port}'
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            raise SystemExit('The test port is occupied; no process was stopped.')
    results = ROOT / 'test-results'
    results.mkdir(exist_ok=True)
    tag = uuid.uuid4().hex
    test_db = results / f'private-access-{tag}.sqlite3'
    origin = args.base_url.rstrip('/') if private else 'https://organiza-fictitious.test.ts.net'
    env = dict(os.environ, APP_DB_PATH=str(test_db), APP_SECRET_KEY=secrets.token_urlsafe(64), APP_PORT=str(args.port),
               APP_LOCAL_MODE='true', APP_PRIVATE_HTTPS_ORIGIN=origin,
               APP_ALLOWED_HOSTS=','.join(['localhost', '127.0.0.1', parsed.hostname]), APP_CSRF_TRUSTED_ORIGINS=origin)
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env, check=True, capture_output=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    server = None
    checks = []

    def start():
        process = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError('The isolated backend exited before becoming ready.')
            try:
                health = expect(Session(local).call('/api/health'))
                if health.get('application') == 'organiza':
                    return process
            except (OSError, AssertionError):
                time.sleep(.1)
        process.terminate()
        process.wait(timeout=10)
        raise AssertionError('The isolated backend did not become ready.')

    def stop(process):
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        for _ in range(50):
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', args.port)) != 0:
                    return
            time.sleep(.1)
        raise AssertionError('The isolated backend port remained open after terminating its subprocess.')

    def backend_pid():
        metadata = json.loads((ROOT / 'data' / 'runtime' / f'server-{args.port}.json').read_text(encoding='utf-8'))
        assert Path(metadata['database_path']).resolve() == test_db.resolve()
        return metadata['pid']

    try:
        server = start()
        first_backend_pid = backend_pid()
        print('Isolated fictitious backend ready; testing configured origin.', flush=True)
        first, collaborator, reader, other = [Session(args.base_url) for _ in range(4)]
        for _ in range(30):
            try:
                health = expect(first.call('/api/health'))
                break
            except (OSError, AssertionError):
                time.sleep(.3)
        else:
            raise AssertionError('The configured origin is unavailable; TLS verification was not bypassed.')
        assert health.get('application') == 'organiza'
        assert set(health) == {'application', 'version', 'instance_id'}
        assert expect(Session(local).call('/api/health')) == health
        checks.append('same_backend_local_and_configured_origin_certificate_validation')
        password = secrets.token_urlsafe(28)
        names = {role: f'private_{role}_{tag[:8]}' for role in ('admin', 'collaborator', 'reader', 'other')}
        for session, role in [(first, 'admin'), (collaborator, 'collaborator'), (reader, 'reader'), (other, 'other')]:
            expect(session.call('/api/session'))
            expect(session.call('/api/auth/register', {'username': names[role], 'password': password}), 201)
        cookies = {cookie.name: cookie for cookie in first.jar}
        if private:
            assert {'organiza_sessionid', 'organiza_csrftoken'} <= cookies.keys()
            assert all(cookies[name].secure for name in ('organiza_sessionid', 'organiza_csrftoken'))
            assert 'sessionid' not in cookies and 'csrftoken' not in cookies
            assert 'max-age=' in (first.headers.get('Strict-Transport-Security') or '')
        else:
            assert {'sessionid', 'csrftoken'} <= cookies.keys()
            assert not cookies['sessionid'].secure
        checks.append('transport_cookie_names_secure_flags_and_hsts')
        local_session = Session(local)
        expect(local_session.call('/api/session'))
        expect(local_session.call('/api/auth/login', {'username': names['admin'], 'password': password}))
        assert expect(local_session.call('/api/session'))['user'] is not None
        expect(local_session.call('/api/auth/logout', {}))
        assert expect(local_session.call('/api/session'))['user'] is None
        assert expect(first.call('/api/session'))['user'] is not None
        expect(first.call('/api/spaces', {'name': 'Invalid missing CSRF'}, token=False), 403)
        expect(first.call('/api/spaces', {'name': 'Invalid origin'}, origin='https://untrusted.invalid'), 403)
        checks.append('local_http_login_logout_and_private_csrf_origin_enforcement')
        space = expect(first.call('/api/spaces', {'name': 'Ensaio fictício de acesso privado'}), 201)['space']['id']
        for role in ('collaborator', 'reader'):
            expect(first.call(f'/api/spaces/{space}/members', {'username': names[role], 'role': role}))
        url = f'/api/spaces/{space}/actions'

        def state(session=first):
            return expect(session.call(f'/api/spaces/{space}/state'))

        def action(action, data, session=first):
            payload = {'action': action, 'data': data, 'expected_revision': state(session)['revision'], 'request_id': str(uuid.uuid4())}
            return expect(session.call(url, payload))

        today = datetime.now(ZoneInfo('America/Manaus')).date().isoformat()
        account = action('account.create', {'name': 'Conta fictícia HTTPS', 'opening_balance_cents': 100000, 'reference_date': today}, collaborator)['result']['id']
        assert state(reader)['space']['role'] == 'reader'
        forbidden = {'action': 'account.create', 'data': {'name': 'Fictitious forbidden'}, 'expected_revision': state()['revision'], 'request_id': str(uuid.uuid4())}
        expect(reader.call(url, forbidden), 403)
        expect(other.call(f'/api/spaces/{space}/state'), 404)
        expect(other.call(url, forbidden), 404)
        checks.append('admin_collaborator_reader_and_space_isolation')
        purchase = action('entry.create', {'kind': 'expense', 'method': 'pix', 'description': 'Conta fictícia HTTPS',
                                           'amount_cents': 50000, 'account_id': account, 'due_date': today})
        obligation = next(item for item in purchase['state']['obligations'] if item['entry_id'] == purchase['result']['id'])
        action('obligation.pay', {'obligation_id': obligation['id'], 'mode': 'partial', 'amount_cents': 15000, 'account_id': account})
        partial = state()
        assert (partial['entries'][0]['amount_cents'], partial['entries'][0]['paid_cents'], partial['debt_cents'], partial['balance_cents']) == (50000, 15000, 35000, 85000)
        action('obligation.pay', {'obligation_id': obligation['id'], 'mode': 'full', 'expected_remaining_cents': 35000, 'account_id': account})
        assert (state()['debt_cents'], state()['balance_cents']) == (0, 50000)
        checks.append('authenticated_partial_and_full_payment_preserve_original_and_cash')
        second = action('entry.create', {'kind': 'expense', 'method': 'pix', 'description': 'Concorrência fictícia HTTPS',
                                         'amount_cents': 10000, 'account_id': account, 'due_date': today})
        obligation = next(item for item in second['state']['obligations'] if item['entry_id'] == second['result']['id'])
        revision = state()['revision']
        payloads = [{'action': 'obligation.pay', 'data': {'obligation_id': obligation['id'], 'mode': 'full',
                     'expected_remaining_cents': 10000, 'account_id': account}, 'expected_revision': revision,
                     'request_id': str(uuid.uuid4())} for _ in range(2)]
        barrier = threading.Barrier(2)

        def simultaneous(index):
            barrier.wait(timeout=10)
            return (first, collaborator)[index].call(url, payloads[index])

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(simultaneous, index) for index in (0, 1)]
            replies = [future.result(timeout=35) for future in futures]
        statuses = [response[0] for response in replies]
        assert sorted(statuses) == [200, 409]
        final = state()
        assert (final['debt_cents'], final['balance_cents'], len(final['payments']), len(final['ledger'])) == (0, 40000, 3, 3)
        winner = statuses.index(200)
        repeated = expect((first, collaborator)[winner].call(url, payloads[winner]))
        assert repeated['duplicate'] and state() == final
        checks.append('simultaneous_authenticated_sessions_stale_rejection_and_idempotent_retry')
        stop(server)
        server = start()
        assert backend_pid() != first_backend_pid
        assert state() == final
        assert state(reader)['space']['role'] == 'reader'
        checks.append('complete_state_and_authenticated_sessions_persist_after_backend_restart')
        expect(first.call('/api/auth/logout', {}))
        expect(first.call(f'/api/spaces/{space}/state'), 401)
        expect(first.call('/api/auth/login', {'username': names['admin'], 'password': password}))
        assert state()['revision'] == final['revision']
        checks.append('logout_revokes_session_and_login_restores_access_through_origin')
        evidence = {'checks': checks, 'checks_passed': len(checks), 'transport': parsed.scheme,
                    'origin': args.base_url.rstrip('/'), 'backend': local, 'version': health['version'],
                    'tls_certificate_verified': private, 'concurrent_response_statuses': statuses,
                    'restart_changed_backend_process': True,
                    'restart_preserved_complete_snapshot': True, 'fictitious_data_only': True,
                    'official_database_accessed': False, 'tailscale_configuration_changed_by_script': False,
                    'physical_devices_tested': False, 'fictitious_database': test_db.name}
        filename = 'private-access-https-evidence.json' if private else 'private-access-http-evidence.json'
        (results / filename).write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
    finally:
        stop(server)


if __name__ == '__main__':
    main()
