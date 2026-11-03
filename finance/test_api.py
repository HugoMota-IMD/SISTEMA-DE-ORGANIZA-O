"""Integration checks use independent sessions and fictitious financial data only."""

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import Http404
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from .models import AuditEvent, FinancialState, Membership, Operation
from .security import actor_context


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FinancialApiTests(TestCase):
    password = 'Fictional-test-passphrase-42!'

    def post_json(self, client, url, data, expected=200, method='post', **headers):
        response = getattr(client, method)(url, data=json.dumps(data), content_type='application/json', **headers)
        self.assertEqual(response.status_code, expected, response.content[:1000])
        return response.json()

    def register(self, name, client=None):
        client = client or Client()
        result = self.post_json(client, '/api/auth/register', {
            'username': name, 'display_name': name, 'password': self.password,
        }, expected=201)
        return client, result['user']['id']

    def setUp(self):
        self.admin, self.admin_id = self.register('qa_admin')
        self.other, self.other_id = self.register('qa_other')
        self.reader, self.reader_id = self.register('qa_reader')
        self.space = self.post_json(self.admin, '/api/spaces', {'name': 'Pessoal fictício'}, 201)['space']['id']
        self.other_space = self.post_json(self.other, '/api/spaces', {'name': 'Outro fictício'}, 201)['space']['id']
        self.members_url = f'/api/spaces/{self.space}/members'
        self.post_json(self.admin, self.members_url, {'username': 'qa_reader', 'role': 'reader'})

    def state(self, client=None, space=None):
        response = (client or self.admin).get(f'/api/spaces/{space or self.space}/state')
        self.assertEqual(response.status_code, 200, response.content[:1000])
        return response.json()

    def action(self, action, data, *, client=None, space=None, revision=None, request_id=None, expected=200):
        space = space or self.space
        client = client or self.admin
        if revision is None:
            revision = self.state(client, space)['revision']
        return self.post_json(client, f'/api/spaces/{space}/actions', {
            'action': action, 'data': data, 'expected_revision': revision,
            'request_id': request_id or str(uuid.uuid4()),
        }, expected)

    def test_authentication_and_persistent_independent_session(self):
        anonymous = Client()
        self.assertIsNone(anonymous.get('/api/session').json()['user'])
        self.assertEqual(anonymous.get('/api/spaces').status_code, 401)
        self.post_json(anonymous, '/api/auth/login', {'username': 'qa_admin', 'password': 'incorrect'}, 401)
        login = self.post_json(anonymous, '/api/auth/login', {'username': 'QA_ADMIN', 'password': self.password})
        self.assertEqual(login['user']['id'], self.admin_id)
        self.assertEqual(self.state(anonymous), self.state())
        self.post_json(anonymous, '/api/auth/logout', {})
        self.assertEqual(anonymous.get(f'/api/spaces/{self.space}/state').status_code, 401)
        self.assertEqual(self.admin.get(f'/api/spaces/{self.space}/state').status_code, 200)
        stored = get_user_model().objects.get(pk=self.admin_id)
        self.assertNotEqual(stored.password, self.password)
        self.assertTrue(stored.check_password(self.password))

    def test_space_membership_isolation_and_no_implicit_family_access(self):
        visible = self.other.get('/api/spaces').json()['spaces']
        self.assertEqual([space['id'] for space in visible], [self.other_space])
        self.assertEqual(self.other.get(f'/api/spaces/{self.space}/state').status_code, 404)
        self.assertEqual(self.other.get(self.members_url).status_code, 404)
        self.action('unknown', {}, client=self.other, space=self.space, revision=0, expected=404)
        self.post_json(self.other, self.members_url, {'username': 'qa_other', 'role': 'admin'}, 404)
        self.assertEqual(self.admin.get(f'/api/spaces/{self.other_space}/state').status_code, 404)

    def test_reader_cannot_mutate_or_manage_participants(self):
        self.assertEqual(self.state(self.reader)['space']['role'], 'reader')
        self.action('unknown', {}, client=self.reader, revision=0, expected=403)
        self.post_json(self.reader, self.members_url, {'username': 'qa_other', 'role': 'admin'}, 403)
        own = next(m for m in self.state(self.reader)['members'] if m['user_id'] == self.reader_id)
        self.post_json(self.reader, f'{self.members_url}/{own["id"]}', {'role': 'admin'}, 403)

    def test_member_management_last_admin_and_revocation(self):
        members = self.state()['members']
        admin = next(m for m in members if m['user_id'] == self.admin_id)
        reader = next(m for m in members if m['user_id'] == self.reader_id)
        self.post_json(self.admin, f'{self.members_url}/{admin["id"]}', {'role': 'reader'}, 400)
        self.post_json(self.admin, f'{self.members_url}/{admin["id"]}', {}, 400, method='delete')
        self.post_json(self.admin, f'{self.members_url}/{reader["id"]}', {'role': 'collaborator'})
        self.assertEqual(self.state(self.reader)['space']['role'], 'collaborator')
        self.post_json(self.reader, self.members_url, {'username': 'qa_other', 'role': 'reader'}, 403)
        self.post_json(self.admin, f'{self.members_url}/{reader["id"]}', {}, method='delete')
        self.assertEqual(self.reader.get(f'/api/spaces/{self.space}/state').status_code, 404)

    def test_invalid_requests_are_rejected_without_partial_state(self):
        before = self.state()
        response = self.admin.post(f'/api/spaces/{self.space}/actions', data='{bad', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response = self.admin.post(f'/api/spaces/{self.space}/actions', data='[]', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.action('unrecognized_action', {}, expected=400)
        self.action('unrecognized_action', {}, revision=True, expected=400)
        self.action('unrecognized_action', {}, request_id='invalid-id', expected=400)
        self.action('unrecognized_action', {'person_id': self.other_id}, expected=400)
        self.assertEqual(self.state(), before)
        self.assertFalse(Operation.objects.filter(workspace_id=self.space).exists())

    def test_csrf_is_enforced_for_authenticated_mutations(self):
        strict = Client(enforce_csrf_checks=True)
        session = strict.get('/api/session').json()
        self.post_json(strict, '/api/auth/login', {'username': 'qa_admin', 'password': self.password}, 403)
        login = self.post_json(strict, '/api/auth/login', {'username': 'qa_admin', 'password': self.password}, HTTP_X_CSRFTOKEN=session['csrf_token'])
        self.post_json(strict, '/api/spaces', {'name': 'CSRF rejected'}, 403)
        self.post_json(strict, '/api/spaces', {'name': 'CSRF accepted'}, 201, HTTP_X_CSRFTOKEN=login['csrf_token'])

    def test_database_rejects_financial_writes_without_authorized_actor(self):
        for user_id in (0, self.other_id, self.reader_id):
            with self.subTest(user_id=user_id):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic(), actor_context(user_id):
                        FinancialState.objects.filter(workspace_id=self.space).update(revision=1)
        self.assertEqual(FinancialState.objects.get(workspace_id=self.space).revision, 0)

    def test_database_preserves_revision_and_immutable_audit(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), actor_context(self.admin_id):
                FinancialState.objects.filter(workspace_id=self.space).update(revision=0)
        event = AuditEvent.objects.filter(workspace_id=self.space).first()
        for operation in ('update', 'delete'):
            with self.subTest(operation=operation), self.assertRaises(IntegrityError):
                with transaction.atomic(), actor_context(self.admin_id):
                    query = AuditEvent.objects.filter(pk=event.pk)
                    query.update(action='forged') if operation == 'update' else query.delete()
        self.assertEqual(AuditEvent.objects.get(pk=event.pk).action, event.action)

    def test_database_rejects_role_escalation_and_last_admin_removal(self):
        reader = Membership.objects.get(workspace_id=self.space, user_id=self.reader_id)
        admin = Membership.objects.get(workspace_id=self.space, user_id=self.admin_id)
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), actor_context(self.reader_id):
                Membership.objects.filter(pk=reader.pk).update(role='admin')
        with self.assertRaises(IntegrityError):
            with transaction.atomic(), actor_context(self.admin_id):
                Membership.objects.filter(pk=admin.pk).delete()

    def test_complete_financial_flow_and_cross_session_persistence(self):
        today = timezone.localdate().isoformat()
        account = self.action('account.create', {
            'name': 'Conta QA', 'opening_balance_cents': 100000,
            'reference_date': today, 'owner_id': self.admin_id,
        })['result']['id']
        card = self.action('card.create', {
            'name': 'Cartão QA', 'account_id': account, 'closing_day': 5,
            'due_day': 15, 'limit_cents': 200000, 'last_four': '1234',
        })['result']['id']
        income = self.action('entry.create', {
            'kind': 'income', 'description': 'Receita fictícia', 'amount_cents': 50000,
            'account_id': account, 'method': 'pix', 'due_date': today,
        })
        self.assertEqual(income['state']['balance_cents'], 100000)
        self.assertEqual(income['state']['income_pending_cents'], 50000)
        obligation = next(o for o in income['state']['obligations'] if o['entry_id'] == income['result']['id'])
        received = self.action('obligation.pay', {'obligation_id': obligation['id'], 'account_id': account, 'paid_on': today})
        self.assertEqual(received['state']['balance_cents'], 150000)
        self.assertEqual(received['state']['income_pending_cents'], 0)
        food = next(c['id'] for c in received['state']['categories'] if c['name'] == 'Alimentação')
        for merchant, amount, method in [('iFood', 10000, 'pix'), ('Crepes e Crepes', 18500, 'debit')]:
            self.action('entry.create', {
                'kind': 'expense', 'description': merchant, 'merchant': merchant,
                'amount_cents': amount, 'category_id': food, 'account_id': account,
                'method': method, 'paid': True, 'paid_on': today,
                'person_id': self.reader_id, 'paid_by': self.admin_id,
            })
        before_card = self.state()
        self.assertEqual(before_card['balance_cents'], 121500)
        food_row = next(row for row in before_card['reports']['by_category'] if row['id'] == food)
        self.assertEqual(food_row['amount_cents'], 28500)
        purchase = self.action('entry.create', {
            'kind': 'expense', 'description': 'Compra parcelada fictícia',
            'amount_cents': 100000, 'category_id': food, 'card_id': card,
            'method': 'credit', 'installments': 3, 'purchase_date': today,
            'due_date': today,
        })
        installments = [o for o in purchase['state']['obligations'] if o['entry_id'] == purchase['result']['id']]
        self.assertEqual(sum(o['amount_cents'] for o in installments), 100000)
        self.assertEqual([o['amount_cents'] for o in installments], [33334, 33333, 33333])
        self.assertTrue(all(o['card_id'] == card for o in installments))
        self.assertEqual(purchase['state']['debt_cents'], 100000)
        first_invoice = installments[0]['invoice_id']
        partial = self.action('invoice.pay', {
            'invoice_id': first_invoice, 'account_id': account,
            'amount_cents': 10000, 'paid_on': today, 'paid_by': self.admin_id,
        })
        invoice = next(i for i in partial['state']['invoices'] if i['id'] == first_invoice)
        self.assertEqual(invoice['remaining_cents'], 23334)
        self.assertEqual(invoice['status'], 'partial')
        self.assertEqual(partial['state']['balance_cents'], 111500)
        self.assertEqual(partial['state']['debt_cents'], 90000)
        self.assertEqual(partial['state']['reports']['expense_cents'], 128500)
        self.assertEqual(partial['state']['reports']['cash_expense_cents'], 38500)
        self.assertEqual(partial['state']['projection'][0]['commitment_cents'], 23334)
        settled = self.action('invoice.pay', {
            'invoice_id': first_invoice, 'account_id': account,
            'amount_cents': 23334, 'paid_on': today,
        })
        self.assertEqual(settled['state']['balance_cents'], 88166)
        self.assertEqual(settled['state']['debt_cents'], 66666)
        self.assertEqual(settled['state']['reports']['expense_cents'], 128500)
        self.assertEqual(len(settled['state']['projection']), 12)
        self.assertEqual(settled['state']['accounts'], self.state(self.reader)['accounts'])
        second_device = Client()
        self.post_json(second_device, '/api/auth/login', {'username': 'qa_admin', 'password': self.password})
        for key in ('balance_cents', 'debt_cents', 'projection', 'obligations', 'payments'):
            self.assertEqual(self.state(second_device)[key], settled['state'][key])

    def test_request_idempotency_and_concurrent_revision(self):
        request_id = str(uuid.uuid4())
        data = {'name': 'Conta idempotente', 'opening_balance_cents': 10000}
        first = self.action('account.create', data, revision=0, request_id=request_id)
        repeated = self.action('account.create', data, revision=0, request_id=request_id)
        self.assertTrue(repeated['duplicate'])
        self.assertEqual(first['result'], repeated['result'])
        self.assertEqual(repeated['revision'], 1)
        self.assertEqual(len(repeated['state']['accounts']), 1)
        self.assertEqual(Operation.objects.filter(workspace_id=self.space).count(), 1)
        self.action('account.create', {'name': 'Conflito'}, revision=0, expected=409)
        self.action('account.create', {'name': 'Conteúdo diferente'}, revision=1, request_id=request_id, expected=409)
        self.action('account.create', data, client=self.reader, revision=0, request_id=request_id, expected=403)
        self.action('account.create', data, client=self.other, space=self.space, revision=0, request_id=request_id, expected=404)
        self.assertEqual(FinancialState.objects.get(workspace_id=self.space).revision, 1)

    def test_foreign_financial_references_and_card_secrets_rejected(self):
        foreign_account = self.action('account.create', {'name': 'Conta externa'}, client=self.other, space=self.other_space)['result']['id']
        before = self.state()
        self.action('entry.create', {
            'kind': 'expense', 'description': 'Referência externa', 'amount_cents': 100,
            'method': 'pix', 'account_id': foreign_account,
        }, expected=400)
        for sensitive in ('cvv', 'cvc', 'pan', 'number', 'card_number', 'password', 'pin'):
            with self.subTest(field=sensitive):
                self.action('card.create', {
                    'name': 'Cartão rejeitado', 'closing_day': 5, 'due_day': 15,
                    'limit_cents': 10000, sensitive: '1234567890',
                }, expected=400)
        self.assertEqual(self.state(), before)

    def test_money_and_person_types_rejected_without_coercion(self):
        for amount in (1.5, True, '100'):
            with self.subTest(amount=amount):
                self.action('account.create', {'name': 'Valor inválido', 'opening_balance_cents': amount}, expected=400)
        for person_id in (self.admin_id + 0.5, True, 'invalid'):
            with self.subTest(person_id=person_id):
                self.action('account.create', {'name': 'Pessoa inválida', 'owner_id': person_id}, expected=400)

    def test_simulation_reader_has_no_persisted_effect(self):
        before = self.state()
        simulated = self.action('simulation', {
            'amount_cents': 120000, 'installments': 6, 'due_date': timezone.localdate().isoformat(),
        }, client=self.reader)
        self.assertEqual(sum(row['simulation_cents'] for row in simulated['result']['projection']), 120000)
        self.assertEqual([row['simulation_cents'] for row in simulated['result']['projection'][:6]], [20000] * 6)
        self.assertEqual(self.state(), before)

    def test_nested_person_reference_in_recurrence_cannot_escape_membership(self):
        account = self.action('account.create', {'name': 'Conta recorrência'})['result']['id']
        created = self.action('entry.create', {
            'kind': 'expense', 'description': 'Assinatura fictícia', 'amount_cents': 1000,
            'account_id': account, 'method': 'pix', 'recurrence': True,
            'due_date': timezone.localdate().isoformat(),
        })
        before = self.state()
        self.action('recurrence.update', {
            'recurrence_id': created['result']['recurrence']['id'], 'scope': 'future',
            'from_date': timezone.localdate().isoformat(),
            'changes': {'person_id': self.other_id},
        }, expected=400)
        self.assertEqual(self.state(), before)

    def test_collaborator_writes_with_authenticated_author_and_cannot_forge_fields(self):
        member = next(m for m in self.state()['members'] if m['user_id'] == self.reader_id)
        self.post_json(self.admin, f'{self.members_url}/{member["id"]}', {'role': 'collaborator'})
        created = self.action('account.create', {
            'name': 'Conta colaborativa', 'owner_id': self.admin_id,
        }, client=self.reader)
        self.assertEqual(created['result']['account']['created_by'], self.reader_id)
        self.assertEqual(created['result']['account']['owner_id'], self.admin_id)
        event = AuditEvent.objects.filter(workspace_id=self.space).order_by('-id').first()
        self.assertEqual(event.actor_id, self.reader_id)
        self.assertEqual(Operation.objects.get(workspace_id=self.space).actor_id, self.reader_id)
        self.action('account.create', {
            'name': 'Autoria forjada', 'created_by': self.admin_id,
        }, client=self.reader, expected=400)

    def test_static_paths_reject_windows_and_traversal_before_filesystem_resolution(self):
        from .views import static_asset

        request = RequestFactory().get('/')
        forbidden = ('../README.md', 'sub/../../.env', '/etc/passwd',
                     r'C:\Windows\win.ini', r'\\qa.invalid\share\file', 'app.js:stream')
        # Prevent any OS path resolution in this regression test, including UNC.
        with patch('finance.views.Path.resolve', side_effect=AssertionError('Unsafe path reached the filesystem')):
            for asset in forbidden:
                with self.subTest(asset=asset), self.assertRaises(Http404):
                    static_asset(request, asset)
        self.assertEqual(self.admin.get('/static/../README.md').status_code, 404)
