"""Start/status/stop only this Organiza installation; never creates a database."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.runtime_lock import exclusive_lock, instance_id, metadata_path, runtime_directory


def configuration():
    # Match settings.py without importing Django or creating its data/key files.
    values = dict(os.environ)
    env_file = ROOT / '.env'
    if env_file.is_file():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    port_value = values.get('APP_PORT', '8765')
    if not re.fullmatch(r'\d+', port_value) or not 1 <= int(port_value) <= 65535:
        raise RuntimeError('APP_PORT deve conter uma porta inteira entre 1 e 65535.')
    database = Path(values.get('APP_DB_PATH', str(ROOT / 'data' / 'finance.sqlite3')))
    if not database.is_absolute():
        database = ROOT / database
    database = database.resolve()
    if not database.is_relative_to(ROOT):
        raise RuntimeError('O banco configurado fica fora da raiz exclusiva. Nenhum processo foi iniciado.')
    private_url = values.get('APP_PRIVATE_HTTPS_ORIGIN', '').rstrip('/')
    if private_url:
        try:
            private = urllib.parse.urlsplit(private_url)
            valid_port = private.port is None or 1 <= private.port <= 65535
        except ValueError:
            raise RuntimeError('APP_PRIVATE_HTTPS_ORIGIN não é uma origem HTTPS válida.') from None
        if (private.scheme != 'https' or not private.hostname or private.username or private.password
                or private.query or private.fragment or private.path or not valid_port):
            raise RuntimeError('APP_PRIVATE_HTTPS_ORIGIN deve conter somente a origem HTTPS privada, sem credenciais ou caminho.')
    return {'port': int(port_value), 'database': database,
            'private_url': private_url, 'environment': values}


def validate_database(database):
    if not database.is_file():
        raise RuntimeError(f'Banco existente não encontrado: {database}. Não será criada uma instalação vazia.')
    try:
        with database.open('rb') as handle:
            if handle.read(16) != b'SQLite format 3\x00':
                raise RuntimeError('O arquivo configurado não é um banco SQLite válido.')
        with sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {'django_migrations', 'auth_user', 'finance_workspace', 'finance_financialstate', 'finance_operation'}
            if not required.issubset(tables):
                raise RuntimeError('O banco não contém a estrutura esperada do Organiza. Nenhuma migração automática foi aplicada.')
            if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('A verificação SQLite encontrou um problema; preserve o arquivo e revise o backup.')
    except sqlite3.Error:
        raise RuntimeError('Não foi possível validar o banco existente em leitura. Nenhum banco foi criado ou alterado.') from None


def health(port):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/health', headers={'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            result = json.load(response)
        return result if isinstance(result, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def is_our_health(value):
    return bool(value and value.get('application') == 'organiza' and value.get('instance_id') == instance_id(ROOT))


def port_is_open(port):
    with socket.socket() as client:
        client.settimeout(.5)
        return client.connect_ex(('127.0.0.1', port)) == 0


def powershell():
    executable = shutil.which('powershell.exe') or shutil.which('pwsh.exe')
    if not executable:
        raise RuntimeError('PowerShell não encontrado para verificar o processo. Nenhum processo será encerrado.')
    return executable


def windows_process(pid):
    # Only a validated integer is interpolated; command lines are never logged.
    command = f"Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}' | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run([powershell(), '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, timeout=15)
    try:
        return json.loads(result.stdout.lstrip('\ufeff')) if result.stdout.strip() else None
    except ValueError:
        return None


def listeners(port):
    if os.name != 'nt':
        # POSIX support is only for isolated development, with psutil optional.
        try:
            import psutil
            return sorted({item.pid for item in psutil.net_connections(kind='tcp')
                           if item.status == 'LISTEN' and item.laddr.port == port and item.pid})
        except (ImportError, OSError):
            return []
    result = subprocess.run(['netstat', '-ano', '-p', 'tcp'], capture_output=True, text=True, timeout=10)
    owners = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == 'TCP' and parts[1].rsplit(':', 1)[-1] == str(port):
            # A listener's remote endpoint has port zero; this avoids localized state names.
            if parts[2].rsplit(':', 1)[-1] == '0' and parts[-1].isdigit():
                owners.add(int(parts[-1]))
    return sorted(owners)


def command_arguments(command):
    if os.name != 'nt':
        import shlex
        return shlex.split(command)
    import ctypes
    from ctypes import wintypes
    count = ctypes.c_int()
    parser = ctypes.windll.shell32.CommandLineToArgvW
    parser.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parser.restype = ctypes.POINTER(wintypes.LPWSTR)
    pointers = parser(command, ctypes.byref(count))
    if not pointers:
        return []
    try:
        return [pointers[index] for index in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(pointers, wintypes.HLOCAL))


def owned_process(pid):
    if os.name == 'nt':
        record = windows_process(pid)
        if not record:
            return False
        args = command_arguments(record.get('CommandLine') or '')
    else:
        try:
            args = subprocess.check_output(['ps', '-p', str(pid), '-o', 'args='], text=True).strip().split()
        except subprocess.SubprocessError:
            return False
    expected_script = ROOT / 'serve.py'
    if len(args) != 2:
        return False
    executable = Path(args[0]).resolve()
    script = Path(args[1])
    if script.is_absolute():
        return script.resolve() == expected_script.resolve() and executable.name.lower() in {'python', 'python3', 'python.exe', 'pythonw.exe'}
    expected_python = (ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')).resolve()
    return args[1] == 'serve.py' and executable == expected_python


def read_metadata(port):
    path = ROOT / 'data' / 'runtime' / f'server-{port}.json'
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('instance_id') != instance_id(ROOT) or record.get('port') != port:
            return None
        return record
    except (OSError, ValueError):
        return None


def serve_state(record, config, dns_name=''):
    """Inspect only our endpoint; never resets or changes another service."""
    origin = config.get('private_url')
    if not isinstance(record, dict):
        return 'unavailable', 'O Tailscale retornou uma configuração Serve não reconhecida.'
    if not origin:
        return 'not_configured', 'Endereço HTTPS privado ainda não configurado no Organiza.'
    parsed = urllib.parse.urlsplit(origin)
    endpoint = f"{parsed.hostname}:{parsed.port or 443}"
    if (record.get('AllowFunnel') or {}).get(endpoint):
        return 'public_funnel', 'ATENÇÃO: este endpoint está marcado para Funnel público. Não o use como acesso privado; revise somente esta rota.'
    handler = ((record.get('Web') or {}).get(endpoint, {}).get('Handlers') or {}).get('/')
    tcp = (record.get('TCP') or {}).get(str(parsed.port or 443), {})
    if not handler:
        return 'not_configured', 'Tailscale Serve ainda não possui a rota HTTPS do Organiza. O endereço acima está apenas preparado.'
    if (dns_name and parsed.hostname != dns_name) or not tcp.get('HTTPS') or (handler.get('Proxy') or '').rstrip('/') != f"http://127.0.0.1:{config['port']}":
        return 'wrong_target', 'A rota Serve encontrada não corresponde ao backend e endereço configurados. Nenhuma rota foi modificada.'
    return 'configured', 'Rota HTTPS privada configurada no Tailscale Serve; a disponibilidade depende da conexão do servidor.'


def tailscale_status(config):
    candidates = [shutil.which('tailscale.exe'), shutil.which('tailscale')]
    candidates.append(str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tailscale' / 'tailscale.exe'))
    executable = next((value for value in candidates if value and Path(value).is_file()), None)
    if not executable:
        return {'state': 'not_installed', 'serve_state': 'missing', 'message': 'Tailscale não encontrado. O acesso local pode continuar.'}
    try:
        result = subprocess.run([executable, 'status', '--json'], capture_output=True, text=True, timeout=8)
        record = json.loads(result.stdout)
        connected = result.returncode == 0 and record.get('BackendState') == 'Running' and record.get('Self', {}).get('Online', False)
        dns_name = record.get('Self', {}).get('DNSName', '').rstrip('.')
        try:
            serving = subprocess.run([executable, 'serve', 'status', '--json'], capture_output=True, text=True, timeout=8)
            if serving.returncode == 0:
                serving_state, serving_message = serve_state(json.loads(serving.stdout), config, dns_name)
            else:
                serving_state, serving_message = 'unavailable', 'Não foi possível consultar a configuração do Tailscale Serve.'
        except (OSError, ValueError, subprocess.TimeoutExpired):
            serving_state, serving_message = 'unavailable', 'Não foi possível consultar a configuração do Tailscale Serve.'
        return {'state': 'connected' if connected else 'disconnected', 'serve_state': serving_state,
                'message': 'Tailscale conectado.' if connected else 'Tailscale desconectado: conecte o aplicativo para permitir acesso privado.',
                'serve_message': serving_message, 'dns_name': dns_name}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'state': 'unavailable', 'serve_state': 'unavailable', 'message': 'Não foi possível consultar o Tailscale. Confira o aplicativo do Tailscale.'}


def status(config, *, include_network=True):
    check = health(config['port'])
    running = is_our_health(check)
    record = read_metadata(config['port'])
    owners = listeners(config['port']) if not running else []
    return {'application': 'organiza', 'status': 'running' if running else 'port_conflict' if port_is_open(config['port']) or owners else 'stopped',
            'version': check.get('version') if running else None,
            'local_url': f"http://127.0.0.1:{config['port']}/",
            'private_url': config['private_url'] or None,
            'database_path': str(config['database']),
            'running_database_path': record.get('database_path') if record else None,
            'port_owner_pids': owners,
            'tailscale': tailscale_status(config) if include_network else None}


def log_event(event, port):
    directory = runtime_directory(ROOT)
    with (directory / 'lifecycle.log').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'event': event, 'port': port}) + '\n')


def start(config):
    validate_database(config['database'])
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file() or not (ROOT / 'serve.py').is_file():
        raise RuntimeError('Ambiente Python existente ou serve.py não encontrado. A instalação não será recriada automaticamente.')
    with exclusive_lock(runtime_directory(ROOT) / f"control-{config['port']}.lock", timeout=25):
        check = health(config['port'])
        if is_our_health(check):
            record = read_metadata(config['port'])
            if record and Path(record.get('database_path', '')).resolve() != config['database']:
                raise RuntimeError('O Organiza já está funcionando com outro banco configurado. Pare e confira o caminho antes de iniciar.')
            return {'result': 'already_running', **status(config)}
        if port_is_open(config['port']) or listeners(config['port']):
            owners = listeners(config['port'])
            owner_message = ', '.join(str(pid) for pid in owners) or 'não identificado'
            raise RuntimeError(f"Porta {config['port']} ocupada por outro serviço ou instalação (PID {owner_message}). Nenhum processo foi encerrado.")
        tag = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        logs = ROOT / 'data' / 'runtime'
        with (logs / f'organiza-{tag}.stdout.log').open('ab') as output, (logs / f'organiza-{tag}.stderr.log').open('ab') as errors:
            process = subprocess.Popen([str(python), str(ROOT / 'serve.py')], cwd=ROOT,
                                       env=config['environment'], stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=errors,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                       start_new_session=os.name != 'nt')
        for _ in range(100):
            if is_our_health(health(config['port'])):
                log_event('started', config['port'])
                return {'result': 'started', 'log_prefix': str(logs / f'organiza-{tag}'), **status(config)}
            if process.poll() is not None:
                break
            time.sleep(.15)
        raise RuntimeError(f"O Organiza não respondeu. Consulte somente os logs desta tentativa em {logs / ('organiza-' + tag)}.*.log. Nenhum banco foi reinicializado.")


def stop(config):
    port = config['port']
    with exclusive_lock(runtime_directory(ROOT) / f'control-{port}.lock', timeout=25):
        owners = listeners(port)
        record = read_metadata(port)
        if not owners:
            # A PID file is not proof of port ownership: its PID may have been
            # reused by a newer process after an unclean shutdown.
            return {'result': 'already_stopped', **status(config)}
        if len(owners) != 1 or not owned_process(owners[0]):
            raise RuntimeError(f'Porta {port} pertence a um processo que não foi confirmado como este Organiza. Nada foi encerrado.')
        pid = owners[0]
        if not is_our_health(health(port)) and not (record and record.get('pid') == pid):
            raise RuntimeError('Não foi possível confirmar a identidade do servidor. Nenhum processo foi encerrado.')
        # On Windows SIGTERM targets only the confirmed Python server process.
        # SQLite transactions remain atomic; no database file is removed or reset.
        os.kill(pid, signal.SIGTERM)
        for _ in range(60):
            if not port_is_open(port):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('O processo recebeu o pedido de parada, mas a porta continua ocupada. Confira status; nenhum outro processo será encerrado.')
        if record and record.get('pid') == pid:
            metadata_path(ROOT, port).unlink(missing_ok=True)
        log_event('stopped', port)
        return {'result': 'stopped', **status(config)}


def display(result):
    state = result.get('result', result.get('status'))
    print({'started': 'Organiza iniciado.', 'already_running': 'Organiza já está funcionando; nenhum processo duplicado foi criado.',
           'stopped': 'Organiza parado.', 'already_stopped': 'Organiza já está parado.', 'running': 'Organiza funcionando.',
           'port_conflict': 'Porta local ocupada por outro serviço ou instalação.', 'checked': 'Instalação e banco existentes conferidos.'}.get(state, str(state)))
    print('Local: ' + result['local_url'])
    print('HTTPS privado configurado: ' + (result['private_url'] or 'ainda não configurado'))
    if result.get('tailscale'):
        print(result['tailscale']['message'])
        if result['tailscale'].get('serve_message'):
            print(result['tailscale']['serve_message'])
    if result.get('log_prefix'):
        print('Logs desta inicialização: ' + result['log_prefix'] + '.*.log')
    if result.get('port_owner_pids'):
        print('Processos na porta (PID): ' + ', '.join(str(value) for value in result['port_owner_pids']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'check'])
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        config = configuration()
        if args.action == 'start':
            result = start(config)
        elif args.action == 'stop':
            result = stop(config)
        elif args.action == 'check':
            validate_database(config['database'])
            result = {'result': 'checked', **status(config)}
        else:
            result = status(config)
        # ASCII JSON remains portable across Windows PowerShell 5 code pages.
        print(json.dumps(result, ensure_ascii=True)) if args.json else display(result)
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, RuntimeError) else 'Não foi possível concluir a operação local. Confira permissões e logs; nenhum banco será recriado.'
        print(json.dumps({'error': message}, ensure_ascii=True) if args.json else 'ERRO: ' + message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
