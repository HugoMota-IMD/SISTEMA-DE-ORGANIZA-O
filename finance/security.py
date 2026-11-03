from contextlib import contextmanager
from contextvars import ContextVar

from django.db import InterfaceError, OperationalError, connections, transaction
from django.http import JsonResponse

current_actor = ContextVar('finance_actor', default=0)

def register_connection(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.connection.create_function('finance_actor', 0, lambda: current_actor.get())

@contextmanager
def _postgres_context(values, using):
    """Transaction-local state also works through PgBouncer transaction pooling.

    Never set actor/import state at session scope. A nested context restores the
    caller's values; an error rolls back its savepoint and all local settings.
    """
    connection = connections[using]
    with transaction.atomic(using=using):
        with connection.cursor() as cursor:
            previous = {}
            for key, value in values.items():
                cursor.execute('SELECT current_setting(%s, true)', [key])
                previous[key] = cursor.fetchone()[0] or ''
                cursor.execute('SELECT set_config(%s, %s, true)', [key, str(value)])
        try:
            yield
        except BaseException:
            # The atomic block rolls local settings back along with the writes.
            raise
        else:
            # Do not mask a database exception caught inside the caller's block.
            if not connection.needs_rollback and not connection.closed_in_transaction:
                with connection.cursor() as cursor:
                    for key, value in previous.items():
                        cursor.execute('SELECT set_config(%s, %s, true)', [key, value])


@contextmanager
def actor_context(user_id, using='default'):
    actor = int(user_id or 0)
    token = current_actor.set(actor)
    try:
        if connections[using].vendor == 'postgresql':
            with _postgres_context({'organiza.actor_id': actor, 'organiza.import_mode': 'off'}, using):
                yield
        else:
            yield
    finally:
        current_actor.reset(token)


@contextmanager
def import_context(using='default'):
    """Trusted management-only insertion of a reconciled historical import.

    This is deliberately not an HTTP permission. Import tools must additionally
    require an empty, approved destination. Constraints and foreign keys remain
    active. The database operator remains privileged, as with the SQLite file;
    these application guards are not independent row-level security.
    """
    if connections[using].vendor != 'postgresql':
        raise RuntimeError('A importação histórica exige destino PostgreSQL isolado.')
    with _postgres_context({'organiza.actor_id': '0', 'organiza.import_mode': 'on'}, using):
        yield

class ActorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Keep health independent of database availability and session loading.
        try:
            if request.path == '/api/health' and request.method == 'GET':
                response = self.get_response(request)
            else:
                user_id = request.user.pk if request.user.is_authenticated else 0
                with actor_context(user_id):
                    response = self.get_response(request)
        except (OperationalError, InterfaceError):
            # This also covers authentication/context setup and an uncertain
            # COMMIT response outside the endpoint's own error decorator. Do
            # not expose driver messages or claim that no write took place.
            response = JsonResponse({
                'error': 'Não foi possível confirmar o resultado. Confira os dados e saldos antes de repetir, mantendo a mesma chave da operação.',
                'retry_same_request_id': True,
            }, status=503, headers={'Retry-After': '60'})
        response['Cache-Control'] = 'no-store'
        response['Referrer-Policy'] = 'same-origin'
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response
