"""Interactive password setup for the existing Organiza roles on Neon.

Run only in the operator's terminal. No dotenv, password arguments, secret files,
or Django initialization. Neon requires a password literal, not psql's verifier.
TLS protects transport; provider-side SQL logging is outside this tool's control.
"""
import argparse
import getpass
import re
import sys
import warnings

import certifi
import psycopg
from psycopg import sql


HOST = 'ep-lucky-forest-b6z1zyft.c-2.sa-east-1.aws.neon.tech'
DATABASE = 'neondb'
ADMIN = 'neondb_owner'
ROLES = ('organiza_app', 'organiza_migrator')


class SetupError(Exception):
    """An operator-facing message that never contains a secret or server text."""


def read_secret(prompt):
    if not sys.stdin.isatty():
        raise SetupError('Execute em um terminal interativo, sem redirecionar a entrada.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        return getpass.getpass(prompt)


def collect_passwords():
    admin_password = read_secret('Senha ATUAL de neondb_owner: ')
    if not admin_password:
        raise SetupError('A senha administrativa nao pode ficar vazia.')
    passwords = {}
    for role in ROLES:
        password = read_secret(f'Nova senha de {role}: ')
        confirmation = read_secret(f'Repita a nova senha de {role}: ')
        if password != confirmation:
            raise SetupError(f'As duas entradas para {role} diferem. Nenhuma alteracao enviada.')
        # Printable ASCII avoids console encoding mistakes. It is not an entropy
        # estimate: the operator must use a password manager's random generator.
        if len(password) < 24 or not all(33 <= ord(c) <= 126 for c in password):
            raise SetupError('Use senhas aleatorias com ao menos 24 caracteres ASCII, sem espacos.')
        if password.startswith(('SCRAM-SHA-256$', 'md5')):
            raise SetupError('Informe a senha original gerada no cofre, sem hash pre-calculado.')
        if password == admin_password or password in passwords.values():
            raise SetupError('Use uma senha diferente para cada uma das tres roles.')
        passwords[role] = password
    return admin_password, passwords


def connect(role, password):
    return psycopg.connect(
        host=HOST, port=5432, dbname=DATABASE, user=role, password=password,
        sslmode='verify-full', sslrootcert=certifi.where(), channel_binding='require',
        connect_timeout=20, application_name='organiza-role-password-setup', autocommit=True,
    )


def check_target(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), current_user, session_user')
        if cursor.fetchone() != (DATABASE, ADMIN, ADMIN):
            raise SetupError('Banco ou identidade administrativa diferente do destino esperado.')
        cursor.execute("""
            SELECT r.rolname, r.rolcanlogin,
                   r.rolsuper OR r.rolcreatedb OR r.rolcreaterole
                       OR r.rolreplication OR r.rolbypassrls,
                   EXISTS(SELECT FROM pg_auth_members m WHERE m.member = r.oid),
                   has_database_privilege(r.oid, current_database(), 'CONNECT'),
                   has_database_privilege(r.oid, current_database(), 'CREATE'),
                   has_database_privilege(r.oid, current_database(), 'TEMPORARY'),
                   has_schema_privilege(r.oid, 'public', 'USAGE'),
                   has_schema_privilege(r.oid, 'public', 'CREATE')
            FROM pg_roles r WHERE r.rolname IN ('organiza_app', 'organiza_migrator')
            ORDER BY r.rolname
        """)
        expected = [
            (role, True, False, False, True, False, False, True, role == 'organiza_migrator')
            for role in ROLES
        ]
        if cursor.fetchall() != expected:
            raise SetupError('Roles ausentes ou privilegios diferentes dos conferidos. Nada alterado.')


def password_statement(role, password):
    if role not in ROLES:
        raise SetupError('Role fora do escopo autorizado.')
    # Utility commands do not accept PostgreSQL $1 parameters. Identifier/Literal
    # perform proper SQL quoting; never use string interpolation or print this SQL.
    return sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role), sql.Literal(password))


def verify_login(role, password):
    with connect(role, password) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user, session_user')
            if cursor.fetchone() != (DATABASE, role, role):
                raise SetupError(f'Identidade inesperada na verificacao de {role}.')


def stage(progress, description):
    progress['stage'] = description
    print(description, flush=True)


