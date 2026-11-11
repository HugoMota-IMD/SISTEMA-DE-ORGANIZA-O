"""Management guardrails, without connecting to any database server."""
from contextlib import closing, redirect_stderr
import hashlib
from io import StringIO
import os
from pathlib import Path
import sqlite3
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from tools.postgres_common import ROOT, direct_url, libpq_environment, private_temporary, require_local_test_database
from tools.migrate_sqlite_postgres import main as migration_main, sqlite_source
from tools.postgres_backup import backup, restore


class PostgresManagementTests(unittest.TestCase):
    def test_render_pair_requires_two_dedicated_roles_on_the_same_branch_and_database(self):
        from tools.render_roles import check_urls
        app = 'postgresql://organiza_app@ep-test-pooler.example.invalid/neondb'
        manager = 'postgresql://organiza_migrator@ep-test.example.invalid/neondb'
        check_urls(app, manager)
        for a, m in [(app.replace('organiza_app', 'neondb_owner'), manager),
                     (app, manager.replace('organiza_migrator', 'organiza_app')),
                     (app.replace('-pooler', ''), manager),
                     (app, manager.replace('ep-test', 'ep-other')),
                     (app, manager.replace('invalid/', 'invalid:5433/')),
                     (app, manager.replace('neondb', 'other'))]:
            with self.subTest(a=a, m=m), self.assertRaises(RuntimeError):
                check_urls(a, m)

    def test_local_sqlite_runner_and_fixture_refuse_inherited_postgres_connection(self):
        from config.database import database_configuration
        from tools.organiza_runtime import start
        values = {'APP_DB_PATH': 'test-results/example.sqlite3',
                  'DATABASE_URL': 'postgresql://fixture@unused.invalid/example'}
        with patch.dict(os.environ, values, clear=True), self.assertRaises(RuntimeError):
            database_configuration(ROOT, hosted=False)
        with self.assertRaises(RuntimeError):
            start({'environment': values})

    def test_missing_and_pooled_management_connections_rejected(self):
        for values in ({}, {'DATABASE_URL': 'postgresql://fictitious@ep-example-pooler.neon.tech/organiza'}):
            with self.subTest(values=list(values)), patch.dict(os.environ, values, clear=True):
                with self.assertRaises(RuntimeError):
                    direct_url()

    def test_management_prefers_direct_connection_and_rejects_plaintext_remote(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://fictitious@pool-pooler.example/db',
                                    'DATABASE_URL_UNPOOLED': 'postgresql://fictitious@direct.example/db?sslmode=require'}, clear=True):
            self.assertEqual(urlsplit(direct_url()).hostname, 'direct.example')
            self.assertEqual(parse_qs(urlsplit(direct_url()).query)['sslmode'], ['verify-full'])
        for mode in ('disable', 'allow', 'prefer'):
            with patch.dict(os.environ, {'DATABASE_URL_UNPOOLED': f'postgresql://fictitious@direct.example/db?sslmode={mode}'}, clear=True):
                with self.assertRaises(RuntimeError):
                    direct_url()

    def test_remote_tools_and_native_clients_use_same_trust_store_without_tls_option(self):
        with patch.dict(os.environ, {'DATABASE_URL_UNPOOLED': 'postgresql://fixture@direct.example/db'}, clear=True):
            query = parse_qs(urlsplit(direct_url()).query)
            with libpq_environment() as env:
                self.assertEqual(env['PGSSLMODE'], 'verify-full')
                self.assertEqual(env['PGSSLROOTCERT'], query['sslrootcert'][0])
                self.assertTrue(Path(env['PGSSLROOTCERT']).is_file())

    def test_management_query_cannot_override_approved_destination(self):
        for suffix in ('host=another.example', 'dbname=another', 'sslmode=require&sslmode=disable'):
            with self.subTest(suffix=suffix), patch.dict(os.environ, {
                'DATABASE_URL_UNPOOLED': 'postgresql://fixture@127.0.0.1/test?' + suffix,
            }, clear=True), self.assertRaises(RuntimeError):
                direct_url()

    def test_fixture_import_refuses_remote_and_local_operational_databases(self):
        for url in ('postgresql://fixture@remote.example/organiza_test_x',
                    'postgresql://fixture@127.0.0.1/organiza'):
            with patch.dict(os.environ, {'DATABASE_URL_UNPOOLED': url}, clear=True), self.assertRaises(RuntimeError):
                require_local_test_database()

    def test_passfile_is_private_ephemeral_and_credentials_not_in_child_environment(self):
        url = 'postgresql://fictitious:fictional%3Apass%5Cword@127.0.0.1/organiza_test_example?sslmode=disable'
        with patch.dict(os.environ, {'DATABASE_URL': url, 'PGPASSWORD': 'never-propagate', 'APP_SECRET_KEY': 'never-propagate'}, clear=True):
            with libpq_environment() as environment:
                path = Path(environment['PGPASSFILE'])
                self.assertTrue(path.is_relative_to(ROOT / 'test-results'))
                self.assertTrue(path.is_file())
                self.assertIn('fictional\\:pass\\\\word', path.read_text())
                self.assertNotIn('DATABASE_URL', environment)
                self.assertNotIn('PGPASSWORD', environment)
                self.assertNotIn('APP_SECRET_KEY', environment)
            self.assertFalse(path.exists())

    def test_sqlite_inspection_is_read_only(self):
        with private_temporary('sqlite-read-only-') as temporary:
            path = temporary / 'fictitious.sqlite3'
            with closing(sqlite3.connect(path)) as connection:
                connection.executescript('CREATE TABLE auth_user(id INTEGER PRIMARY KEY,password TEXT); CREATE TABLE finance_workspace(id TEXT PRIMARY KEY); CREATE TABLE finance_financialstate(workspace_id TEXT,document TEXT);')
                connection.execute('INSERT INTO auth_user VALUES(1,?)', ['fictitious-hash'])
                connection.commit()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(len(sqlite_source(path)['auth_user']), 1)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_unapproved_source_never_reaches_importer(self):
        arguments = ['migrate', '--source', str(ROOT / 'backups' / 'unapproved.sqlite3'), '--source-frozen']
        with patch('sys.argv', arguments), patch('tools.migrate_sqlite_postgres.migrate') as importer, redirect_stderr(StringIO()):
            self.assertEqual(migration_main(), 1)
            importer.assert_not_called()

    def test_unfrozen_source_never_reaches_importer(self):
        with patch('sys.argv', ['migrate', '--source', str(ROOT / 'test-results' / 'fictitious.sqlite3')]), patch('tools.migrate_sqlite_postgres.migrate') as importer, redirect_stderr(StringIO()):
            self.assertEqual(migration_main(), 1)
            importer.assert_not_called()

    def test_backup_existing_output_is_never_overwritten(self):
        with private_temporary('backup-existing-') as temporary:
            output = temporary / 'existing.age'
            output.write_bytes(b'preserve encrypted backup')
            with self.assertRaises(RuntimeError):
                backup(output)
            self.assertEqual(output.read_bytes(), b'preserve encrypted backup')

    def test_restore_requires_explicit_empty_target_confirmation_before_connection(self):
        with private_temporary('restore-approval-') as temporary:
            encrypted = temporary / 'fictitious.age'
            encrypted.write_bytes(b'fictitious')
            with patch('tools.postgres_backup.empty_database') as check:
                with self.assertRaises(RuntimeError):
                    restore(encrypted)
                check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
