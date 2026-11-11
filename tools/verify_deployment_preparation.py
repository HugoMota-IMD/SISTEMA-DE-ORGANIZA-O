"""Validate the Render candidate locally, without a real secret or database.

The intentionally unreachable PostgreSQL URL proves that checks/static builds
do not connect to the database or silently create SQLite. No provider is called.
"""
import json
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    import yaml
    blueprint = yaml.safe_load((ROOT / 'render.yaml').read_text(encoding='utf-8'))
    services = blueprint['services']
    assert len(services) == 1 and not blueprint.get('databases')
    service = services[0]
    assert service['type'] == 'web' and service['runtime'] == 'python'
    assert service['plan'] == 'free' and service['numInstances'] == 1
    assert service['autoDeployTrigger'] == 'off' and service['healthCheckPath'] == '/api/health'
    assert 'preDeployCommand' not in service and 'disk' not in service
    variables = {item['key']: item for item in service['envVars']}
    assert service['region'] == 'virginia' and service['branch'] == 'main'
    assert 'DATABASE_URL_UNPOOLED' not in variables
    for name in ['DATABASE_URL', 'APP_SECRET_KEY']:
        assert variables[name]['sync'] is False and 'value' not in variables[name]
    assert variables['APP_READ_ONLY']['value'] == 'true'
    assert variables['APP_REGISTRATION_MODE']['value'] == 'approval'
    checks = ['render_blueprint_free_only_no_secrets_no_public_signup']
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('APP_') or key in {'DATABASE_URL', 'DATABASE_URL_UNPOOLED', 'RENDER', 'RENDER_EXTERNAL_HOSTNAME'}:
            env.pop(key, None)
    env.update(APP_ENVIRONMENT='production', APP_LOCAL_MODE='false', APP_DEBUG='false',
               APP_SECRET_KEY=secrets.token_urlsafe(64), APP_REGISTRATION_MODE='approval', APP_READ_ONLY='true',
               RENDER='true', RENDER_EXTERNAL_HOSTNAME='organiza-build-test.onrender.com',
               DATABASE_URL='postgresql://build_fixture:not-a-real-password@127.0.0.1:1/organiza_build_test?sslmode=require')
    for args in [['manage.py', 'check', '--deploy', '--fail-level', 'WARNING'],
                 ['manage.py', 'collectstatic', '--noinput']]:
        result = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, text=True, capture_output=True)
        if result.returncode:
            # This environment has only fictitious credentials. Persist logs in
            # ignored test-results; never use this runner with a real DSN.
            (ROOT / 'test-results/deployment-preparation-failure.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            raise RuntimeError('A configuração/build local falhou; consulte o registro fictício ignorado.')
    checks.append('production_checks_and_manifest_static_build_without_database_access')
    probe = r'''
import json, django
django.setup()
from django.test import Client
from django.conf import settings
from django.core.files.storage import storages
from config.log_filters import SafeErrorFilter
import logging
client=Client()
headers={'HTTP_HOST':settings.ALLOWED_HOSTS[0], 'HTTP_X_FORWARDED_PROTO':'https'}
health=client.get('/api/health',**headers)
assert health.status_code==200 and health.json()['application']=='organiza'
assert set(health.json())=={'application','version','instance_id'}
manifest=json.loads((settings.STATIC_ROOT/'staticfiles.json').read_text())['paths']
for asset in ['app.js','app.css','icon.svg']:
    response=client.get('/static/'+manifest[asset],**headers)
    assert response.status_code==200
response=client.post('/api/spaces',data='{}',content_type='application/json',**headers)
assert response.status_code==503 and response.json()['read_only'] is True
record=logging.LogRecord('django.db.backends',logging.ERROR,'',0,'SECRET=fixture-sensitive-data',(),None)
SafeErrorFilter().filter(record)
assert 'fixture-sensitive-data' not in record.getMessage() and record.exc_info is None
print(json.dumps({'health_no_database':True,'hashed_static_files':True,'read_only_without_database':True,'sanitized_error_log':True}))
'''
    result = subprocess.run([sys.executable, '-c', probe], cwd=ROOT,
                            env={**env, 'DJANGO_SETTINGS_MODULE': 'config.settings'}, text=True, capture_output=True)
    if result.returncode:
        (ROOT / 'test-results/deployment-preparation-failure.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        raise RuntimeError('A verificação HTTP simulada de produção falhou; nenhum deploy foi realizado.')
    assert json.loads(result.stdout)['hashed_static_files']
    checks.append('production_proxy_simulation_health_hashed_statics_readonly_and_safe_logs')
    bash = Path(os.getenv('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe' if os.name == 'nt' else Path('/bin/bash')
    if not bash.is_file():
        raise RuntimeError('Bash indisponível para validar os scripts Linux.')
    for name in ['build.sh', 'start-render.sh']:
        subprocess.run([str(bash), '-n', name], cwd=ROOT, check=True, capture_output=True)
    conf = runpy.run_path(str(ROOT / 'gunicorn.conf.py'))
    assert conf['workers'] == 1 and conf['threads'] == 2 and conf['accesslog'] is None
    assert conf['bind'].startswith('0.0.0.0:')
    checks.append('linux_shell_syntax_and_gunicorn_configuration')
    # Exercise the real start script up to its failure boundary. A broken app
    # URL or registration setting must stop it before schema changes or WSGI.
    start_env = dict(env, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'],
                     DATABASE_URL_UNPOOLED=env['DATABASE_URL'])
    for changes, message in [
            ({'DATABASE_URL': ''}, 'DATABASE_URL'),
            ({'DATABASE_URL': 'sqlite:///temporary.sqlite3'}, 'PostgreSQL'),
            ({'APP_REGISTRATION_MODE': 'open'}, 'APP_REGISTRATION_MODE')]:
        result = subprocess.run([str(bash), 'start-render.sh'], cwd=ROOT, env={**start_env, **changes},
                                text=True, errors='replace', capture_output=True, timeout=30)
        assert result.returncode and message in result.stderr
        assert 'Applying ' not in result.stdout and 'fixture-sensitive-data' not in result.stderr
    # An accidentally inherited migrator URL is discarded. Missing web URL is
    # still rejected, without ever invoking the migration script.
    assert 'migrate_schema' not in (ROOT / 'start-render.sh').read_text()
    assert 'unset APP_USE_DIRECT_DATABASE DATABASE_URL_UNPOOLED' in (ROOT / 'start-render.sh').read_text()
    checks.append('startup_rejects_missing_or_sqlite_urls_and_open_signup_without_migrations')
    result = {'checks': checks, 'checks_passed': len(checks), 'production_database_contacted': False,
              'external_resources_created': False, 'linux_gunicorn_executed': False,
              'render_actual_suspend_tested': False, 'https_transport_simulated_only': True,
              'real_credentials_used': False}
    (ROOT / 'test-results/deployment-preparation-evidence.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
