import copy
import hashlib
import json
import mimetypes
import uuid
from datetime import timedelta
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ObjectDoesNotExist, ValidationError, RequestDataTooBig
from django.db import IntegrityError, OperationalError, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone

from . import domain
from .models import AuditEvent, FinancialState, LoginAttempt, Membership, Operation, UserAccessEvent, Workspace

User = get_user_model()

def api(methods=('GET',), public=False):
    def decorate(fn):
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                response = JsonResponse({'error': 'Método não permitido.'}, status=405)
                response['Allow'] = ', '.join(methods)
                return response
            if not public and not request.user.is_authenticated:
                return JsonResponse({'error': 'Entre na sua conta para continuar.'}, status=401)
            try:
                return fn(request, *args, **kwargs)
            except (Http404, ObjectDoesNotExist):
                return JsonResponse({'error': 'Espaço ou registro não encontrado.'}, status=404)
            except PermissionError as exc:
                return JsonResponse({'error': str(exc)}, status=403)
            except (ValueError, TypeError, KeyError, ValidationError, RequestDataTooBig) as exc:
                if isinstance(exc, ValidationError):
                    message = ' '.join(exc.messages)
                elif isinstance(exc, (TypeError, KeyError)):
                    message = 'Confira o preenchimento: há um campo ausente ou em formato inválido.'
                else:
                    message = str(exc) or 'Confira os campos informados.'
                fields = getattr(exc, 'fields', None) or getattr(exc, 'field_errors', None)
                if not isinstance(fields, dict):
                    fields = {}
                    for needle, field in [('Parcelas já pagas','paid_installments'),('Número de parcelas','installments'),('Primeiro vencimento','due_date'),('primeira fatura','first_invoice_month'),('Data do pagamento','paid_on'),('data futura','paid_on'),('Cartão','card_id'),('Conta','account_id'),('Categoria','category_id'),('Descrição','description'),('centavo','amount_cents'),('Valor','amount_cents'),('saldo pendente','amount_cents')]:
                        if needle.casefold() in message.casefold():
                            fields[field] = message
                            break
                return JsonResponse({'error': message, 'field_errors': fields}, status=400)
            except IntegrityError:
                return JsonResponse({'error': 'Operação recusada pelas regras de integridade. Atualize e tente novamente.'}, status=409)
            except OperationalError:
                return JsonResponse({'error': 'Banco ocupado. Atualize os dados e repita a operação com a mesma chave.'}, status=503)
        return wrapped
    return decorate

def body(request):
    try:
        data = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('Envie um objeto JSON válido.')
    if not isinstance(data, dict):
        raise ValueError('Envie um objeto JSON válido.')
    return data

def text(data, field, max_length=80):
    value = data.get(field, '')
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
        raise ValueError(f'Preencha {field} com até {max_length} caracteres.')
    return value.strip()

def password_value(data):
    value = data.get('password')
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ValueError('Informe uma senha de até 256 caracteres.')
    return value

ACTION_FIELDS = {
    'account.create': {'name','institution','owner_id','opening_balance_cents','reference_date'},
    'account.update': {'account_id','name','institution','owner_id','status'},
    'card.create': {'name','institution','holder_id','last_four','limit_cents','closing_day','due_day','account_id'},
    'card.update': {'card_id','name','institution','holder_id','last_four','limit_cents','closing_day','due_day','account_id','status'},
    'category.create': {'name','parent_id'},
    'category.update': {'category_id','name','parent_id','status'},
    'entry.create': {'kind','description','amount_cents','merchant','category_id','person_id','purchase_date','competence_date','due_date','method','account_id','destination_account_id','card_id','installments','paid_installments','paid','paid_on','paid_by','notes','tags','channel','recurrence','end_date'},
    'obligation.pay': {'obligation_id','amount_cents','account_id','paid_on','paid_by'},
    'invoice.pay': {'invoice_id','amount_cents','account_id','paid_on','paid_by'},
    'payment.reverse': {'payment_id','occurred_on','paid_on','reason'},
    'entry.cancel': {'entry_id','reason'},
    'obligation.adjust': {'obligation_id','kind','type','amount_cents','reason','account_id','paid_on'},
    'invoice.update': {'invoice_id','obligation_ids','obligation_id','due_date','closing_date'},
    'budget.set': {'category_id','month','amount_cents'},
    'recurrence.update': {'recurrence_id','scope','entry_id','from_date','changes'},
    'simulation': {'amount_cents','installments','due_date','months','start_month'},
}
ACTION_FIELDS['entry.create'].update({'value_mode','installment_amount_cents','first_invoice_month'})
ACTION_FIELDS['entry.preview'] = set(ACTION_FIELDS['entry.create'])
PAYMENT_FIELDS = {'obligation_id','invoice_id','mode','amount_cents','account_id','paid_on','paid_by','expected_remaining_cents','operation','notes'}
ACTION_FIELDS['payment.preview'] = set(PAYMENT_FIELDS)
ACTION_FIELDS['payment.advance'] = set(PAYMENT_FIELDS)
ACTION_FIELDS['obligation.pay'].update({'mode','expected_remaining_cents','notes'})
ACTION_FIELDS['invoice.pay'].update({'mode','expected_remaining_cents','notes'})

