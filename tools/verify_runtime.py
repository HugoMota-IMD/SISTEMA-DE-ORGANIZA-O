"""Real start/stop/conflict regressions, isolated fictitious database and ports."""
import concurrent.futures
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from organiza_runtime import serve_state

ROOT = Path(__file__).resolve().parent.parent
PORT = 8786
FOREIGN_PORT = 8787


def run(env, action, expected=0):
    result = subprocess.run([sys.executable, 'tools/organiza_runtime.py', action, '--json'],
                            cwd=ROOT, env=env, text=True, encoding='utf-8', capture_output=True, timeout=50)
    assert result.returncode == expected, (action, result.stdout, result.stderr)
    return json.loads((result.stdout if expected == 0 else result.stderr).strip())


def free(port):
    with socket.socket() as probe:
        probe.settimeout(.2)
        return probe.connect_ex(('127.0.0.1', port)) != 0


class Session:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token = ''

    def call(self, path, payload=None):
        headers = {'Accept': 'application/json'}
        if payload is not None:
            headers.update({'Content-Type': 'application/json', 'X-CSRFToken': self.token})
        request = urllib.request.Request(f'http://127.0.0.1:{PORT}' + path,
                                         data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        with self.opener.open(request, timeout=10) as response:
            result = json.load(response)
            self.token = result.get('csrf_token', self.token)
            return result


def main():
    assert free(PORT) and free(FOREIGN_PORT), 'Test ports occupied; nothing was changed.'
    results = ROOT / 'test-results'
    results.mkdir(exist_ok=True)
    tag = uuid.uuid4().hex
    database = results / f'runtime-{tag}.sqlite3'
    env = dict(os.environ, APP_PORT=str(PORT), APP_DB_PATH=str(database),
               APP_SECRET_KEY=secrets.token_urlsafe(64), APP_LOCAL_MODE='true')
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env,
                   check=True, capture_output=True)
    foreign = None
    running = False
    checks = []
    try:
        serving_config = {'private_url':'https://runtime-example.ts.net','port':PORT}
        good = {'TCP':{'443':{'HTTPS':True}},'Web':{'runtime-example.ts.net:443':{'Handlers':{'/':{'Proxy':f'http://127.0.0.1:{PORT}'}}}}}
        assert serve_state({}, serving_config)[0] == 'not_configured'
        assert serve_state(good, serving_config, 'runtime-example.ts.net')[0] == 'configured'
        assert serve_state(good, serving_config, 'other.ts.net')[0] == 'wrong_target'
        assert serve_state(good, dict(serving_config,port=9999))[0] == 'wrong_target'
        assert serve_state(dict(good,AllowFunnel={'runtime-example.ts.net:443':True}),serving_config)[0] == 'public_funnel'
        assert serve_state({},dict(serving_config,private_url=''))[0] == 'not_configured'
        checks.append('serve_status_distinguishes_missing_configured_wrong_endpoint_and_public_funnel')

        missing = results / f'runtime-missing-{tag}.sqlite3'
        rejected = run(dict(env, APP_DB_PATH=str(missing)), 'start', expected=1)
        assert not missing.exists() and 'não encontrado' in rejected['error']
        checks.append('missing_database_rejected_without_creating_installation')

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(run, env, 'start') for _ in range(2)]
            starts = [item.result(timeout=50) for item in attempts]
        running = True
        assert sorted(item['result'] for item in starts) == ['already_running', 'started']
        assert all(item['status'] == 'running' for item in starts)
        checks.append('two_simultaneous_launchers_one_server_and_already_running_detection')

        duplicate = subprocess.run([sys.executable, str(ROOT / 'serve.py')], cwd=ROOT, env=env,
                                   capture_output=True, timeout=15)
        assert duplicate.returncode != 0 and run(env, 'status')['status'] == 'running'
        checks.append('direct_duplicate_server_rejected_by_lifetime_lock')

        client = Session()
        client.call('/api/session')
        client.call('/api/auth/register', {'username': 'runtime_fictitious', 'password': secrets.token_urlsafe(32)})
        space = client.call('/api/spaces', {'name': 'Espaço fictício runtime'})['space']['id']
        state_url = f'/api/spaces/{space}/state'
        state = client.call(state_url)
        today = datetime.now(ZoneInfo('America/Manaus')).date().isoformat()
        client.call(f'/api/spaces/{space}/actions', {'action': 'account.create',
                    'data': {'name': 'Conta fictícia runtime', 'opening_balance_cents': 123456, 'reference_date': today},
                    'expected_revision': state['revision'], 'request_id': str(uuid.uuid4())})
        before = client.call(state_url)
        assert before['balance_cents'] == 123456
        assert run(env, 'stop')['result'] == 'stopped'
        running = False
        assert run(env, 'stop')['result'] == 'already_stopped'
        assert run(env, 'start')['result'] == 'started'
        running = True
        after = client.call(state_url)
        assert before == after, 'Financial state or authentication was lost after restart.'
        checks.append('stop_restart_retains_exact_fictitious_financial_state_and_session')

        foreign = subprocess.Popen([sys.executable, '-m', 'http.server', str(FOREIGN_PORT), '--bind', '127.0.0.1'],
                                   cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        for _ in range(100):
            if not free(FOREIGN_PORT):
                break
            time.sleep(.1)
        assert not free(FOREIGN_PORT)
        foreign_env = dict(env, APP_PORT=str(FOREIGN_PORT))
        assert run(foreign_env, 'status')['status'] == 'port_conflict'
        assert 'ocupada' in run(foreign_env, 'start', expected=1)['error']
        assert 'não foi confirmado' in run(foreign_env, 'stop', expected=1)['error']
        assert foreign.poll() is None and not free(FOREIGN_PORT)
        checks.append('foreign_port_conflict_identified_and_foreign_process_never_stopped')

        assert run(env, 'stop')['result'] == 'stopped'
        running = False
        evidence = {'checks': checks, 'checks_passed': len(checks), 'fake_database': database.name,
                    'ports': [PORT, FOREIGN_PORT], 'official_port_used': False,
                    'production_database_accessed': False, 'fictitious_data_only': True,
                    'autostart_activated': False}
        (results / 'runtime-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(json.dumps(evidence, indent=2))
    finally:
        if running:
            run(env, 'stop')
        if foreign:
            foreign.terminate()
            foreign.wait(timeout=10)


if __name__ == '__main__':
    main()
