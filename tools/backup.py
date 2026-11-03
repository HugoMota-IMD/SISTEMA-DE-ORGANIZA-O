"""Consistent SQLite backup and non-destructive restore, confined to this project."""
import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def inside(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    if not path.is_relative_to(ROOT) or path.suffix != '.sqlite3':
        raise ValueError('Use arquivo .sqlite3 dentro da raiz exclusiva deste projeto.')
    return path

def verify(path):
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Falha na integridade SQLite.')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Falha nas referências do banco.')
        counts = {name: connection.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ('auth_user', 'finance_workspace', 'finance_membership', 'finance_financialstate', 'finance_auditevent')}
        for (document,) in connection.execute('SELECT document FROM finance_financialstate'):
            parsed = json.loads(document)
            if not isinstance(parsed, dict) or not all(isinstance(parsed.get(key), list) for key in ('accounts','cards','entries','obligations','ledger')):
                raise ValueError('Documento financeiro inválido no backup.')
        return counts

def copy_database(source, destination):
    source, destination = inside(source), inside(destination)
    if not source.is_file():
        raise ValueError('Banco de origem não encontrado.')
    if destination.exists():
        raise ValueError('O destino já existe. A restauração nunca sobrescreve arquivos.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation makes accidental replacement impossible, including races.
    destination.touch(exist_ok=False)
    try:
        with sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True) as original, sqlite3.connect(destination) as copied:
            original.backup(copied)
        return verify(destination)
    except Exception:
        # This exact file was exclusively created above; never touch the source.
        destination.unlink(missing_ok=True)
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['backup','restore','verify'])
    parser.add_argument('--source', default='data/finance.sqlite3')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.operation == 'verify':
        print(json.dumps(verify(inside(args.source)), ensure_ascii=False))
    elif not args.output:
        parser.error('--output é obrigatório; informe um arquivo novo.')
    else:
        print(json.dumps(copy_database(args.source, args.output), ensure_ascii=False))