def validate_people(payload, member_ids):
    if isinstance(payload, dict):
        for field, value in list(payload.items()):
            if field in ('person_id','owner_id','holder_id','paid_by') and value not in (None, ''):
                valid_integer = isinstance(value, int) and not isinstance(value, bool)
                valid_string = isinstance(value, str) and value.isascii() and value.isdecimal()
                if not (valid_integer or valid_string) or int(value) not in member_ids:
                    raise ValueError('A pessoa informada não participa deste espaço.')
                payload[field] = int(value)
            else:
                validate_people(value, member_ids)
    elif isinstance(payload, list):
        for value in payload:
            validate_people(value, member_ids)

def authorized(request, space_id, admin=False, write=False):
    member = Membership.objects.select_related('workspace', 'user').filter(workspace_id=space_id, user=request.user).first()
    if not member:
        raise Http404
    if admin and member.role != 'admin':
        raise PermissionError('Somente administradores podem gerenciar participantes.')
    if write and member.role == 'reader':
        raise PermissionError('Seu perfil permite apenas consultar este espaço.')
    return member

def space_list(user):
    return [{'id': str(m.workspace_id), 'name': m.workspace.name, 'role': m.role} for m in Membership.objects.filter(user=user).select_related('workspace').order_by('workspace__created_at')]

def member_list(space_id):
    return [{'id': m.pk, 'user_id': m.user_id, 'username': m.user.username, 'display_name': m.user.first_name or m.user.username, 'role': m.role, 'is_active': m.user.is_active, 'status': 'active' if m.user.is_active else 'blocked'} for m in Membership.objects.filter(workspace_id=space_id).select_related('user').order_by('id')]

def user_identity(user):
    return {'id': user.pk, 'username': user.username,
            'display_name': user.first_name or user.username,
            'technical_admin': bool(user.is_superuser)}

def snapshot_for(member, months=12, start=None, report_month=None):
    # The SQL join enforces workspace membership on financial reads as well.
    saved = FinancialState.objects.filter(workspace_id=member.workspace_id, workspace__memberships__user_id=member.user_id).get()
    options = {'as_of': timezone.localdate(), 'months': months, 'start_month': start}
    if report_month:
        options['report_month'] = report_month
    result = domain.snapshot(copy.deepcopy(saved.document), **options)
    result.update(space={'id': str(member.workspace_id), 'name': member.workspace.name, 'role': member.role}, revision=saved.revision, members=member_list(member.workspace_id))
    result['audit'] = [{'id': event.pk, 'actor': event.actor.first_name or event.actor.username, 'action': event.action, 'created_at': event.created_at.isoformat(), 'details': event.details} for event in AuditEvent.objects.filter(workspace_id=member.workspace_id).select_related('actor').order_by('-id')[:100]]
    return result

def csrf_failure(request, reason=''):
    return JsonResponse({'error': 'Sua sessão de segurança mudou. Atualize a página e tente novamente.'}, status=403)

def index(request):
    get_token(request)
    return render(request, 'index.html')

@api(public=True)
def health(request):
    """Identify this checkout without sessions, database reads or private data."""
    identity = hashlib.sha256(str(settings.BASE_DIR.resolve()).casefold().encode()).hexdigest()[:16]
    response = JsonResponse({'application': 'organiza', 'version': settings.APP_VERSION,
                             'instance_id': identity})
    response['Cache-Control'] = 'no-store'
    return response

