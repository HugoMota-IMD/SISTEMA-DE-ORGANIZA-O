"""Real PostgreSQL guard regressions, always using Django's isolated test DB."""
import concurrent.futures
import threading
import uuid
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings

from .domain import new_state
from .models import AuditEvent, FinancialState, Membership, Operation, Workspace
from .security import actor_context, import_context


POSTGRES = connection.vendor == 'postgresql'


def settings_state():
    with connection.cursor() as cursor:
        cursor.execute('SELECT finance_actor(), finance_import_mode()')
        return cursor.fetchone()


@skipUnless(POSTGRES, 'PostgreSQL write guards require an isolated PostgreSQL test database.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PostgresGuardTests(TestCase):
    def setUp(self):
        user = get_user_model()
        self.admin, self.collaborator, self.reader, self.foreign = [
            user.objects.create_user(username='pg_guard_' + name, password='Fictitious-guards-49261!')
            for name in ('admin', 'collaborator', 'reader', 'foreign')
        ]
        with actor_context(self.admin.pk):
            self.space = Workspace.objects.create(name='Espaço fictício PostgreSQL', created_by=self.admin)
            self.admin_member = Membership.objects.create(workspace=self.space, user=self.admin, role='admin')
            Membership.objects.create(workspace=self.space, user=self.collaborator, role='collaborator')
            Membership.objects.create(workspace=self.space, user=self.reader, role='reader')
            FinancialState.objects.create(workspace=self.space, document=new_state())
            self.event = AuditEvent.objects.create(workspace=self.space, actor=self.admin,
                                                  action='fictitious.setup', details={})
            self.operation = Operation.objects.create(workspace=self.space, actor=self.admin,
                                                       request_id=uuid.uuid4(), fingerprint='a' * 64, result={})

    def test_missing_foreign_and_reader_actor_cannot_write_financial_state(self):
        for user in (None, self.reader, self.foreign):
            with self.subTest(user=user.pk if user else 0), self.assertRaises(IntegrityError):
                with actor_context(user.pk if user else 0):
                    FinancialState.objects.filter(workspace=self.space).update(revision=1)
        self.assertEqual(FinancialState.objects.get(workspace=self.space).revision, 0)

    def test_collaborator_advances_exactly_once_and_cannot_forge_history_actor(self):
        with actor_context(self.collaborator.pk):
            self.assertEqual(FinancialState.objects.filter(workspace=self.space, revision=0).update(revision=1), 1)
        with self.assertRaises(IntegrityError), actor_context(self.admin.pk):
            FinancialState.objects.filter(workspace=self.space).update(revision=3)
        with self.assertRaises(IntegrityError), actor_context(self.collaborator.pk):
            AuditEvent.objects.create(workspace=self.space, actor=self.admin, action='forged', details={})
        with self.assertRaises(IntegrityError), actor_context(self.collaborator.pk):
            Operation.objects.create(workspace=self.space, actor=self.admin, request_id=uuid.uuid4(),
                                     fingerprint='b' * 64, result={})

    def test_history_remains_immutable_even_inside_import_context(self):
        for model, pk in ((AuditEvent, self.event.pk), (Operation, self.operation.pk)):
            for action in ('update', 'delete'):
                with self.subTest(model=model.__name__, action=action), self.assertRaises(IntegrityError):
                    with import_context():
                        query = model.objects.filter(pk=pk)
                        query.update(actor=self.foreign) if action == 'update' else query.delete()
        self.assertEqual(AuditEvent.objects.get(pk=self.event.pk).actor_id, self.admin.pk)
        self.assertEqual(Operation.objects.get(pk=self.operation.pk).actor_id, self.admin.pk)

    def test_member_reassignment_escalation_and_last_admin_removal_rejected(self):
        reader = Membership.objects.get(workspace=self.space, user=self.reader)
        with self.assertRaises(IntegrityError), actor_context(self.reader.pk):
            Membership.objects.filter(pk=reader.pk).update(role='admin')
        with self.assertRaises(IntegrityError), actor_context(self.admin.pk):
            Membership.objects.filter(pk=reader.pk).update(user=self.foreign)
        with self.assertRaises(IntegrityError), actor_context(self.admin.pk):
            Membership.objects.filter(pk=self.admin_member.pk).update(role='reader')
        with self.assertRaises(IntegrityError), actor_context(self.admin.pk):
            Membership.objects.filter(pk=self.admin_member.pk).delete()

    def test_import_preserves_historical_revision_actor_and_records_then_closes_bypass(self):
        imported_id = uuid.uuid4()
        request_id = uuid.uuid4()
        with import_context():
            self.assertEqual(settings_state(), (0, True))
            historical = Workspace.objects.create(id=imported_id, name='Histórico fictício', created_by=self.foreign)
            Membership.objects.create(workspace=historical, user=self.foreign, role='admin')
            FinancialState.objects.create(workspace=historical, document=new_state(), revision=27)
            # A former author need not be a current member of the imported space.
            AuditEvent.objects.create(workspace=historical, actor=self.reader, action='historical', details={'kept': True})
            Operation.objects.create(workspace=historical, actor=self.reader, request_id=request_id,
                                     fingerprint='c' * 64, result={'original': True})
        self.assertEqual(settings_state(), (0, False))
        self.assertEqual(FinancialState.objects.get(workspace_id=imported_id).revision, 27)
        self.assertEqual(Operation.objects.get(request_id=request_id).actor_id, self.reader.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FinancialState.objects.filter(workspace_id=imported_id).update(revision=28)

    def test_failed_import_rolls_back_insertions_and_context(self):
        imported_id = uuid.uuid4()
        with self.assertRaises(IntegrityError):
            with import_context():
                Workspace.objects.create(id=imported_id, name='Importação fictícia falha', created_by=self.foreign)
                FinancialState.objects.create(workspace_id=None, document=new_state(), revision=9)
        self.assertFalse(Workspace.objects.filter(pk=imported_id).exists())
        self.assertEqual(settings_state(), (0, False))

    def test_nested_actor_and_import_settings_restore_without_session_state(self):
        self.assertEqual(settings_state(), (0, False))
        with actor_context(self.admin.pk):
            self.assertEqual(settings_state(), (self.admin.pk, False))
            with actor_context(self.collaborator.pk):
                self.assertEqual(settings_state(), (self.collaborator.pk, False))
            self.assertEqual(settings_state(), (self.admin.pk, False))
            with import_context():
                self.assertEqual(settings_state(), (0, True))
                with actor_context(self.reader.pk):
                    self.assertEqual(settings_state(), (self.reader.pk, False))
                self.assertEqual(settings_state(), (0, True))
            self.assertEqual(settings_state(), (self.admin.pk, False))
        self.assertEqual(settings_state(), (0, False))


@skipUnless(POSTGRES, 'Concurrency requires an isolated PostgreSQL test database.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PostgresGuardConcurrencyTests(TransactionTestCase):
    def test_two_admins_cannot_concurrently_remove_the_last_pair(self):
        users = [get_user_model().objects.create_user(username='pg_concurrent_admin_' + str(index)) for index in range(2)]
        with actor_context(users[0].pk):
            space = Workspace.objects.create(name='Dupla fictícia', created_by=users[0])
            members = [Membership.objects.create(workspace=space, user=user, role='admin') for user in users]
        barrier = threading.Barrier(2)

        def demote(index):
            try:
                with actor_context(users[index].pk):
                    barrier.wait(timeout=10)
                    Membership.objects.filter(pk=members[index].pk).update(role='reader')
                return 'updated'
            except IntegrityError:
                return 'blocked'
            finally:
                connections.close_all()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(demote, index) for index in range(2)]
            outcomes = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(outcomes), ['blocked', 'updated'])
        self.assertEqual(Membership.objects.filter(workspace=space, role='admin').count(), 1)

    def test_actor_is_zero_after_committed_and_failed_transactions(self):
        user = get_user_model().objects.create_user(username='pg_context_reuse')
        with actor_context(user.pk):
            self.assertEqual(settings_state(), (user.pk, False))
        self.assertEqual(settings_state(), (0, False))
        with self.assertRaises(RuntimeError):
            with import_context():
                self.assertEqual(settings_state(), (0, True))
                raise RuntimeError('Fictitious interrupted management operation')
        self.assertEqual(settings_state(), (0, False))
