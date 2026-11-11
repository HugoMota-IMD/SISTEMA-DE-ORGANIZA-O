"""Local management helpers; never log connection strings or passwords."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent.parent


@contextmanager
def private_temporary(prefix):
    """Cleanup is confined to a newly created directory in this project."""
    parent = (ROOT / 'test-results' / '.postgres-management').resolve()
    parent.mkdir(parents=True, exist_ok=True)
    parent.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix=prefix, dir=parent) as temporary:
        directory = Path(temporary).resolve()
        if not directory.is_relative_to(parent):
            raise RuntimeError('Diretório temporário fora do destino permitido.')
        directory.chmod(0o700)
        yield directory


def load_env_file(value):
    if not value:
        return
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT):
        raise RuntimeError('O arquivo de ambiente deve estar nesta raiz exclusiva.')
    values = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, (str, int, bool)) for k, v in values.items()):
        raise RuntimeError('Arquivo de ambiente JSON inválido.')
    os.environ.update({key: str(value) for key, value in values.items()})


def direct_url():
    value = os.getenv('DATABASE_URL_UNPOOLED') or os.getenv('DATABASE_URL')
    if not value:
        raise RuntimeError('Defina DATABASE_URL_UNPOOLED no ambiente seguro; não informe segredos no argumento do comando.')
    parsed = urlsplit(value)
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname or not parsed.path.strip('/'):
        raise RuntimeError('A conexão de gestão deve ser PostgreSQL com banco explícito.')
    if '-pooler' in parsed.hostname:
        raise RuntimeError('Migração e backup exigem conexão direta, sem -pooler.')
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.keys() - {'sslmode', 'sslrootcert', 'channel_binding', 'connect_timeout', 'application_name'} or any(len(values) != 1 for values in query.values()):
        raise RuntimeError('A URL direta contém opções de conexão inesperadas ou repetidas. Confira o destino no ambiente seguro.')
    for part in (parsed.hostname, unquote(parsed.username or ''), unquote(parsed.password or ''), unquote(parsed.path[1:])):
        if '\n' in part or '\r' in part:
            raise RuntimeError('A configuração da conexão contém caracteres inválidos.')
    if parsed.hostname in ('127.0.0.1', 'localhost', '::1'):
        return value
    if not os.getenv('DATABASE_URL_UNPOOLED'):
        raise RuntimeError('Defina DATABASE_URL_UNPOOLED explícita para manutenção remota.')
    if query.get('sslmode', ['verify-full'])[0] not in {'require', 'verify-ca', 'verify-full'}:
        raise RuntimeError('A conexão PostgreSQL remota exige TLS com verificação do servidor.')
    import certifi
    query['sslmode'] = ['verify-full']
    query['sslrootcert'] = [os.getenv('APP_DATABASE_SSLROOTCERT') or query.get('sslrootcert', [certifi.where()])[0]]
    return parsed._replace(query=urlencode(query, doseq=True)).geturl()


def require_local_test_database():
    parsed = urlsplit(direct_url())
    if (parsed.hostname not in ('127.0.0.1', 'localhost', '::1')
            or not unquote(parsed.path[1:]).startswith('organiza_test_')):
        raise RuntimeError('Um ensaio exige destino PostgreSQL local com nome organiza_test_.')


def binary(name):
    explicit = os.getenv(name.upper().replace('-', '_') + '_PATH')
    if explicit and Path(explicit).is_file():
        return str(Path(explicit).resolve())
    group = 'PG_BIN_DIR' if name.startswith('pg_') else 'AGE_BIN_DIR'
    directory = os.getenv(group)
    if directory:
        candidate = Path(directory) / (name + ('.exe' if os.name == 'nt' else ''))
        if candidate.is_file():
            return str(candidate.resolve())
    value = shutil.which(name)
    if value:
        return value
    raise RuntimeError(f'Executável {name} não encontrado; configure {group} ou PATH.')


@contextmanager
def libpq_environment(url=None):
    """Pass credentials through a temporary private passfile, never argv."""
    parsed = urlsplit(url or direct_url())
    query = parse_qs(parsed.query)
    fields = {'PGHOST': parsed.hostname, 'PGPORT': str(parsed.port or 5432),
              'PGUSER': unquote(parsed.username or ''), 'PGDATABASE': unquote(parsed.path[1:])}
    with private_temporary('organiza-pg-pass-') as directory:
        passfile = directory / 'pgpass'
        escape = lambda value: str(value).replace('\\', '\\\\').replace(':', '\\:')
        password = unquote(parsed.password or '')
        passfile.write_text(':'.join(escape(fields[key]) for key in ('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER')) + ':' + escape(password) + '\n', encoding='utf-8')
        passfile.chmod(0o600)
        env = dict(os.environ)
        for key in ('PGPASSWORD', 'DATABASE_URL', 'DATABASE_URL_UNPOOLED', 'APP_SECRET_KEY'):
            env.pop(key, None)
        env.update(fields, PGPASSFILE=str(passfile), PGCONNECT_TIMEOUT='10')
        env['PGSSLMODE'] = query.get('sslmode', ['disable' if parsed.hostname in ('127.0.0.1', 'localhost', '::1') else 'require'])[0]
        for key, option in [('sslrootcert', 'PGSSLROOTCERT'), ('channel_binding', 'PGCHANNELBINDING')]:
            if key in query:
                env[option] = query[key][0]
        yield env


def prepare_django():
    import sys
    sys.path.insert(0, str(ROOT))
    os.environ['DATABASE_URL'] = direct_url()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.db import connection
    if connection.vendor != 'postgresql':
        raise RuntimeError('Operação recusada: o destino não é PostgreSQL.')
    return connection


def management_error(error):
    # Database/CLI exception details can include a failing financial row or DSN.
    return str(error) if isinstance(error, RuntimeError) else 'Operação de gestão falhou; dados sensíveis omitidos. Confira o ambiente e os registros locais de verificação.'
