"""HTTPS-only private origin, alongside the existing loopback HTTP session.

Private cookies use their own names so another app on the same Tailscale node
cannot accidentally consume an Organiza session. Existing localhost sessions
keep their names. Authentication and CSRF still run in Django's middleware.
"""
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponse, JsonResponse


class PrivateAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        private = bool(settings.PRIVATE_HTTPS_HOST) and (
            urlsplit('//' + request.get_host()).hostname == settings.PRIVATE_HTTPS_HOST
        )
        if private and not request.is_secure():
            return HttpResponse(status=308, headers={
                'Location': settings.PRIVATE_HTTPS_ORIGIN + request.get_full_path(),
            })
        if getattr(settings, 'READ_ONLY_MODE', False) and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            return JsonResponse({'error': 'Este ambiente está somente para consulta durante a migração. Nenhuma alteração foi registrada.',
                                 'read_only': True}, status=503, headers={'Retry-After': '60'})
        cookie_names = {
            settings.SESSION_COOKIE_NAME: 'organiza_sessionid',
            settings.CSRF_COOKIE_NAME: 'organiza_csrftoken',
        }
        if private:
            for internal, external in cookie_names.items():
                # Ignore other apps' generic cookies on this shared hostname.
                if internal != external:
                    request.COOKIES.pop(internal, None)
                    if external in request.COOKIES:
                        request.COOKIES[internal] = request.COOKIES[external]
        response = self.get_response(request)
        if private:
            for internal, external in cookie_names.items():
                if internal in response.cookies:
                    if internal != external:
                        source = response.cookies[internal]
                        response.cookies[external] = source.value
                        for name, value in source.items():
                            response.cookies[external][name] = value
                        del response.cookies[internal]
                    response.cookies[external]['secure'] = True
            response['Strict-Transport-Security'] = 'max-age=31536000'
        return response
