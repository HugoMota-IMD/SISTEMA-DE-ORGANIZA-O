"""Fail-closed hosted configuration, using fresh processes and fictitious secrets.

Settings probes never connect to a database or read the local .env. HTTP tests
use Django's disposable test database, never the official application database.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from django.db import IntegrityError, InterfaceError, OperationalError
from django.http import JsonResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from .security import ActorMiddleware


ROOT = Path(__file__).resolve().parent.parent
FICTITIOUS_SECRET = 'Fictitious-hosted-config-only-74652-abcdefghijklmnopqrstuvwxyz-0123456789'
URL_PASSWORD = 'Fictitious-Connection-DO-NOT-ECHO-9247'
DATABASE = 'postgresql://fictitious:' + URL_PASSWORD + '@db.fictitious.invalid/organiza?sslmode=require'
HOST = 'organiza-fictitious.onrender.com'

PROBE = r'''
import json,os
from pathlib import Path
exists=Path.exists
read_text=Path.read_text
def guarded_exists(path):
    return True if path.name=='.env' else exists(path)
def guarded_read(path,*args,**kwargs):
    if path.name=='.env':
        raise RuntimeError('UNEXPECTED_LOCAL_ENV_READ')
    return read_text(path,*args,**kwargs)
Path.exists=guarded_exists
Path.read_text=guarded_read
try:
    import config.settings as value
    db=value.DATABASES['default']
    options=db.get('OPTIONS',{})
    print(json.dumps({'ok':True,'hosted':value.HOSTED,'local_mode':value.LOCAL_MODE,
        'debug':value.DEBUG,'registration':value.REGISTRATION_MODE,
        'hosts':value.ALLOWED_HOSTS,'origins':value.CSRF_TRUSTED_ORIGINS,
        'private_origin':value.PRIVATE_HTTPS_ORIGIN,'private_host':value.PRIVATE_HTTPS_HOST,
        'engine':db['ENGINE'],'connection_age':db.get('CONN_MAX_AGE'),
        'server_cursors_disabled':db.get('DISABLE_SERVER_SIDE_CURSORS'),
        'sslmode':options.get('sslmode'),'sslrootcert_present':bool(options.get('sslrootcert')),
        'prepare_threshold_present':'prepare_threshold' in options,
        'prepare_threshold':options.get('prepare_threshold'),'connect_timeout':options.get('connect_timeout'),
        'session_secure':value.SESSION_COOKIE_SECURE,'csrf_secure':value.CSRF_COOKIE_SECURE,
        'session_cookie':value.SESSION_COOKIE_NAME if hasattr(value,'SESSION_COOKIE_NAME') else 'sessionid',
        'csrf_cookie':value.CSRF_COOKIE_NAME if hasattr(value,'CSRF_COOKIE_NAME') else 'csrftoken',
        'ssl_redirect':value.SECURE_SSL_REDIRECT,'proxy_ssl_header':value.SECURE_PROXY_SSL_HEADER,
        'forwarded_host':value.USE_X_FORWARDED_HOST,'read_only':value.READ_ONLY_MODE,
        'secret_preserved':value.SECRET_KEY==os.environ.get('APP_SECRET_KEY')}))
except Exception as error:
    print(json.dumps({'ok':False,'error_type':type(error).__name__,'message':str(error)}))
'''


class HostedConfigurationTests(SimpleTestCase):
    cache = {}

    def probe(self, **changes):
        values = {
            'APP_ENVIRONMENT': 'production', 'APP_LOCAL_MODE': 'false', 'APP_DEBUG': 'false',
            'APP_SECRET_KEY': FICTITIOUS_SECRET, 'APP_ALLOWED_HOSTS': HOST,
            'APP_CSRF_TRUSTED_ORIGINS': 'https://' + HOST, 'DATABASE_URL': DATABASE,
        }
        values.update(changes)
        key = tuple(sorted((name, value) for name, value in values.items()))
        if key not in self.cache:
            env = {name: value for name, value in os.environ.items()
                   if not (name.startswith('APP_') or name.startswith('RENDER')
                           or name in {'DATABASE_URL', 'DATABASE_URL_UNPOOLED', 'DJANGO_SETTINGS_MODULE'})}
            env.update({name: value for name, value in values.items() if value is not None})
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            run = subprocess.run([sys.executable, '-c', PROBE], cwd=ROOT, env=env,
                                 capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, 'The isolated configuration probe did not finish.')
            try:
                result = json.loads(run.stdout)
            except ValueError:
                self.fail('The isolated configuration probe did not return structured output.')
            self.assertNotIn(URL_PASSWORD, run.stdout + run.stderr)
            self.assertNotIn(FICTITIOUS_SECRET, run.stdout + run.stderr)
            self.cache[key] = result
        return self.cache[key]

    def assert_rejected(self, **changes):
        result = self.probe(**changes)
        self.assertFalse(result['ok'], 'An unsafe hosted configuration was accepted.')
        self.assertEqual(result['error_type'], 'RuntimeError')
        self.assertNotIn('UNEXPECTED_LOCAL_ENV_READ', result['message'])
        return result

    def test_production_requires_postgres_without_sqlite_fallback(self):
        result = self.assert_rejected(DATABASE_URL='')
        self.assertIn('PostgreSQL', result['message'])
        self.assert_rejected(DATABASE_URL='sqlite:///temporary.sqlite3')
        self.assert_rejected(DATABASE_URL='mysql://fictitious:password@db.fictitious.invalid/organiza')

    def test_render_automatically_selects_hosted_and_fails_without_database(self):
        result = self.assert_rejected(RENDER='true', APP_ENVIRONMENT=None, DATABASE_URL='')
        self.assertIn('PostgreSQL', result['message'])

    def test_production_refuses_local_debug_and_public_registration(self):
        for changes in ({'APP_LOCAL_MODE':'true'}, {'APP_DEBUG':'true'}, {'APP_REGISTRATION_MODE':'open'}):
            with self.subTest(changes=changes):
                self.assert_rejected(**changes)

    def test_production_rejects_absent_short_and_placeholder_secrets(self):
        for secret in ('', 'short', 'a' * 64, 'django-insecure-' + FICTITIOUS_SECRET):
            with self.subTest(kind='missing' if not secret else 'invalid'):
                result = self.assert_rejected(APP_SECRET_KEY=secret)
                if secret:
                    self.assertNotIn(secret, result['message'])

    def test_exact_hosts_required_without_wildcards_or_url_syntax(self):
        for host in ('', '*', '.onrender.com', '*.onrender.com', 'https://' + HOST,
                     HOST + ':443', HOST + '?unexpected', '-invalid.onrender.com'):
            with self.subTest(host=host):
                self.assert_rejected(APP_ALLOWED_HOSTS=host)

    def test_csrf_origins_require_exact_https_and_valid_port(self):
        for origin in ('http://' + HOST, 'https://*.onrender.com', 'https://' + HOST + '/path',
                       'https://user:password@' + HOST, 'https://' + HOST + '?query=1',
                       'https://' + HOST + ':invalid', 'https://' + HOST + ':0'):
            with self.subTest(origin=origin):
                self.assert_rejected(APP_CSRF_TRUSTED_ORIGINS=origin)

    def test_hosted_database_uses_verified_tls_and_transaction_pooling_options(self):
        result = self.probe()
        self.assertTrue(result['ok'])
        self.assertEqual(result['engine'], 'django.db.backends.postgresql')
        self.assertEqual(result['sslmode'], 'verify-full')
        self.assertTrue(result['sslrootcert_present'])
        self.assertEqual(result['connection_age'], 0)
        self.assertTrue(result['server_cursors_disabled'])
        self.assertTrue(result['prepare_threshold_present'])
        self.assertIsNone(result['prepare_threshold'])
        self.assertGreaterEqual(result['connect_timeout'], 1)
        self.assertEqual(result['registration'], 'approval')

    def test_weak_database_tls_and_malformed_credentials_are_rejected_without_echo(self):
        for suffix in ('disable', 'allow', 'prefer'):
            with self.subTest(sslmode=suffix):
                self.assert_rejected(DATABASE_URL=DATABASE.replace('sslmode=require', 'sslmode=' + suffix))
        self.assert_rejected(DATABASE_URL='postgresql://fictitious:' + URL_PASSWORD + '@[broken/organiza')

    def test_maintenance_requires_direct_connection_if_pooler_is_supplied(self):
        pooled = DATABASE.replace('db.fictitious.invalid', 'ep-fictitious-pooler.neon.tech')
        result = self.assert_rejected(APP_USE_DIRECT_DATABASE='true', DATABASE_URL=pooled)
        self.assertIn('DATABASE_URL_UNPOOLED', result['message'])
        result = self.probe(APP_USE_DIRECT_DATABASE='true', DATABASE_URL=pooled, DATABASE_URL_UNPOOLED=DATABASE)
        self.assertTrue(result['ok'])

    def test_cutover_defaults_to_read_only_and_requires_explicit_boolean(self):
        self.assertTrue(self.probe()['read_only'])
        self.assertFalse(self.probe(APP_READ_ONLY='false')['read_only'])
        self.assert_rejected(APP_READ_ONLY='treu')

    def test_hosted_url_query_cannot_replace_the_database_host(self):
        self.assert_rejected(DATABASE_URL=DATABASE + '&host=unexpected.invalid')
        self.assert_rejected(DATABASE_URL=DATABASE + '&sslmode=prefer')

    def test_production_never_reads_the_local_dotenv_or_its_private_origin(self):
        result = self.probe()
        self.assertTrue(result['ok'])
        self.assertEqual(result['private_origin'], '')
        self.assertEqual(result['private_host'], '')
        self.assertNotIn('desktop-flde4sk.tail08d4d6.ts.net', result['hosts'])

    def test_hosted_cannot_accidentally_adopt_the_local_tailscale_origin(self):
        self.assert_rejected(APP_PRIVATE_HTTPS_ORIGIN='https://organiza-fictitious.tailnet.ts.net')

    def test_render_host_and_origin_are_added_as_exact_values(self):
        result = self.probe(RENDER='true', APP_ENVIRONMENT=None, APP_ALLOWED_HOSTS='',
                            APP_CSRF_TRUSTED_ORIGINS='', RENDER_EXTERNAL_HOSTNAME=HOST)
        self.assertTrue(result['ok'])
        self.assertEqual(result['hosts'], [HOST])
        self.assertEqual(result['origins'], ['https://' + HOST])
        self.assertTrue(result['hosted'])
        self.assertFalse(result['local_mode'])

    def test_proxy_header_trust_is_render_only_and_secure_cookie_flags_are_hosted(self):
        direct = self.probe()
        rendered = self.probe(RENDER='true', APP_ENVIRONMENT=None, RENDER_EXTERNAL_HOSTNAME=HOST)
        self.assertTrue(direct['ok'] and rendered['ok'])
        self.assertIsNone(direct['proxy_ssl_header'])
        self.assertEqual(rendered['proxy_ssl_header'], ['HTTP_X_FORWARDED_PROTO', 'https'])
        for result in (direct, rendered):
            self.assertTrue(result['session_secure'] and result['csrf_secure'] and result['ssl_redirect'])
            self.assertFalse(result['forwarded_host'])
            self.assertEqual(result['session_cookie'], 'organiza_sessionid')
            self.assertEqual(result['csrf_cookie'], 'organiza_csrftoken')
            self.assertTrue(result['secret_preserved'])


@override_settings(READ_ONLY_MODE=True, ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
                   PRIVATE_HTTPS_HOST='', PRIVATE_HTTPS_ORIGIN='', SECURE_SSL_REDIRECT=False)
class MigrationReadOnlyTests(TestCase):
    def test_write_methods_are_rejected_before_authentication_or_database_access(self):
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method), self.assertNumQueries(0):
                response = getattr(Client(), method)('/api/spaces', data='{}', content_type='application/json')
            self.assertEqual(response.status_code, 503)
            self.assertTrue(response.json()['read_only'])
            self.assertEqual(response.headers['Retry-After'], '60')

    def test_health_stays_available_without_connecting_even_in_read_only_mode(self):
        with self.assertNumQueries(0):
            response = Client().get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['application'], 'organiza')

    def test_read_only_response_never_discloses_submitted_financial_or_secret_values(self):
        marker = 'Fictitious-private-payload-DO-NOT-ECHO-9431'
        with self.assertNumQueries(0):
            response = Client().post('/api/auth/login', data=json.dumps({'password':marker}),
                                     content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(marker, response.content.decode())


@override_settings(PRIVATE_HTTPS_HOST='organiza-fictitious.tailnet.ts.net',
                   PRIVATE_HTTPS_ORIGIN='https://organiza-fictitious.tailnet.ts.net',
                   ALLOWED_HOSTS=['organiza-fictitious.tailnet.ts.net'],
                   SESSION_COOKIE_NAME='organiza_sessionid', CSRF_COOKIE_NAME='organiza_csrftoken',
                   READ_ONLY_MODE=False, SECURE_SSL_REDIRECT=False)
class HostedPrivateCookieTests(TestCase):
    def test_already_namespaced_cookies_are_not_removed_by_private_middleware(self):
        response = Client().get('/api/session', secure=True, HTTP_HOST='organiza-fictitious.tailnet.ts.net')
        self.assertEqual(response.status_code, 200)
        self.assertIn('organiza_csrftoken', response.cookies)
        self.assertTrue(response.cookies['organiza_csrftoken']['secure'])


class DatabaseUnavailableResponseTests(SimpleTestCase):
    marker = 'Fictitious-driver-secret-DO-NOT-ECHO-58294'

    def request(self, path='/api/spaces', *, user=None, method='post'):
        request = getattr(RequestFactory(), method)(path)
        request.user = user or SimpleNamespace(is_authenticated=True, pk=902)
        return request

    def assert_unavailable(self, response):
        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.content)
        self.assertTrue(payload['retry_same_request_id'])
        self.assertIn('confirmar', payload['error'])
        self.assertIn('mesma chave', payload['error'])
        self.assertNotIn(self.marker, response.content.decode())
        self.assertNotIn('Traceback', response.content.decode())
        self.assertEqual(response.headers['Retry-After'], '60')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_connection_failure_while_resolving_session_is_sanitized(self):
        marker = self.marker

        class UnavailableUser:
            @property
            def is_authenticated(self):
                raise OperationalError(marker)

        called = []
        response = ActorMiddleware(lambda request: called.append(True))(self.request(user=UnavailableUser()))
        self.assert_unavailable(response)
        self.assertEqual(called, [])

    def test_context_setup_failure_is_sanitized_before_endpoint_runs(self):
        called = []
        for error in (OperationalError, InterfaceError):
            with self.subTest(error=error.__name__), patch('finance.security.actor_context', side_effect=error(self.marker)):
                response = ActorMiddleware(lambda request: called.append(True))(self.request())
            self.assert_unavailable(response)
        self.assertEqual(called, [])

    def test_uncertain_commit_replaces_success_without_claiming_a_rollback(self):
        marker = self.marker

        @contextmanager
        def fail_on_commit(user_id):
            yield
            raise OperationalError(marker)

        called = []

        def endpoint(request):
            called.append(True)
            return JsonResponse({'ok': True, 'private_value': marker})

        with patch('finance.security.actor_context', fail_on_commit):
            response = ActorMiddleware(endpoint)(self.request())
        self.assertEqual(called, [True])
        self.assert_unavailable(response)
        self.assertNotIn('ok', json.loads(response.content))
        self.assertNotIn('private_value', json.loads(response.content))
        self.assertNotIn('Nenhuma alteração', json.loads(response.content)['error'])

    def test_integrity_errors_are_not_misclassified_as_transient_connection_errors(self):
        with patch('finance.security.actor_context', side_effect=IntegrityError('Fictitious integrity rejection')):
            with self.assertRaises(IntegrityError):
                ActorMiddleware(lambda request: JsonResponse({'ok': True}))(self.request())

    def test_health_does_not_resolve_user_or_create_actor_database_context(self):
        class UnavailableUser:
            @property
            def is_authenticated(self):
                raise AssertionError('Health resolved an authentication session.')

        with patch('finance.security.actor_context', side_effect=AssertionError('Health created actor context.')):
            response = ActorMiddleware(lambda request: JsonResponse({'application':'organiza'}))(
                self.request('/api/health', user=UnavailableUser(), method='get'))
        self.assertEqual(response.status_code, 200)

    def test_successful_response_is_returned_only_after_context_exits_successfully(self):
        events = []

        @contextmanager
        def context(user_id):
            events.append('enter')
            yield
            events.append('commit')

        def endpoint(request):
            events.append('endpoint')
            return JsonResponse({'ok': True})

        with patch('finance.security.actor_context', context):
            response = ActorMiddleware(endpoint)(self.request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(events, ['enter', 'endpoint', 'commit'])