def static_asset(request, asset):
    if asset.startswith('/') or '\\' in asset or ':' in asset or Path(asset).is_absolute() or '..' in Path(asset).parts:
        raise Http404
    root = Path(settings.BASE_DIR) / 'static'
    target = (root / asset).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file() or any(part.startswith('.') for part in Path(asset).parts):
        raise Http404
    return FileResponse(target.open('rb'), content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')

@api(public=True)
def session_info(request):
    user = request.user
    return JsonResponse({'user': user_identity(user) if user.is_authenticated else None, 'csrf_token': get_token(request), 'spaces': space_list(user) if user.is_authenticated else [], 'version': settings.APP_VERSION, 'local_mode': settings.LOCAL_MODE, 'registration_mode': getattr(settings, 'REGISTRATION_MODE', 'open')})

def throttle(request, name, *, subject=None):
    now = timezone.now()
    # The web server supplies REMOTE_ADDR. Never trust arbitrary client XFF.
    bucket = str(subject) if subject is not None else request.META.get('REMOTE_ADDR', '')
    key = hashlib.sha256(f'{name}|{bucket}'.encode()).hexdigest()
    with transaction.atomic():
        attempt, _ = LoginAttempt.objects.select_for_update().get_or_create(key=key, defaults={'window_start': now})
        if attempt.window_start < now - timedelta(minutes=15):
            attempt.window_start, attempt.failures = now, 0
        if attempt.failures >= 10:
            return None
        attempt.failures += 1
        attempt.save(update_fields=['window_start', 'failures'])
        return attempt

@api(('POST',), public=True)
def register(request):
    mode = getattr(settings, 'REGISTRATION_MODE', 'open')
    if mode == 'closed':
        return JsonResponse({'error': 'O cadastro público está fechado. Solicite seu acesso à administração técnica.'}, status=403)
    data = body(request)
    if throttle(request, 'register') is None:
        return JsonResponse({'error': 'Muitas tentativas. Aguarde 15 minutos.'}, status=429)
    username = text(data, 'username', 64).lower()
    if not all(c.isalnum() or c in '@.+_-' for c in username) or len(username) < 3:
        raise ValueError('Use um usuário com 3 a 64 letras, números, ponto, hífen ou @.')
    password = password_value(data)
    display_name = text({'name': data.get('display_name') or username}, 'name', 80)
    candidate = User(username=username, first_name=display_name, is_active=mode == 'open')
    validate_password(password, candidate)
    with transaction.atomic():
        if User.objects.filter(username=username).exists():
            raise ValueError('Este usuário já está cadastrado.')
        candidate.set_password(password)
        candidate.save()
    if mode != 'open':
        return JsonResponse({'user': None, 'registration_pending': True,
                             'message': 'Solicitação recebida. Aguarde a aprovação da administração técnica para entrar.'}, status=202)
    login(request, candidate)
    return JsonResponse({'user': user_identity(candidate), 'csrf_token': get_token(request), 'spaces': []}, status=201)

@api(('POST',), public=True)
def sign_in(request):
    data = body(request)
    username = text(data, 'username', 64).lower()
    attempt = throttle(request, 'login')
    account_attempt = throttle(request, 'login-account', subject=username)
    if attempt is None or account_attempt is None:
        return JsonResponse({'error': 'Muitas tentativas. Aguarde 15 minutos.'}, status=429)
    user = authenticate(request, username=username, password=password_value(data))
    if user is None:
        return JsonResponse({'error': 'Usuário ou senha inválidos, ou acesso indisponível.'}, status=401)
    attempt.delete()
    account_attempt.delete()
    login(request, user)
    return JsonResponse({'user': user_identity(user), 'csrf_token': get_token(request), 'spaces': space_list(user)})

def technical_administrator(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionError('Somente a administração técnica pode gerenciar contas de usuário.')

@api()
def technical_users(request):
    technical_administrator(request)
    raw_offset = request.GET.get('offset', '0')
    if not raw_offset.isascii() or not raw_offset.isdecimal():
        raise ValueError('Página de contas inválida.')
    offset = int(raw_offset)
    if offset < 0 or offset > 100000:
        raise ValueError('Página de contas inválida.')
    users = User.objects.order_by('pk')
    rows = list(users[offset:offset + 100])
    count = users.count()
    return JsonResponse({'users': [{**user_identity(user), 'is_active': user.is_active,
                                   'status': 'active' if user.is_active else 'pending_or_blocked'} for user in rows],
                         'total': count, 'next_offset': offset + len(rows) if offset + len(rows) < count else None})

@api(('POST',))
def technical_user_status(request, user_id):
    technical_administrator(request)
    data = body(request)
    if set(data) != {'is_active'} or not isinstance(data['is_active'], bool):
        raise ValueError('Informe somente a situação ativa ou bloqueada da conta.')
    with transaction.atomic():
        # Lock technical administrators in a stable order before the subject.
        # This serializes concurrent approvals/blocks without a last-admin race.
        admins = list(User.objects.select_for_update().filter(is_superuser=True, is_active=True).order_by('pk'))
        if request.user.pk not in {user.pk for user in admins}:
            raise PermissionError('Seu acesso técnico mudou. Entre novamente para continuar.')
        target = User.objects.select_for_update().filter(pk=user_id).first()
        if not target:
            raise Http404
        active = data['is_active']
        if not active and target.pk == request.user.pk:
            raise ValueError('Não é permitido bloquear seu próprio acesso técnico.')
        if not active and target.is_superuser and target.is_active and len(admins) <= 1:
            raise ValueError('Mantenha pelo menos uma administração técnica ativa.')
        before = target.is_active
        if before != active:
            target.is_active = active
            target.save(update_fields=['is_active'])
            UserAccessEvent.objects.create(actor=request.user, subject=target,
                                           before_active=before, after_active=active)
    return JsonResponse({'user': {**user_identity(target), 'is_active': target.is_active},
                         'changed': before != active})

@api(('POST',))
def sign_out(request):
    logout(request)
    return JsonResponse({'ok': True, 'csrf_token': get_token(request)})

@api(('GET','POST'))
def spaces(request):
    if request.method == 'GET':
        return JsonResponse({'spaces': space_list(request.user)})
    data = body(request)
    with transaction.atomic():
        space = Workspace.objects.create(name=text(data, 'name'), created_by=request.user)
        member = Membership.objects.create(workspace=space, user=request.user, role='admin')
        FinancialState.objects.create(workspace=space, document=domain.new_state())
        AuditEvent.objects.create(workspace=space, actor=request.user, action='space.create', details={'name': space.name})
    return JsonResponse({'space': {'id': str(space.pk), 'name': space.name, 'role': member.role}, 'spaces': space_list(request.user)}, status=201)

@api()
def state(request, space_id):
    member = authorized(request, space_id)
    months = int(request.GET.get('months', 12))
    if not 12 <= months <= 60:
        raise ValueError('Escolha entre 12 e 60 meses para a projeção.')
    return JsonResponse(snapshot_for(member, months, request.GET.get('start'), request.GET.get('report_month')))

@api(('POST',))
def actions(request, space_id):
    data = body(request)
    action = text(data, 'action')
    payload = data.get('data', {})
    if not isinstance(payload, dict):
        raise ValueError('Dados da operação devem ser um objeto.')
    sensitive = {'cvv', 'cvc', 'pan', 'pin', 'password', 'senha', 'secret', 'token', 'card_number', 'full_number', 'numero_cartao', 'number'}
    def has_sensitive(value):
        if isinstance(value, dict):
            return any(str(key).lower() in sensitive or has_sensitive(item) for key, item in value.items())
        return isinstance(value, list) and any(has_sensitive(item) for item in value)
    if has_sensitive(payload):
        raise ValueError('Não envie número completo, código de segurança ou senha de cartão.')
    if action in ACTION_FIELDS and set(payload) - ACTION_FIELDS[action]:
        raise ValueError('A operação contém campos não reconhecidos.')
    recurrence = payload.get('recurrence')
    if isinstance(recurrence, dict) and set(recurrence) - {'frequency','end_date'}:
        raise ValueError('A recorrência contém campos não reconhecidos.')
    member = authorized(request, space_id, write=action not in ('simulation', 'entry.preview', 'payment.preview'))
    member_ids = set(Membership.objects.filter(workspace_id=space_id).values_list('user_id', flat=True))
    validate_people(payload, member_ids)
    if action in ('simulation', 'entry.preview', 'payment.preview'):
        saved = FinancialState.objects.filter(workspace_id=space_id, workspace__memberships__user=request.user).get()
        if action in ('entry.preview','payment.preview'):
            expected = data.get('expected_revision')
            if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
                raise ValueError('Informe a revisão atual do espaço.')
            if expected != saved.revision:
                message = 'Outro acesso alterou este espaço. Confira novamente os valores antes de confirmar.'
                return JsonResponse({'error': message, 'revision': saved.revision}, status=409)
            result = domain.mutate(copy.deepcopy(saved.document), action, payload, request.user.pk, today=timezone.localdate())
            result['revision'] = saved.revision
        else:
            result = domain.mutate(copy.deepcopy(saved.document), action, payload, request.user.pk, today=timezone.localdate())
        return JsonResponse({'result': result, 'revision': saved.revision})
    request_id = uuid.UUID(text(data, 'request_id', 36))
    expected = data.get('expected_revision')
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 0:
        raise ValueError('Informe a revisão atual do espaço.')
    fingerprint = hashlib.sha256(json.dumps({'action': action, 'data': payload}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    with transaction.atomic():
        # Recheck inside the write transaction so concurrent role changes cannot race.
        member = authorized(request, space_id, write=True)
        previous = Operation.objects.filter(workspace_id=space_id, request_id=request_id).first()
        if previous:
            if previous.fingerprint != fingerprint or previous.actor_id != request.user.pk:
                return JsonResponse({'error': 'Esta chave já foi usada em outra operação.'}, status=409)
            return JsonResponse({'result': previous.result, 'state': snapshot_for(member), 'revision': FinancialState.objects.get(workspace_id=space_id).revision, 'duplicate': True})
        saved = FinancialState.objects.get(workspace_id=space_id)
        if saved.revision != expected:
            return JsonResponse({'error': 'Outro acesso alterou este espaço. Atualize antes de salvar.', 'revision': saved.revision}, status=409)
        document = copy.deepcopy(saved.document)
        result = domain.mutate(document, action, payload, request.user.pk, today=timezone.localdate())
        updated = FinancialState.objects.filter(workspace_id=space_id, revision=expected).update(document=document, revision=expected + 1, updated_at=timezone.now())
        if updated != 1:
            raise IntegrityError('revision conflict')
        Operation.objects.create(workspace_id=space_id, request_id=request_id, actor=request.user, fingerprint=fingerprint, result=result)
        AuditEvent.objects.create(workspace_id=space_id, actor=request.user, action=action, details={'request_id': str(request_id), 'revision': expected + 1, 'data': payload, 'result': result})
        return JsonResponse({'result': result, 'state': snapshot_for(member), 'revision': expected + 1})

@api(('GET','POST'))
def members(request, space_id):
    authorized(request, space_id, admin=request.method == 'POST')
    if request.method == 'POST':
        data = body(request)
        role = data.get('role', 'reader')
        if role not in ('admin','collaborator','reader'):
            raise ValueError('Perfil inválido.')
        user = User.objects.filter(username=text(data, 'username', 64).lower()).first()
        if not user:
            raise ValueError('Peça à pessoa para criar seu acesso primeiro e informe o usuário exato.')
        with transaction.atomic():
            authorized(request, space_id, admin=True)
            Membership.objects.create(workspace_id=space_id, user=user, role=role)
            AuditEvent.objects.create(workspace_id=space_id, actor=request.user, action='member.add', details={'user_id': user.pk, 'role': role})
    return JsonResponse({'members': member_list(space_id)})

@api(('POST','DELETE'))
def member_update(request, space_id, member_id):
    with transaction.atomic():
        authorized(request, space_id, admin=True)
        member = Membership.objects.filter(pk=member_id, workspace_id=space_id).first()
        if not member:
            raise Http404
        data = body(request)
        role = data.get('role') if request.method == 'POST' else None
        if request.method == 'POST' and role not in ('admin','collaborator','reader'):
            raise ValueError('Perfil inválido.')
        if member.role == 'admin' and role != 'admin' and Membership.objects.filter(workspace_id=space_id, role='admin').count() <= 1:
            raise ValueError('Mantenha pelo menos um administrador neste espaço.')
        AuditEvent.objects.create(workspace_id=space_id, actor=request.user, action='member.remove' if role is None else 'member.role', details={'user_id': member.user_id, 'role': role})
        if role is None:
            member.delete()
        else:
            member.role = role
            member.save(update_fields=['role'])
    return JsonResponse({'members': member_list(space_id)})
