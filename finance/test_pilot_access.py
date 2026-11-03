"""Pilot approval and technical administration use disposable test databases."""
import concurrent.futures
import json
import threading
from datetime import timedelta
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .models import FinancialState, LoginAttempt, Membership, UserAccessEvent

User = get_user_model()
PASSWORD = 'Fictitious-pilot-access-89412!'


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], REGISTRATION_MODE='approval')
class PilotAccessTests(TestCase):
    def setUp(self):
        self.technical = User.objects.create_superuser(username='pilot_technical', password=PASSWORD)
        self.staff = User.objects.create_user(username='pilot_staff', password=PASSWORD, is_staff=True)
        self.member = User.objects.create_user(username='pilot_member', password=PASSWORD)
        self.pending = User.objects.create_user(username='pilot_pending', password=PASSWORD, is_active=False)
        self.admin = Client()
        self.admin.force_login(self.technical)

    def post(self, client, path, data, expected=200, **headers):
        response = client.post(path, data=json.dumps(data), content_type='application/json', **headers)
        self.assertEqual(response.status_code, expected, response.content[:700])
        return response.json()

    def status(self, user=None):
        return f'/api/technical/users/{(user or self.pending).pk}/status'

    def test_approval_registration_does_not_login_or_create_financial_data(self):
        client = Client()
        response = self.post(client, '/api/auth/register', {
            'username': 'pilot_requested', 'display_name': 'Pessoa fictícia', 'password': PASSWORD,
        }, 202)
        self.assertTrue(response['registration_pending'])
        self.assertIsNone(response['user'])
        person = User.objects.get(username='pilot_requested')
        self.assertFalse(person.is_active)
        self.assertTrue(person.check_password(PASSWORD))
        self.assertIsNone(client.get('/api/session').json()['user'])
        self.assertEqual(client.get('/api/spaces').status_code, 401)
        self.assertEqual(FinancialState.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.post(client, '/api/auth/login', {'username': person.username, 'password': PASSWORD}, 401)

    @override_settings(REGISTRATION_MODE='closed')
    def test_closed_registration_does_not_create_a_user(self):
        before = User.objects.count()
        response = Client().get('/api/session').json()
        self.assertEqual(response['registration_mode'], 'closed')
        self.post(Client(), '/api/auth/register', {'username': 'pilot_denied', 'password': PASSWORD}, 403)
        self.assertEqual(User.objects.count(), before)

    @override_settings(REGISTRATION_MODE='open')
    def test_open_mode_keeps_existing_local_registration_behavior(self):
        client = Client()
        result = self.post(client, '/api/auth/register', {'username': 'pilot_open', 'password': PASSWORD}, 201)
        user = User.objects.get(pk=result['user']['id'])
        self.assertTrue(user.is_active)
        self.assertFalse(result['user']['technical_admin'])
        self.assertEqual(client.get('/api/session').json()['user']['id'], user.pk)

    def test_only_superuser_can_list_global_accounts_and_no_secrets_are_returned(self):
        self.assertEqual(Client().get('/api/technical/users').status_code, 401)
        for person in (self.member, self.staff):
            client = Client()
            client.force_login(person)
            self.assertEqual(client.get('/api/technical/users').status_code, 403)
        response = self.admin.get('/api/technical/users')
        self.assertEqual(response.status_code, 200)
        users = response.json()['users']
        self.assertEqual(len(users), 4)
        allowed = {'id', 'username', 'display_name', 'technical_admin', 'is_active', 'status'}
        for row in users:
            self.assertEqual(set(row), allowed)
        for person in (self.technical, self.member, self.pending):
            self.assertNotIn(person.password, response.content.decode())
        self.assertNotIn(PASSWORD, response.content.decode())
        self.assertEqual(self.admin.get('/api/technical/users?offset=-1').status_code, 400)
        self.assertEqual(self.admin.get('/api/technical/users?offset=invalid').json()['error'], 'Página de contas inválida.')

    def test_approval_is_audited_idempotent_and_preserves_password_and_permissions(self):
        original_hash = self.pending.password
        first = self.post(self.admin, self.status(), {'is_active': True})
        self.assertTrue(first['changed'])
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertEqual(self.pending.password, original_hash)
        self.assertFalse(self.pending.is_staff)
        self.assertFalse(self.pending.is_superuser)
        event = UserAccessEvent.objects.get()
        self.assertEqual((event.actor_id, event.subject_id), (self.technical.pk, self.pending.pk))
        self.assertEqual((event.before_active, event.after_active), (False, True))
        repeated = self.post(self.admin, self.status(), {'is_active': True})
        self.assertFalse(repeated['changed'])
        self.assertEqual(UserAccessEvent.objects.count(), 1)
        client = Client()
        self.post(client, '/api/auth/login', {'username': self.pending.username, 'password': PASSWORD})
        self.assertEqual(client.get('/api/session').json()['user']['id'], self.pending.pk)

    def test_blocking_revokes_existing_session_without_deleting_membership_or_finances(self):
        client = Client()
        client.force_login(self.member)
        space = self.post(client, '/api/spaces', {'name': 'Espaço fictício preservado'}, 201)['space']['id']
        before = client.get(f'/api/spaces/{space}/state').json()
        result = self.post(self.admin, self.status(self.member), {'is_active': False})
        self.assertTrue(result['changed'])
        self.assertIsNone(client.get('/api/session').json()['user'])
        self.assertEqual(client.get(f'/api/spaces/{space}/state').status_code, 401)
        self.assertEqual(Membership.objects.filter(workspace_id=space, user=self.member).count(), 1)
        self.assertEqual(FinancialState.objects.get(workspace_id=space).revision, before['revision'])
        self.assertEqual(UserAccessEvent.objects.get().after_active, False)

    def test_technical_account_cannot_block_itself_or_grant_privileges(self):
        self.post(self.admin, self.status(self.technical), {'is_active': False}, 400)
        self.post(self.admin, self.status(), {'is_active': True, 'is_superuser': True}, 400)
        self.post(self.admin, self.status(), {'is_active': 'true'}, 400)
        self.assertEqual(self.admin.delete(self.status()).status_code, 405)
        self.pending.refresh_from_db()
        self.technical.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.assertFalse(self.pending.is_superuser)
        self.assertTrue(self.technical.is_active)
        self.assertEqual(UserAccessEvent.objects.count(), 0)

    def test_approval_csrf_is_enforced_and_regular_admin_cannot_change_global_access(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.technical)
        self.post(strict, self.status(), {'is_active': True}, 403)
        token = strict.get('/api/session').json()['csrf_token']
        self.post(strict, self.status(), {'is_active': True}, HTTP_X_CSRFTOKEN=token)
        ordinary = Client()
        ordinary.force_login(self.member)
        self.post(ordinary, self.status(), {'is_active': False}, 403)
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)

    def test_participants_show_identifiers_role_and_account_status_only_in_their_space(self):
        member = Client()
        member.force_login(self.member)
        space = self.post(member, '/api/spaces', {'name': 'Participantes fictícios'}, 201)['space']['id']
        members = self.post(member, f'/api/spaces/{space}/members', {'username': self.pending.username, 'role': 'reader'})['members']
        pending = next(row for row in members if row['user_id'] == self.pending.pk)
        self.assertIsInstance(pending['id'], int)
        self.assertEqual(pending['role'], 'reader')
        self.assertFalse(pending['is_active'])
        self.assertEqual(pending['status'], 'blocked')
        self.assertEqual(member.get('/api/technical/users').status_code, 403)
        self.post(member, self.status(), {'is_active': True}, 403)
        # Technical administration does not bypass financial workspace membership.
        self.assertEqual(self.admin.get(f'/api/spaces/{space}/members').status_code, 404)
        self.assertEqual(self.admin.get(f'/api/spaces/{space}/state').status_code, 404)

    def test_login_throttle_persists_per_account_across_different_ips(self):
        for index in range(10):
            self.post(Client(), '/api/auth/login', {'username': self.member.username, 'password': 'invalid'}, 401,
                      REMOTE_ADDR=f'192.0.2.{index + 1}', HTTP_X_FORWARDED_FOR=f'198.51.100.{index + 1}')
        self.post(Client(), '/api/auth/login', {'username': self.member.username, 'password': PASSWORD}, 429,
                  REMOTE_ADDR='192.0.2.99')
        self.assertGreater(LoginAttempt.objects.count(), 0)
        LoginAttempt.objects.update(window_start=timezone.now() - timedelta(minutes=16))
        self.post(Client(), '/api/auth/login', {'username': self.member.username, 'password': PASSWORD},
                  REMOTE_ADDR='192.0.2.100')

    def test_successful_login_clears_its_failed_attempt_buckets(self):
        client = Client()
        self.post(client, '/api/auth/login', {'username': self.member.username, 'password': 'invalid'}, 401)
        self.assertEqual(LoginAttempt.objects.count(), 2)
        self.post(client, '/api/auth/login', {'username': self.member.username, 'password': PASSWORD})
        self.assertEqual(LoginAttempt.objects.count(), 0)


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row-lock concurrency check')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TechnicalAccountConcurrencyTests(TransactionTestCase):
    def test_concurrent_technical_blocks_leave_one_active_administrator(self):
        first = User.objects.create_superuser(username='concurrent_technical_a', password=PASSWORD)
        second = User.objects.create_superuser(username='concurrent_technical_b', password=PASSWORD)
        clients = [Client(), Client()]
        clients[0].force_login(first)
        clients[1].force_login(second)
        barrier = threading.Barrier(2)

        def block(index):
            try:
                barrier.wait(timeout=10)
                target = (second, first)[index]
                return clients[index].post(f'/api/technical/users/{target.pk}/status',
                                           data=json.dumps({'is_active': False}), content_type='application/json').status_code
            finally:
                connections.close_all()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(block, (0, 1)))
        self.assertEqual(statuses.count(200), 1, statuses)
        self.assertTrue(all(code in (200, 401, 403) for code in statuses), statuses)
        self.assertEqual(User.objects.filter(is_superuser=True, is_active=True).count(), 1)
        self.assertEqual(UserAccessEvent.objects.count(), 1)
