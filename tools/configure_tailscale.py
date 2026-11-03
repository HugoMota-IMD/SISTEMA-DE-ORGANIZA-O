"""Inspect or change only Organiza's private Tailscale Serve HTTPS endpoint.

Does not install software, enable Funnel, change tailnet policies, start Django,
create a database or reset Serve. Network/configuration commands are bounded.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.organiza_runtime import ROOT, configuration, validate_database
from tools.runtime_lock import exclusive_lock, instance_id, runtime_directory

READ_TIMEOUT = 8
CHANGE_TIMEOUT = 18
ADMIN_STEP = ('No console administrativo do Tailscale, abra DNS, confira MagicDNS e '
              'HTTPS Certificates > Enable HTTPS. Habilite somente HTTPS/Serve, sem Funnel. '
              'Se houver acesso negado no Windows, execute este mesmo comando em Terminal '
              'como administrador. Depois repita apply e check --verify.')


def executable():
    candidates = [shutil.which('tailscale.exe'), shutil.which('tailscale'),
                  str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tailscale' / 'tailscale.exe')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError('Tailscale não encontrado. Instale/conecte o cliente; o Organiza local não foi alterado.')


def read_json(binary, *arguments):
    try:
        result = subprocess.run([binary, *arguments], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=READ_TIMEOUT)
        if result.returncode:
            raise RuntimeError('Não foi possível consultar o Tailscale. Confira conexão e permissões; nenhuma rota foi alterada.')
        record = json.loads(result.stdout.lstrip('\ufeff'))
        if not isinstance(record, dict):
            raise ValueError('object expected')
        return record
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise RuntimeError('A consulta ao Tailscale falhou ou excedeu o tempo limite. Nenhuma alteração foi solicitada nesta consulta.') from None


def inspect(binary):
    return {'node': read_json(binary, 'status', '--json'),
            'serve': read_json(binary, 'serve', 'status', '--json'),
            'services': read_json(binary, 'serve', 'get-config', '--all')}


def target(config, node, *, require_online=False):
    origin = config.get('private_url', '')
    try:
        parsed = urllib.parse.urlsplit(origin)
        port = parsed.port if parsed.port is not None else 443
    except (ValueError, AttributeError):
        raise RuntimeError('APP_PRIVATE_HTTPS_ORIGIN deve conter a origem HTTPS exata do servidor.') from None
    host = parsed.hostname or ''
    labels = host.split('.')
    if (parsed.scheme != 'https' or not 1 <= port <= 65535 or parsed.username or parsed.password or parsed.path
            or parsed.query or parsed.fragment or not host.endswith('.ts.net')
            or len(labels) < 3 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)):
        raise RuntimeError('APP_PRIVATE_HTTPS_ORIGIN deve ser HTTPS do Tailscale, sem caminho, credenciais ou curingas.')
    self_record = node.get('Self') or {}
    if not isinstance(self_record, dict):
        raise RuntimeError('O Tailscale não informou a identidade deste computador.')
    dns_name = str(self_record.get('DNSName') or '').rstrip('.').lower()
    if host != dns_name:
        raise RuntimeError('O endereço privado não corresponde ao Self.DNSName deste computador. Confira o servidor; nenhuma rota foi alterada.')
    online = node.get('BackendState') == 'Running' and self_record.get('Online') is True
    tailnet = node.get('CurrentTailnet') or {}
    magic_dns = isinstance(tailnet, dict) and tailnet.get('MagicDNSEnabled') is True
    if require_online and not online:
        raise RuntimeError('Tailscale desconectado. Conecte este servidor antes de alterar a rota privada.')
    if require_online and not magic_dns:
        raise RuntimeError('MagicDNS não está habilitado ou não pôde ser confirmado. ' + ADMIN_STEP)
    return {'host': host, 'https_port': port, 'endpoint': f'{host}:{port}',
            'origin': 'https://' + host + (f':{port}' if port != 443 else ''),
            'backend': f"http://127.0.0.1:{config['port']}",
            'online': online, 'magic_dns': magic_dns}


def map_field(record, key):
    value = record.get(key, {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise RuntimeError('Configuração Serve não reconhecida; nenhuma rota será substituída.')
    return value


def route_state(record, desired):
    """Reject occupied/public/raw endpoints without printing another app's target."""
    web, tcp, funnel = (map_field(record, key) for key in ('Web', 'TCP', 'AllowFunnel'))
    port = str(desired['https_port'])
    if any(enabled and str(endpoint).rsplit(':', 1)[-1] == port for endpoint, enabled in funnel.items()):
        raise RuntimeError('Esta porta HTTPS possui Funnel público. Escolha outra porta livre; nenhum Funnel ou serviço existente foi alterado.')
    transport = tcp.get(port, {})
    if not isinstance(transport, dict) or any(key != 'HTTPS' for key in transport) or (transport and transport.get('HTTPS') is not True):
        raise RuntimeError('Esta porta já possui outro serviço TCP/TLS. Escolha outra porta HTTPS livre; nada foi alterado.')
    shared_handlers = any(str(name).rsplit(':', 1)[-1] == port and isinstance(data, dict)
                          and any(path != '/' or name != desired['endpoint'] for path in map_field(data, 'Handlers'))
                          for name, data in web.items())
    if shared_handlers and transport.get('HTTPS') is not True:
        raise RuntimeError('A porta possui configuração compartilhada incompleta. Revise-a manualmente; nenhuma rota será substituída.')
    endpoint = web.get(desired['endpoint'], {})
    if not isinstance(endpoint, dict):
        raise RuntimeError('Endpoint Serve não reconhecido; nenhuma rota será substituída.')
    handlers = map_field(endpoint, 'Handlers')
    if '/' not in handlers:
        return 'not_configured'
    handler = handlers['/']
    if (not isinstance(handler, dict) or set(handler) != {'Proxy'}
            or handler['Proxy'] not in (desired['backend'], desired['backend'] + '/')):
        raise RuntimeError('A rota raiz HTTPS pertence a outro serviço. Escolha outra porta livre; nenhuma rota foi substituída.')
    return 'configured' if transport.get('HTTPS') is True else 'not_configured'


