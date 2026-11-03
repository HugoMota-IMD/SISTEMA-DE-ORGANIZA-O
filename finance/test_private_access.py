"""Private HTTPS and localhost regressions; Django uses a disposable test DB."""
import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

HOST = 'organiza-test.tailnet-test.ts.net'
ORIGIN = 'https://' + HOST


@override_settings(
    PRIVATE_HTTPS_ORIGIN=ORIGIN,
    PRIVATE_HTTPS_HOST=HOST,
    ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1', HOST],
    CSRF_TRUSTED_ORIGINS=[ORIGIN],
    SECURE_PROXY_SSL_HEADER=None,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class PrivateAccessTests(TestCase):
    password = 'Fictitious-private-access-58279!'

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='private_test_admin', password=self.password)

    def get(self, client, path, *, private=True, secure=True, **headers):
        return client.get(path, secure=secure if private else False,
                          HTTP_HOST=HOST if private else '127.0.0.1', **headers)

    def post(self, client, path, data, *, private=True, token=None, expected=200, origin=None):
        headers = {'HTTP_HOST': HOST if private else '127.0.0.1'}
        if token is not None:
            headers['HTTP_X_CSRFTOKEN'] = token
        if private:
            headers['HTTP_ORIGIN'] = origin or ORIGIN
        response = client.post(path, data=json.dumps(data), content_type='application/json', secure=private, **headers)
        self.assertEqual(response.status_code, expected, response.content[:700])
        return response

    def login(self, client=None, *, private=True):
        client = client or Client(enforce_csrf_checks=True)
        session = self.get(client, '/api/session', private=private).json()
        response = self.post(client, '/api/auth/login', {'username': self.user.username, 'password': self.password},
                             private=private, token=session['csrf_token'])
        return client, response

    def test_health_is_read_only_and_does_not_disclose_paths_or_finances(self):
        with self.assertNumQueries(0):
            response = self.get(Client(), '/api/health')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['application'], 'organiza')
        self.assertRegex(payload['instance_id'], r'^[a-f0-9]{16}$')
        self.assertEqual(set(payload), {'application', 'version', 'instance_id'})
        self.assertFalse(response.cookies)

    def test_private_http_redirects_to_exact_https_origin_and_ignores_raw_forwarded_proto(self):
        response = self.get(Client(), '/api/session?check=1', secure=False, HTTP_X_FORWARDED_PROTO='https')
        self.assertIn(response.status_code, (301, 302, 307, 308))
        self.assertEqual(response.headers['Location'], ORIGIN + '/api/session?check=1')

    def test_unknown_host_is_rejected(self):
        response = Client().get('/api/health', secure=True, HTTP_HOST='untrusted.invalid')
        self.assertEqual(response.status_code, 400)

    def test_private_login_logout_secure_named_cookies_and_hsts(self):
        client, response = self.login()
        self.assertIn('organiza_sessionid', response.cookies)
        self.assertIn('organiza_csrftoken', response.cookies)
        for name in ('organiza_sessionid', 'organiza_csrftoken'):
            self.assertTrue(response.cookies[name]['secure'])
            self.assertEqual(response.cookies[name]['samesite'], 'Strict')
        self.assertTrue(response.cookies['organiza_sessionid']['httponly'])
        self.assertNotIn('sessionid', response.cookies)
        self.assertNotIn('csrftoken', response.cookies)
        self.assertIn('max-age=', response.headers['Strict-Transport-Security'])
        self.assertNotIn('includeSubDomains', response.headers['Strict-Transport-Security'])
        self.assertEqual(self.get(client, '/api/session').json()['user']['id'], self.user.pk)
        logout = self.post(client, '/api/auth/logout', {}, token=response.json()['csrf_token'])
        self.assertEqual(logout.cookies['organiza_sessionid']['max-age'], 0)
        self.assertTrue(logout.cookies['organiza_sessionid']['secure'])
        self.assertIsNone(self.get(client, '/api/session').json()['user'])

    def test_local_http_keeps_working_without_https_only_cookie_requirement(self):
        client, response = self.login(private=False)
        self.assertIn('sessionid', response.cookies)
        self.assertIn('csrftoken', response.cookies)
        self.assertFalse(response.cookies['sessionid']['secure'])
        self.assertFalse(response.cookies['csrftoken']['secure'])
        self.assertNotIn('organiza_sessionid', response.cookies)
        self.assertEqual(self.get(client, '/api/session', private=False).json()['user']['id'], self.user.pk)
        self.post(client, '/api/auth/logout', {}, private=False, token=response.json()['csrf_token'])
        self.assertIsNone(self.get(client, '/api/session', private=False).json()['user'])

    def test_private_csrf_rejects_missing_token_and_wrong_origin(self):
        client = Client(enforce_csrf_checks=True)
        initial = self.get(client, '/api/session').json()
        payload = {'username': self.user.username, 'password': self.password}
        self.post(client, '/api/auth/login', payload, expected=403)
        self.post(client, '/api/auth/login', payload, token=initial['csrf_token'], origin='https://untrusted.invalid', expected=403)
        login = self.post(client, '/api/auth/login', payload, token=initial['csrf_token'])
        self.post(client, '/api/spaces', {'name': 'Fictitious rejected'}, token=login.json()['csrf_token'],
                  origin='https://untrusted.invalid', expected=403)
        self.assertEqual(self.get(client, '/api/spaces').json()['spaces'], [])

    def test_generic_cookie_from_other_app_is_not_accepted_as_private_session(self):
        _, response = self.login()
        stranger = Client()
        stranger.cookies['sessionid'] = response.cookies['organiza_sessionid'].value
        self.assertIsNone(self.get(stranger, '/api/session').json()['user'])

    def test_roles_and_space_isolation_remain_enforced_on_private_https(self):
        admin, login = self.login()
        token = login.json()['csrf_token']
        space = self.post(admin, '/api/spaces', {'name': 'Espaço fictício HTTPS'}, token=token, expected=201).json()['space']['id']
        clients = {}
        for name, role in [('private_collab', 'collaborator'), ('private_reader', 'reader'), ('private_other', None)]:
            person = get_user_model().objects.create_user(username=name, password=self.password)
            client = Client(enforce_csrf_checks=True)
            initial = self.get(client, '/api/session').json()
            signed = self.post(client, '/api/auth/login', {'username': person.username, 'password': self.password}, token=initial['csrf_token']).json()
            clients[name] = (client, signed['csrf_token'])
            if role:
                self.post(admin, f'/api/spaces/{space}/members', {'username': name, 'role': role}, token=token)
        url = f'/api/spaces/{space}/actions'
        data = {'action': 'account.create', 'data': {'name': 'Conta fictícia HTTPS'}, 'expected_revision': 0, 'request_id': str(uuid.uuid4())}
        collaborator, csrf = clients['private_collab']
        self.post(collaborator, url, data, token=csrf)
        reader, csrf = clients['private_reader']
        self.assertEqual(self.get(reader, f'/api/spaces/{space}/state').status_code, 200)
        self.post(reader, url, {**data, 'expected_revision': 1, 'request_id': str(uuid.uuid4())}, token=csrf, expected=403)
        other, csrf = clients['private_other']
        self.assertEqual(self.get(other, f'/api/spaces/{space}/state').status_code, 404)
        self.post(other, url, {**data, 'expected_revision': 1, 'request_id': str(uuid.uuid4())}, token=csrf, expected=404)
