import os
import secrets
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent.parent
# An optional local .env is read without adding a runtime dependency.
env_file = BASE_DIR / '.env'
_platform_hosted = os.getenv('RENDER', '').lower() == 'true'
_explicit_hosted = os.getenv('APP_ENVIRONMENT', '').lower() == 'production'
if env_file.exists() and not (_platform_hosted or _explicit_hosted):
    for line in env_file.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

DATA_DIR = BASE_DIR / 'data'
ENVIRONMENT = os.getenv('APP_ENVIRONMENT', 'production' if _platform_hosted else 'local').lower()
if ENVIRONMENT not in {'local', 'test', 'production'}:
    raise RuntimeError('APP_ENVIRONMENT deve ser local, test ou production.')
HOSTED = _platform_hosted or ENVIRONMENT == 'production'
if not HOSTED:
    DATA_DIR.mkdir(exist_ok=True)
DEBUG = os.getenv('APP_DEBUG', 'false').lower() == 'true'
LOCAL_MODE = os.getenv('APP_LOCAL_MODE', 'false' if HOSTED else 'true').lower() == 'true'
if HOSTED and (LOCAL_MODE or DEBUG):
    raise RuntimeError('Produção exige APP_LOCAL_MODE=false e APP_DEBUG=false.')
REGISTRATION_MODE = os.getenv('APP_REGISTRATION_MODE', 'approval' if HOSTED else 'open').lower()
if REGISTRATION_MODE not in {'open', 'approval', 'closed'} or (HOSTED and REGISTRATION_MODE == 'open'):
    raise RuntimeError('Escolha APP_REGISTRATION_MODE approval ou closed em produção; open somente local.')
READ_ONLY_MODE = os.getenv('APP_READ_ONLY', 'false').lower() == 'true'
from config.database import database_configuration
DATABASES = database_configuration(BASE_DIR, HOSTED)
secret_path = DATA_DIR / '.local-secret'
if not os.getenv('APP_SECRET_KEY') and LOCAL_MODE:
    if not secret_path.exists():
        try:
            with secret_path.open('x', encoding='utf-8') as secret_file:
                secret_file.write(secrets.token_urlsafe(64))
        except FileExistsError:
            pass
    SECRET_KEY = secret_path.read_text(encoding='utf-8').strip()
else:
    SECRET_KEY = os.getenv('APP_SECRET_KEY', '')
if not SECRET_KEY:
    raise RuntimeError('Defina APP_SECRET_KEY fora do modo local.')
if HOSTED and (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith('django-insecure-')):
    raise RuntimeError('APP_SECRET_KEY de produção deve ser aleatória, com pelo menos 50 caracteres; use o gerador de segredos do provedor.')


def exact_host(value):
    try:
        parsed = urlsplit('//' + value)
        port = parsed.port
    except ValueError:
        raise RuntimeError('Informe hosts específicos sem esquema, caminho ou porta.') from None
    if (not parsed.hostname or port is not None or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or '*' in value):
        raise RuntimeError('Informe hosts específicos sem esquema, caminho ou porta.')
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if (len(host) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                   for label in host.split('.'))):
            raise RuntimeError('Host DNS inválido; não usar wildcard ou sufixos amplos.') from None
    return '[' + host + ']' if ':' in host else host


ALLOWED_HOSTS = [h.strip() for h in os.getenv('APP_ALLOWED_HOSTS', '' if HOSTED else 'localhost,127.0.0.1,[::1]').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [s.strip() for s in os.getenv('APP_CSRF_TRUSTED_ORIGINS', '').split(',') if s.strip()]
_render_host = os.getenv('RENDER_EXTERNAL_HOSTNAME', '').strip().lower()
if HOSTED and _render_host:
    if not _render_host.endswith('.onrender.com') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-.' for c in _render_host):
        raise RuntimeError('RENDER_EXTERNAL_HOSTNAME inválido.')
    if _render_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_render_host)
    if 'https://' + _render_host not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append('https://' + _render_host)
