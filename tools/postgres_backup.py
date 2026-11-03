"""Consistent custom PostgreSQL dump encrypted with age public recipients.

No upload or scheduler is activated here. Run this independently of the web
process. Direct DATABASE_URL_UNPOOLED and age identity live in secure env/files,
never in the command line or repository. Restore requires an empty PostgreSQL DB.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.postgres_common import binary, direct_url, libpq_environment, load_env_file, management_error, private_temporary


def inside(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise RuntimeError('Use um arquivo dentro da raiz exclusiva para o backup local.')
    return path


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def run_command(arguments, *, env=None, output=None):
    result = subprocess.run(arguments, env=env, stdin=subprocess.DEVNULL,
                            stdout=output if output is not None else subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=600)
    if result.returncode:
        raise RuntimeError('A ferramenta de backup/restauração recusou a operação. Detalhes que podem conter credenciais ou dados foram omitidos.')
    return result


def backup(output, *, recipient=None):
    target = inside(output)
    if not target.name.endswith('.age'):
        raise RuntimeError('O backup deve terminar em .age; não gerar cópia externa sem cifragem.')
    manifest = target.with_name(target.name + '.json')
    if target.exists() or manifest.exists():
        raise RuntimeError('O destino já existe; backups nunca sobrescrevem arquivos.')
    recipient = recipient or os.getenv('AGE_RECIPIENT')
    if not recipient or not recipient.startswith(('age1', 'ssh-')):
        raise RuntimeError('Defina AGE_RECIPIENT com a chave pública de backup; não use a chave privada no agendamento.')
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False
    manifest_created = False
    try:
        # Each temporary directory is created here, never derived from a user's
        # database path. Cleanup removes only this exclusively created directory.
        with private_temporary('organiza-pg-backup-') as directory:
            dump = directory / 'database.dump'
            with libpq_environment() as env:
                run_command([binary('pg_dump'), '--format=custom', '--no-owner', '--no-acl',
                             '--no-password', '--file', str(dump)], env=env)
            with dump.open('rb') as probe:
                valid_dump = probe.read(5) == b'PGDMP'
            if not valid_dump:
                raise RuntimeError('Dump PostgreSQL ausente ou inválido; nenhum backup foi entregue.')
            dump.chmod(0o600)
            run_command([binary('pg_restore'), '--list', str(dump)])
            with target.open('xb') as encrypted:
                created = True
                run_command([binary('age'), '--encrypt', '--recipient', recipient, str(dump)], output=encrypted)
            target.chmod(0o600)
        result = {'format': 'postgres-custom+age', 'created_at': datetime.now(timezone.utc).isoformat(),
                  'encrypted_sha256': sha(target), 'encrypted_bytes': target.stat().st_size,
                  'credential_in_arguments': False, 'external_upload_configured': False}
        with manifest.open('x', encoding='utf-8') as handle:
            manifest_created = True
            json.dump(result, handle, indent=2)
        return {'result': 'encrypted_backup_created', **result}
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        if manifest_created:
            manifest.unlink(missing_ok=True)
        raise


def empty_database(url):
    import psycopg
    with psycopg.connect(url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%%' AND c.relkind IN ('r','p','v','m','S')")
            if cursor.fetchone()[0]:
                raise RuntimeError('A restauração exige banco PostgreSQL vazio; nenhum objeto ou dado existente foi sobrescrito.')


def restore(source, *, identity=None, confirm_empty=False, approved_real=False):
    encrypted = inside(source)
    if not encrypted.is_file() or not encrypted.name.endswith('.age'):
        raise RuntimeError('Backup age existente não encontrado.')
    if not confirm_empty:
        raise RuntimeError('Confirme o destino vazio com --confirm-empty-target; a restauração nunca limpa um banco existente.')
    url = direct_url()
    parsed = urlsplit(url)
    database = unquote(parsed.path[1:])
    is_test = parsed.hostname in ('127.0.0.1', 'localhost', '::1') and database.startswith(('organiza_test_', 'test_'))
    if not is_test and not approved_real:
        raise RuntimeError('Restauração fora de banco local de teste exige aprovação final e --approved-real-restore.')
    identity = identity or os.getenv('AGE_IDENTITY_FILE')
    if not identity or not Path(identity).is_file():
        raise RuntimeError('Defina AGE_IDENTITY_FILE com a chave privada protegida fora do Git.')
    manifest_path = encrypted.with_name(encrypted.name + '.json')
    if not manifest_path.is_file():
        raise RuntimeError('Manifesto de integridade do backup não encontrado.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('encrypted_sha256') != sha(encrypted):
        raise RuntimeError('A integridade do arquivo cifrado falhou; nenhuma restauração executada.')
    empty_database(url)
    with private_temporary('organiza-pg-restore-') as directory:
        dump = directory / 'database.dump'
        with dump.open('xb') as plain:
            run_command([binary('age'), '--decrypt', '--identity', str(Path(identity).resolve()), str(encrypted)], output=plain)
        dump.chmod(0o600)
        with dump.open('rb') as probe:
            valid_dump = probe.read(5) == b'PGDMP'
        if not valid_dump:
            raise RuntimeError('O conteúdo decifrado não é um dump PostgreSQL válido.')
        run_command([binary('pg_restore'), '--list', str(dump)])
        # One transaction: failure leaves no partial schema/data in the target.
        with libpq_environment(url) as env:
            run_command([binary('pg_restore'), '--exit-on-error', '--single-transaction', '--no-owner',
                         '--no-acl', '--no-password', '--dbname', database, str(dump)], env=env)
    return {'result': 'restored_into_empty_database', 'encrypted_integrity_verified': True,
            'single_transaction': True, 'credential_in_arguments': False, 'source_preserved': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup', 'restore'])
    parser.add_argument('--env-file')
    parser.add_argument('--output')
    parser.add_argument('--source')
    parser.add_argument('--confirm-empty-target', action='store_true')
    parser.add_argument('--approved-real-restore', action='store_true')
    args = parser.parse_args()
    try:
        load_env_file(args.env_file)
        if args.operation == 'backup':
            if not args.output:
                raise RuntimeError('Informe --output com nome novo terminado em .age.')
            result = backup(args.output)
        else:
            if not args.source:
                raise RuntimeError('Informe --source com backup .age existente.')
            result = restore(args.source, confirm_empty=args.confirm_empty_target, approved_real=args.approved_real_restore)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as error:
        print(json.dumps({'error': management_error(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