def safe_error(error):
    """Classify locally; never return server text, connection strings or SQL."""
    code = getattr(error, 'sqlstate', None)
    message = str(error).lower()
    if code == '28P01' or 'password authentication failed' in message:
        result = 'AUTENTICACAO_RECUSADA: a senha da role desta etapa foi recusada.'
    elif code == '42501':
        result = 'PERMISSAO_RECUSADA: o servidor recusou a permissao para esta etapa.'
    elif code == '3D000':
        result = 'BANCO_NAO_ENCONTRADO: confira o banco no destino informado.'
    elif 'channel binding' in message:
        result = 'TLS_CHANNEL_BINDING: a verificacao adicional da conexao falhou.'
    elif any(text in message for text in (
            'certificate verify failed', 'certificate verification failed',
            'root certificate', 'server certificate', 'ssl error')):
        result = 'TLS_CERTIFICADO: nao foi possivel validar a conexao segura.'
    elif any(text in message for text in (
            'could not translate host name', 'failed to resolve host',
            'getaddrinfo failed', 'name or service not known')):
        result = 'DNS: nao foi possivel resolver o endereco do servidor.'
    elif isinstance(error, TimeoutError) or any(text in message for text in (
            'timeout expired', 'connection timeout', 'timed out')):
        result = 'TEMPO_ESGOTADO: o servidor nao respondeu no prazo.'
    elif isinstance(error, UnicodeError):
        result = 'CODIFICACAO: houve falha de conversao de caracteres.'
    elif isinstance(error, FileNotFoundError):
        result = 'ARQUIVO_LOCAL: um arquivo necessario nao foi encontrado.'
    else:
        result = 'FALHA_NAO_CLASSIFICADA: a etapa falhou; detalhes sensiveis foram omitidos.'
    if isinstance(code, str) and re.fullmatch(r'[0-9A-Z]{5}', code):
        result += f' SQLSTATE={code}.'
    return result


def report_progress(progress):
    print('Etapa: ' + progress['stage'])
    if progress['sent']:
        print('Alteracao enviada para: ' + ', '.join(progress['sent']) + '.')
        print('Uma alteracao enviada pode ter sido aplicada; nao foi desfeita.')
    else:
        print('Nenhuma alteracao de senha foi enviada ao Neon.')


def check_admin(admin_password, progress):
    stage(progress, 'Conectando como neondb_owner por TLS verificado...')
    with connect(ADMIN, admin_password) as connection:
        stage(progress, 'Login administrativo aceito. Conferindo banco e privilegios...')
        check_target(connection)
    print('DIAGNOSTICO_OK: login administrativo, banco e privilegios conferidos.')
    print('Somente consultas de verificacao foram executadas. Nenhuma senha foi alterada.')


def configure(admin_password, passwords, progress=None):
    progress = progress if progress is not None else {'stage': '', 'sent': []}
    stage(progress, 'Conectando como neondb_owner por TLS verificado...')
    with connect(ADMIN, admin_password) as connection:
        stage(progress, 'Login administrativo aceito. Conferindo banco e privilegios...')
        check_target(connection)
        # Neon forwards role management to its control plane. Do not promise
        # rollback of password updates across roles: report each outcome separately.
        for role in ROLES:
            stage(progress, f'Enviando alteracao de senha para {role}...')
            with connection.cursor() as cursor:
                statement = password_statement(role, passwords[role])
                progress['sent'].append(role)
                cursor.execute(statement)
            print(f'{role}: servidor confirmou a alteracao da senha.')
            stage(progress, f'Verificando novo login de {role}...')
            verify_login(role, passwords[role])
            print(f'{role}: login direto com a nova senha confirmado.')


def main(check_only=False):
    progress = {'stage': 'entrada de senhas', 'sent': []}
    try:
        print('Organiza - ' + ('diagnostico sem alteracoes.' if check_only
                              else 'configurar somente as senhas de duas roles existentes.'))
        print(f'Destino informado por Hugo: production / {DATABASE} / {HOST}')
        if not check_only:
            print('Use o gerenciador de senhas para gerar e guardar duas senhas distintas.')
        print('A entrada fica oculta. Nao cole senhas fora dos prompts abaixo.')
        if check_only:
            admin_password = read_secret('Senha ATUAL de neondb_owner: ')
            if not admin_password:
                raise SetupError('A senha administrativa nao pode ficar vazia.')
            check_admin(admin_password, progress)
            return 0
        admin_password, passwords = collect_passwords()
        configure(admin_password, passwords, progress=progress)
    except SetupError as error:
        print(str(error))
        report_progress(progress)
        return 1
    except (KeyboardInterrupt, EOFError, getpass.GetPassWarning):
        print('\nInterrompido. Confira a etapa e os resultados abaixo antes de repetir.')
        report_progress(progress)
        return 1
    except Exception as error:
        # Server/driver exceptions can contain SQL, connection parameters or
        # passwords. Do not print str(error), diagnostics or a traceback.
        print('Operacao nao concluida. ' + safe_error(error))
        report_progress(progress)
        print('Informe somente este diagnostico e os nomes das roles com sucesso ou falha.')
        return 1
    print('Concluido: as duas senhas foram alteradas e os dois logins diretos foram verificados.')
    print('Nenhuma tabela, permissao, migracao ou dado financeiro foi alterado por este utilitario.')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Configurar senhas das roles existentes do Organiza.')
    parser.add_argument('--check-admin', action='store_true', help='Verificar apenas o acesso e privilegios; nao alterar senhas.')
    args = parser.parse_args()
    sys.exit(main(check_only=args.check_admin))