def preserved_projection(record, desired):
    """Ignore only the owned root handler, HTTPS transport and Funnel flag."""
    result = deepcopy(record)
    endpoint, port = desired['endpoint'], str(desired['https_port'])
    web = map_field(result, 'Web')
    if endpoint in web:
        data = web[endpoint]
        if isinstance(data, dict):
            handlers = map_field(data, 'Handlers')
            handlers.pop('/', None)
            if not handlers:
                data.pop('Handlers', None)
            if not data:
                web.pop(endpoint)
    tcp = map_field(result, 'TCP')
    shared_transport = any(str(name).rsplit(':', 1)[-1] == port and isinstance(data, dict)
                           and bool(map_field(data, 'Handlers')) for name, data in web.items())
    if not shared_transport and port in tcp and isinstance(tcp[port], dict):
        tcp[port].pop('HTTPS', None)
        if not tcp[port]:
            tcp.pop(port)
    funnel = map_field(result, 'AllowFunnel')
    funnel.pop(endpoint, None)
    for key in ('Web', 'TCP', 'AllowFunnel'):
        if not result.get(key):
            result.pop(key, None)
    return result


def root_handler_exists(record, desired):
    endpoint = map_field(record, 'Web').get(desired['endpoint'], {})
    return '/' in map_field(endpoint, 'Handlers')


def snapshot(before, desired):
    directory = runtime_directory(ROOT)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    path = directory / f'tailscale-before-{stamp}-{uuid.uuid4().hex[:8]}.json'
    # Configuration only: no peers, user identities, cookies or financial state.
    with path.open('x', encoding='utf-8') as stream:
        json.dump({'captured_at': datetime.now(timezone.utc).isoformat(),
                   'origin': desired['origin'], 'backend': desired['backend'],
                   'serve_status': before['serve'], 'service_config': before['services']},
                  stream, indent=2)
    return path


def change(binary, action, desired):
    arguments = [binary, 'serve', '--bg', f"--https={desired['https_port']}", '--set-path=/']
    arguments.append(desired['backend'] if action == 'apply' else 'off')
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=CHANGE_TIMEOUT)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        # subprocess.run terminates only the CLI child it created. The Tailscale
        # daemon and other Serve endpoints are not stopped or reset.
        return False
    except OSError:
        raise RuntimeError('Não foi possível executar o CLI do Tailscale. Confira a configuração antes de repetir; nenhum reset foi executado.') from None


def health_check(url):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, stream, code, message, headers, redirected_url):
            return None
    # Direct local/tailnet request; normal HTTPS certificate validation remains.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        request = urllib.request.Request(url.rstrip('/') + '/api/health', headers={'Accept': 'application/json'})
        with opener.open(request, timeout=8) as response:
            value = json.loads(response.read(65536))
        success = (isinstance(value, dict) and value.get('application') == 'organiza'
                   and value.get('instance_id') == instance_id(ROOT))
        return {'ok': success, 'message': 'Organiza desta instalação respondeu.' if success else 'A resposta não identifica esta instalação do Organiza.'}
    except (OSError, ValueError, urllib.error.URLError):
        return {'ok': False, 'message': 'Sem resposta válida. Confira servidor, Tailscale, DNS e certificado; nenhum dado financeiro foi consultado.'}


