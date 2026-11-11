"""Explicit PostgreSQL hosting; local SQLite never becomes a hosted fallback."""
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def database_configuration(base_dir, hosted):
    raw = os.getenv('DATABASE_URL', '').strip()
    direct = os.getenv('APP_USE_DIRECT_DATABASE', 'false').lower() == 'true'
    if direct:
        unpooled = os.getenv('DATABASE_URL_UNPOOLED', '').strip()
        if hosted and not unpooled:
            raise RuntimeError('Defina DATABASE_URL_UNPOOLED direta para migrações e manutenção.')
        raw = unpooled or raw
    if raw:
        if os.getenv('APP_DB_PATH', '').strip():
            raise RuntimeError('APP_DB_PATH identifica SQLite. Separe esse ambiente das conexões PostgreSQL antes de iniciar.')
        try:
            parsed = urlsplit(raw)
            if parsed.scheme not in {'postgres', 'postgresql'} or not parsed.hostname or not parsed.path.strip('/'):
                raise ValueError('invalid PostgreSQL URL')
            if direct and '-pooler' in parsed.hostname:
                raise RuntimeError('Use DATABASE_URL_UNPOOLED direta para migrações e manutenção.')
            if hosted:
                query = parse_qs(parsed.query, keep_blank_values=True)
                if (query.get('sslmode', ['require'])[0] not in {'require', 'verify-ca', 'verify-full'}
                        or any(len(values) != 1 for values in query.values())
                        or query.keys() - {'sslmode', 'sslrootcert', 'channel_binding', 'connect_timeout', 'application_name'}):
                    raise ValueError('Unexpected hosted connection options')
            import dj_database_url
            config = dj_database_url.parse(raw, conn_max_age=0, conn_health_checks=True)
        except (ValueError, TypeError, KeyError):
            raise RuntimeError('DATABASE_URL deve ser PostgreSQL válida; em produção, TLS é obrigatório. Confira o segredo no ambiente, sem imprimi-lo.') from None
        options = config.setdefault('OPTIONS', {})
        options.update(connect_timeout=15, prepare_threshold=None)
        if hosted:
            import certifi
            options['sslmode'] = 'verify-full'
            options['sslrootcert'] = os.getenv('APP_DATABASE_SSLROOTCERT', '').strip() or options.get('sslrootcert') or certifi.where()
        config['DISABLE_SERVER_SIDE_CURSORS'] = True
        if os.getenv('APP_TEST_DATABASE_NAME'):
            name = os.environ['APP_TEST_DATABASE_NAME']
            if not name.startswith('organiza_test_') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in name):
                raise RuntimeError('APP_TEST_DATABASE_NAME deve identificar um banco organiza_test_ isolado.')
            config['TEST'] = {'NAME': name}
        return {'default': config}
    if hosted:
        raise RuntimeError('Defina DATABASE_URL PostgreSQL no ambiente hospedado. SQLite temporário não é permitido em produção.')
    path = Path(os.getenv('APP_DB_PATH', str(base_dir / 'data' / 'finance.sqlite3')))
    if not path.is_absolute():
        path = base_dir / path
    path = path.resolve()
    if not path.is_relative_to(base_dir.resolve()):
        raise RuntimeError('APP_DB_PATH deve ficar dentro da raiz exclusiva deste projeto.')
    return {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(path),
                        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