if HOSTED:
    if not ALLOWED_HOSTS:
        raise RuntimeError('Configure APP_ALLOWED_HOSTS específicos em produção, sem wildcard.')
    ALLOWED_HOSTS = [exact_host(host) for host in ALLOWED_HOSTS]
    if not CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = ['https://' + host for host in ALLOWED_HOSTS]
    for origin in CSRF_TRUSTED_ORIGINS:
        try:
            parsed = urlsplit(origin)
            origin_port = parsed.port
        except ValueError:
            raise RuntimeError('Origem CSRF inválida; conferir host e porta HTTPS.') from None
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or '*' in origin:
            raise RuntimeError('Configure origens CSRF HTTPS exatas, sem caminhos ou wildcard.')
        if origin_port is not None and not 1 <= origin_port <= 65535:
            raise RuntimeError('Porta da origem CSRF inválida.')
        exact_host('[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname)
PRIVATE_HTTPS_ORIGIN = os.getenv('APP_PRIVATE_HTTPS_ORIGIN', '').strip().rstrip('/')
PRIVATE_HTTPS_HOST = ''
if HOSTED and PRIVATE_HTTPS_ORIGIN:
    raise RuntimeError('APP_PRIVATE_HTTPS_ORIGIN pertence ao ambiente Tailscale local; não configurar no serviço hospedado.')
if PRIVATE_HTTPS_ORIGIN:
    private_url = urlsplit(PRIVATE_HTTPS_ORIGIN)
    try:
        private_port = private_url.port
    except ValueError as exc:
        raise RuntimeError('Porta HTTPS privada inválida.') from exc
    if private_port is not None and not 1 <= private_port <= 65535:
        raise RuntimeError('Porta HTTPS privada inválida.')
    if (private_url.scheme != 'https' or not private_url.hostname
            or not private_url.hostname.endswith('.ts.net')
            or private_url.username or private_url.password or private_url.path
            or private_url.query or private_url.fragment
            or any(not part or len(part) > 63 or not part[0].isalnum()
                   or not part[-1].isalnum() or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in part)
                   for part in private_url.hostname.split('.'))):
        raise RuntimeError('APP_PRIVATE_HTTPS_ORIGIN deve ser uma origem HTTPS exata do Tailscale, sem caminho ou credenciais.')
    PRIVATE_HTTPS_HOST = private_url.hostname
    PRIVATE_HTTPS_ORIGIN = 'https://' + PRIVATE_HTTPS_HOST + (f':{private_port}' if private_port and private_port != 443 else '')
    if PRIVATE_HTTPS_HOST not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(PRIVATE_HTTPS_HOST)
    if PRIVATE_HTTPS_ORIGIN not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(PRIVATE_HTTPS_ORIGIN)
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.staticfiles', 'finance.apps.FinanceConfig']
MIDDLEWARE = ['finance.access.PrivateAccessMiddleware', 'django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'finance.security.ActorMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
MIDDLEWARE.insert(2, 'whitenoise.middleware.WhiteNoiseMiddleware')
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request']}}]
WSGI_APPLICATION = 'config.wsgi.application'
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Manaus'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_SECURE = not LOCAL_MODE
CSRF_COOKIE_SECURE = not LOCAL_MODE
if HOSTED:
    SESSION_COOKIE_NAME = 'organiza_sessionid'
    CSRF_COOKIE_NAME = 'organiza_csrftoken'
# Waitress, bound to loopback, validates the single trusted proxy and translates
# X-Forwarded-Proto to wsgi.url_scheme. Django never trusts the raw header again.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if _platform_hosted else None
USE_X_FORWARDED_HOST = False
SECURE_SSL_REDIRECT = not LOCAL_MODE
SECURE_HSTS_SECONDS = 0 if LOCAL_MODE else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not LOCAL_MODE
SECURE_HSTS_PRELOAD = not LOCAL_MODE
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
X_FRAME_OPTIONS = 'DENY'
CSRF_FAILURE_VIEW = 'finance.views.csrf_failure'
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'
                           if HOSTED else 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
WHITENOISE_USE_FINDERS = not HOSTED
APP_VERSION = '0.2.0-prep'
if HOSTED:
    LOGGING = {
        'version': 1, 'disable_existing_loggers': False,
        'filters': {'safe_error': {'()': 'config.log_filters.SafeErrorFilter'}},
        'formatters': {'minimal': {'format': '%(levelname)s %(name)s: %(message)s'}},
        'handlers': {'safe_console': {'class': 'logging.StreamHandler', 'filters': ['safe_error'], 'formatter': 'minimal'}},
        'loggers': {name: {'handlers': ['safe_console'], 'level': 'WARNING', 'propagate': False}
                    for name in ['django.request', 'django.security', 'django.db.backends', 'gunicorn.error']},
    }