def check(config, binary, *, verify=False):
    current = inspect(binary)
    desired = target(config, current['node'])
    try:
        state = route_state(current['serve'], desired)
        message = ('Rota HTTPS privada configurada.' if state == 'configured' else
                   'Rota HTTPS ainda não configurada. O endereço abaixo é provisório. ' + ADMIN_STEP)
    except RuntimeError as error:
        state, message = 'conflict', str(error)
    result = {'result': 'checked', 'tailscale_state': 'connected' if desired['online'] else 'disconnected',
              'magic_dns': desired['magic_dns'], 'serve_state': state,
              'private_url': desired['origin'] + '/', 'provisional_url': state != 'configured',
              'backend_url': desired['backend'] + '/', 'message': message}
    if not desired['online']:
        result['message'] = 'Tailscale desconectado; o acesso privado não está disponível. ' + message
    if verify:
        result['verification'] = {
            'local': health_check(desired['backend']),
            'private_https': health_check(desired['origin']) if state == 'configured' and desired['online'] else
                {'ok': False, 'message': 'HTTPS não testado: rota privada ausente, conflitante ou Tailscale desconectado.'}}
    return result


def mutate(config, binary, action):
    if action not in {'apply', 'disable'}:
        raise RuntimeError('Somente apply e disable podem alterar a rota privada do Organiza.')
    if action == 'apply':
        validate_database(config['database'])
    with exclusive_lock(runtime_directory(ROOT) / 'tailscale-serve.lock', timeout=2):
        before = inspect(binary)
        desired = target(config, before['node'], require_online=True)
        state = route_state(before['serve'], desired)
        if (action == 'apply' and state == 'configured') or (action == 'disable' and not root_handler_exists(before['serve'], desired)):
            return {'result': 'already_configured' if action == 'apply' else 'already_disabled',
                    'private_url': desired['origin'] + '/', 'serve_state': state,
                    'provisional_url': state != 'configured',
                    'message': 'Nenhum comando de alteração foi necessário.'}
        path = snapshot(before, desired)
        succeeded = change(binary, action, desired)
        # Re-read even after timeout/nonzero exit: an uncertain response is not
        # evidence that the daemon did or did not persist an endpoint.
        try:
            after = inspect(binary)
        except RuntimeError:
            raise RuntimeError(f'Não foi possível conferir o resultado. Preserve {path} e execute check antes de repetir. Nenhum reset será executado.') from None
        if (preserved_projection(before['serve'], desired) != preserved_projection(after['serve'], desired)
                or before['services'] != after['services']):
            raise RuntimeError(f'Foi detectada alteração fora do endpoint esperado. Revise manualmente usando {path}; não houve restauração ou reset automático.')
        actual = route_state(after['serve'], desired)
        expected = 'configured' if action == 'apply' else 'not_configured'
        if actual != expected or (action == 'disable' and root_handler_exists(after['serve'], desired)):
            prefix = 'O CLI não concluiu a configuração no tempo/permissão disponível. ' if not succeeded else 'O resultado não corresponde ao endpoint esperado. '
            raise RuntimeError(prefix + ADMIN_STEP + f' Configuração anterior preservada em {path}.')
        return {'result': 'configured' if action == 'apply' else 'disabled',
                'serve_state': actual, 'private_url': desired['origin'] + '/',
                'provisional_url': actual != 'configured',
                'snapshot': str(path), 'other_services_preserved': True,
                'message': 'Rota HTTPS privada conferida.' if action == 'apply' else
                    'Somente a rota do Organiza foi removida. O backend e outros serviços continuam como estavam.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'apply', 'disable'))
    parser.add_argument('--verify', action='store_true', help='GET local/HTTPS /api/health, com validação normal do certificado.')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.verify and args.action == 'disable':
        parser.error('--verify se aplica somente a check ou apply.')
    try:
        config, binary = configuration(), executable()
        result = check(config, binary, verify=args.verify) if args.action == 'check' else mutate(config, binary, args.action)
        if args.verify and args.action == 'apply':
            result['verification'] = check(config, binary, verify=True)['verification']
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            print(result['message'])
            print('HTTPS privado' + (' (provisório)' if result.get('provisional_url') else '') + ': ' + result['private_url'])
            if result.get('verification'):
                print('Verificação: ' + json.dumps(result['verification'], ensure_ascii=True))
        return 3 if args.verify and not all(item['ok'] for item in result['verification'].values()) else 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, RuntimeError) else 'Falha operacional. Confira permissões e a configuração; nenhum reset será executado.'
        print(json.dumps({'error': message}, ensure_ascii=True) if args.json else 'ERRO: ' + message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
