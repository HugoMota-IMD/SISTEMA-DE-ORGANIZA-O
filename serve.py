"""Start the local WSGI app. Internet exposure needs an approved hosting setup."""
import os
from waitress import serve
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
from config.wsgi import application
from django.conf import settings
from tools.runtime_lock import server_guard

if __name__ == '__main__':
    port = int(os.getenv('APP_PORT', '8765'))
    proxy = ({'trusted_proxy': '127.0.0.1', 'trusted_proxy_count': 1,
              'trusted_proxy_headers': {'x-forwarded-proto'}}
             if settings.PRIVATE_HTTPS_ORIGIN else {})
    with server_guard(settings.BASE_DIR, port):
        serve(application, host='127.0.0.1', port=port, threads=4,
              max_request_body_size=262144, clear_untrusted_proxy_headers=True, **proxy)
