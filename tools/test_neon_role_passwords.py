"""Offline regressions for hidden password input, target guards and error redaction."""
import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from tools import set_neon_role_passwords as setup


ADMIN_PASSWORD = 'FakeAdminCredentialForTestsOnly_71'
APP_PASSWORD = "FakeAppCredentialForTestsOnly_'92"
MIGRATOR_PASSWORD = 'FakeMigratorCredentialForTestsOnly_36'


def target_connection():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (setup.DATABASE, setup.ADMIN, setup.ADMIN)
    cursor.fetchall.return_value = [
        (role, True, False, False, True, False, False, True, role == 'organiza_migrator')
        for role in setup.ROLES
    ]
    return connection, cursor


class PasswordSetupTests(unittest.TestCase):
    def test_no_echo_fallback_for_redirected_input(self):
        with patch.object(setup.sys.stdin, 'isatty', return_value=False), \
                patch.object(setup.getpass, 'getpass') as prompt:
            with self.assertRaises(setup.SetupError):
                setup.read_secret('Fake prompt: ')
            prompt.assert_not_called()

    def test_password_confirmation_and_distinct_roles(self):
        with patch.object(setup, 'read_secret', side_effect=[
                ADMIN_PASSWORD, APP_PASSWORD, APP_PASSWORD, MIGRATOR_PASSWORD, MIGRATOR_PASSWORD]):
            admin, passwords = setup.collect_passwords()
        self.assertEqual(admin, ADMIN_PASSWORD)
        self.assertEqual(passwords, dict(zip(setup.ROLES, (APP_PASSWORD, MIGRATOR_PASSWORD))))

    def test_invalid_password_input_never_connects(self):
        cases = [
            [ADMIN_PASSWORD, APP_PASSWORD, 'different'],
            [ADMIN_PASSWORD, 'short', 'short'],
            [ADMIN_PASSWORD, ADMIN_PASSWORD, ADMIN_PASSWORD],
            [ADMIN_PASSWORD, APP_PASSWORD, APP_PASSWORD, APP_PASSWORD, APP_PASSWORD],
            [ADMIN_PASSWORD, 'SCRAM-SHA-256$' + 'x' * 30, 'SCRAM-SHA-256$' + 'x' * 30],
            [ADMIN_PASSWORD, 'x' * 24 + '\n', 'x' * 24 + '\n'],
        ]
        for entries in cases:
            with self.subTest(case=cases.index(entries)), \
                    patch.object(setup, 'read_secret', side_effect=entries), \
                    patch.object(setup, 'connect') as connect, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(setup.main(), 1)
                connect.assert_not_called()
                for secret in entries:
                    self.assertNotIn(secret, output.getvalue())

    def test_tls_and_no_environment_connection_defaults(self):
        with patch.object(setup.psycopg, 'connect') as connect:
            setup.connect(setup.ADMIN, ADMIN_PASSWORD)
        kwargs = connect.call_args.kwargs
        self.assertEqual(kwargs['host'], setup.HOST)
        self.assertEqual(kwargs['dbname'], 'neondb')
        self.assertEqual(kwargs['sslmode'], 'verify-full')
        self.assertEqual(kwargs['channel_binding'], 'require')
        self.assertEqual(kwargs['sslrootcert'], setup.certifi.where())

    def test_target_and_role_privileges_are_checked(self):
        connection, cursor = target_connection()
        setup.check_target(connection)
        cursor.fetchone.return_value = ('another_database', setup.ADMIN, setup.ADMIN)
        with self.assertRaises(setup.SetupError):
            setup.check_target(connection)
        cursor.fetchone.return_value = (setup.DATABASE, setup.ADMIN, setup.ADMIN)
        cursor.fetchall.return_value = []
        with self.assertRaises(setup.SetupError):
            setup.check_target(connection)

    def test_elevated_role_fails_before_password_update(self):
        connection, cursor = target_connection()
        rows = cursor.fetchall.return_value
        rows[0] = (setup.ROLES[0], True, True, False, True, False, False, True, False)
        with patch.object(setup, 'connect') as connect:
            connect.return_value.__enter__.return_value = connection
            with self.assertRaises(setup.SetupError):
                setup.configure(ADMIN_PASSWORD, dict(zip(setup.ROLES, (APP_PASSWORD, MIGRATOR_PASSWORD))))
        self.assertEqual(len(cursor.execute.call_args_list), 2)

    def test_password_is_quoted_not_prehashed_and_only_allowed_roles(self):
        rendered = setup.password_statement('organiza_app', "test'password").as_string()
        self.assertEqual(rendered, 'ALTER ROLE "organiza_app" PASSWORD \'test\'\'password\'')
        with self.assertRaises(setup.SetupError):
            setup.password_statement('neondb_owner', APP_PASSWORD)

    def test_server_error_does_not_disclose_secret_or_traceback(self):
        with patch.object(setup, 'collect_passwords', return_value=(ADMIN_PASSWORD, {})), \
                patch.object(setup, 'configure', side_effect=RuntimeError(APP_PASSWORD)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(setup.main(), 1)
        self.assertNotIn(APP_PASSWORD, output.getvalue())
        self.assertNotIn('Traceback', output.getvalue())

    def test_verification_failure_does_not_claim_login_success(self):
        connection, cursor = target_connection()
        with patch.object(setup, 'connect') as connect, \
                patch.object(setup, 'verify_login', side_effect=RuntimeError(APP_PASSWORD)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            connect.return_value.__enter__.return_value = connection
            with self.assertRaises(RuntimeError):
                setup.configure(ADMIN_PASSWORD, dict(zip(setup.ROLES, (APP_PASSWORD, MIGRATOR_PASSWORD))))
        self.assertIn('organiza_app: servidor confirmou', output.getvalue())
        self.assertNotIn('login direto com a nova senha confirmado', output.getvalue())
        self.assertEqual(len(cursor.execute.call_args_list), 3)

    def test_each_role_is_verified_without_printing_passwords(self):
        connection, cursor = target_connection()
        passwords = dict(zip(setup.ROLES, (APP_PASSWORD, MIGRATOR_PASSWORD)))
        with patch.object(setup, 'connect') as connect, \
                patch.object(setup, 'verify_login') as verify, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            connect.return_value.__enter__.return_value = connection
            setup.configure(ADMIN_PASSWORD, passwords)
        self.assertEqual(len(cursor.execute.call_args_list), 4)
        for role, password in passwords.items():
            verify.assert_any_call(role, password)
            self.assertIn(f'{role}: login direto com a nova senha confirmado.', output.getvalue())
            self.assertNotIn(password, output.getvalue())

    def test_admin_diagnosis_only_prompts_once_and_executes_selects(self):
        connection, cursor = target_connection()
        with patch.object(setup, 'read_secret', return_value=ADMIN_PASSWORD) as prompt, \
                patch.object(setup, 'connect') as connect, \
                patch.object(setup, 'configure') as configure, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            connect.return_value.__enter__.return_value = connection
            self.assertEqual(setup.main(check_only=True), 0)
        self.assertEqual(prompt.call_count, 1)
        configure.assert_not_called()
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT')
                            for call in cursor.execute.call_args_list))
        self.assertIn('DIAGNOSTICO_OK', output.getvalue())
        self.assertNotIn(ADMIN_PASSWORD, output.getvalue())

    def test_startup_auth_failure_has_actionable_code_without_password(self):
        with patch.object(setup, 'read_secret', return_value=ADMIN_PASSWORD), \
                patch.object(setup, 'connect', side_effect=setup.psycopg.OperationalError(
                    'password authentication failed ' + ADMIN_PASSWORD)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(setup.main(check_only=True), 1)
        self.assertIn('AUTENTICACAO_RECUSADA', output.getvalue())
        self.assertIn('Nenhuma alteracao de senha foi enviada', output.getvalue())
        self.assertNotIn(ADMIN_PASSWORD, output.getvalue())

    def test_safe_categories_do_not_echo_exception_details(self):
        cases = [
            ('root certificate file ' + ADMIN_PASSWORD, 'TLS_CERTIFICADO'),
            ('channel binding required ' + ADMIN_PASSWORD, 'TLS_CHANNEL_BINDING'),
            ('could not translate host name ' + ADMIN_PASSWORD, 'DNS'),
            ('timeout expired ' + ADMIN_PASSWORD, 'TEMPO_ESGOTADO'),
            (ADMIN_PASSWORD, 'FALHA_NAO_CLASSIFICADA'),
        ]
        for message, code in cases:
            with self.subTest(category=code):
                diagnostic = setup.safe_error(setup.psycopg.OperationalError(message))
                self.assertIn(code, diagnostic)
                self.assertNotIn(ADMIN_PASSWORD, diagnostic)

    def test_sqlstate_is_exposed_without_server_text(self):
        error = setup.psycopg.errors.InsufficientPrivilege(ADMIN_PASSWORD)
        diagnostic = setup.safe_error(error)
        self.assertIn('PERMISSAO_RECUSADA', diagnostic)
        self.assertIn('SQLSTATE=42501', diagnostic)
        self.assertNotIn(ADMIN_PASSWORD, diagnostic)

    def test_failed_write_is_reported_as_possibly_applied(self):
        connection, cursor = target_connection()
        cursor.execute.side_effect = [None, None, setup.psycopg.OperationalError(APP_PASSWORD)]
        passwords = dict(zip(setup.ROLES, (APP_PASSWORD, MIGRATOR_PASSWORD)))
        with patch.object(setup, 'collect_passwords', return_value=(ADMIN_PASSWORD, passwords)), \
                patch.object(setup, 'connect') as connect, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            connect.return_value.__enter__.return_value = connection
            self.assertEqual(setup.main(), 1)
        self.assertIn('Alteracao enviada para: organiza_app', output.getvalue())
        self.assertIn('pode ter sido aplicada', output.getvalue())
        self.assertNotIn('Nenhuma alteracao de senha foi enviada', output.getvalue())
        self.assertNotIn(APP_PASSWORD, output.getvalue())


if __name__ == '__main__':
    unittest.main()
