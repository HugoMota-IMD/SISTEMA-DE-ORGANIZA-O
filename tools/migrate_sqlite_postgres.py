"""Atomic SQLite-to-PostgreSQL import into an empty, migrated destination.

The default accepts only fictitious files under test-results. Real-data import
requires explicit approved cutover flags and a frozen consistent source copy.
No connection string or business row is printed. Schema migrations run separately.
"""
import argparse
from contextlib import closing
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.postgres_common import load_env_file, management_error, prepare_django

RECEIPT_TABLE = 'organiza_import_receipt'
STANDARD = ['auth_group', 'auth_user', 'auth_group_permissions', 'auth_user_groups',
            'auth_user_user_permissions', 'django_session', 'finance_loginattempt',
            'finance_workspace', 'finance_membership', 'finance_financialstate',
            'finance_operation', 'finance_auditevent']


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def digest(value):
    return hashlib.sha256(stable(value).encode()).hexdigest()


def sqlite_source(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or path.suffix != '.sqlite3':
        raise RuntimeError('Use uma cópia SQLite existente dentro da raiz exclusiva.')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('BEGIN')
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or source.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('A origem falhou na integridade SQLite; nada foi importado.')
        names = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'auth_user', 'finance_workspace', 'finance_financialstate'} <= names:
            raise RuntimeError('A origem não contém a estrutura esperada do Organiza.')
        selected = sorted(name for name in names if name.startswith(('auth_', 'finance_')) or name in ('django_session', 'django_content_type'))
        data = {name: sorted([dict(row) for row in source.execute('SELECT * FROM "' + name.replace('"', '""') + '"')], key=stable) for name in selected}
    return data


def columns(cursor, table):
    cursor.execute('SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position', [table])
    return {name: (kind, udt) for name, kind, udt in cursor.fetchall()}


def conversion(value, kind):
    if value is None:
        return None
    data_type, udt = kind
    if data_type in ('json', 'jsonb'):
        from psycopg.types.json import Jsonb
        return Jsonb(json.loads(value) if isinstance(value, str) else value)
    if udt == 'uuid':
        return uuid.UUID(str(value))
    if data_type == 'boolean':
        return bool(value)
    if data_type.startswith('timestamp'):
        result = datetime.fromisoformat(str(value)) if not isinstance(value, datetime) else value
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    return value


def canonical(value, kind):
    if value is None:
        return None
    data_type, udt = kind
    if data_type in ('json', 'jsonb'):
        return json.loads(value) if isinstance(value, str) else value
    if udt == 'uuid':
        return str(uuid.UUID(str(value)))
    if data_type == 'boolean':
        return bool(value)
    if data_type.startswith('timestamp'):
        result = datetime.fromisoformat(str(value)) if not isinstance(value, datetime) else value
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc).isoformat()
    return value


def quote(value):
    from psycopg import sql
    return sql.Identifier(value)


def execute_insert(cursor, table, row, schema):
    from psycopg import sql
    fields = list(row)
    if set(fields) - set(schema):
        raise RuntimeError('O esquema do destino não é compatível com a origem; aplique e confira as migrações antes da importação.')
    cursor.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(quote(table), sql.SQL(',').join(map(quote, fields)), sql.SQL(',').join(sql.Placeholder() for _ in fields)),
                   [conversion(row[key], schema[key]) for key in fields])


def reference_maps(data):
    content = {row['id']: (row['app_label'], row['model']) for row in data.get('django_content_type', [])}
    permissions = {row['id']: (*content[row['content_type_id']], row['codename']) for row in data.get('auth_permission', [])}
    return content, permissions


def import_metadata(cursor, data):
    content_map, permission_map = {}, {}
    for row in data.get('django_content_type', []):
        cursor.execute('SELECT id FROM django_content_type WHERE app_label=%s AND model=%s', [row['app_label'], row['model']])
        existing = cursor.fetchone()
        if existing:
            content_map[row['id']] = existing[0]
        else:
            cursor.execute('INSERT INTO django_content_type(app_label,model) VALUES(%s,%s) RETURNING id', [row['app_label'], row['model']])
            content_map[row['id']] = cursor.fetchone()[0]
    for row in data.get('auth_permission', []):
        content_id = content_map[row['content_type_id']]
        cursor.execute('SELECT id FROM auth_permission WHERE content_type_id=%s AND codename=%s', [content_id, row['codename']])
        existing = cursor.fetchone()
        if existing:
            permission_map[row['id']] = existing[0]
        else:
            cursor.execute('INSERT INTO auth_permission(name,content_type_id,codename) VALUES(%s,%s,%s) RETURNING id', [row['name'], content_id, row['codename']])
            permission_map[row['id']] = cursor.fetchone()[0]
    return permission_map


def canonical_tables(data, schemas):
    _, permissions = reference_maps(data)
    tables = {}
    for name, schema in schemas.items():
        rows = []
        for row in data.get(name, []):
            normalized = {key: canonical(value, schema[key]) for key, value in row.items()}
            if name in ('auth_group_permissions', 'auth_user_user_permissions'):
                normalized['permission_id'] = permissions[row['permission_id']]
            rows.append(normalized)
        tables[name] = sorted(rows, key=stable)
    return tables


def destination_data(cursor, schemas):
    from psycopg import sql
    result = {}
    for name, schema in schemas.items():
        cursor.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(map(quote, schema)), quote(name)))
        result[name] = [dict(zip(schema, row)) for row in cursor.fetchall()]
    for name in ('django_content_type', 'auth_permission'):
        cursor.execute(sql.SQL('SELECT * FROM {}').format(quote(name)))
        names = [column[0] for column in cursor.description]
        result[name] = [dict(zip(names, row)) for row in cursor.fetchall()]
    return result


def financial_summary(tables, as_of):
    from finance.domain import snapshot
    documents = []
    for row in tables.get('finance_financialstate', []):
        document = row['document']
        document = json.loads(document) if isinstance(document, str) else document
        documents.append({'workspace': str(uuid.UUID(str(row['workspace_id']))), 'revision': row['revision'],
                          'snapshot': snapshot(deepcopy(document), as_of=as_of, months=60)})
    return digest(sorted(documents, key=lambda item: item['workspace']))


def reset_sequences(cursor, tables):
    from psycopg import sql
    for table in tables:
        for column in columns(cursor, table):
            cursor.execute('SELECT pg_get_serial_sequence(%s,%s)', [table, column])
            sequence = cursor.fetchone()[0]
            if sequence:
                cursor.execute(sql.SQL('SELECT MAX({}) FROM {}').format(quote(column), quote(table)))
                maximum = cursor.fetchone()[0]
                cursor.execute('SELECT setval(%s::regclass,%s,%s)', [sequence, maximum or 1, maximum is not None])


def migrate(path, *, as_of=None, after_table=None):
    """Import atomically. Caller must have approved the source and destination."""
    source = sqlite_source(path)
    fingerprint = digest(source)
    connection = prepare_django()
    from finance.security import import_context
    from psycopg import sql
    from django.utils import timezone as django_timezone
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of or django_timezone.localdate()
    with import_context(using='default'):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('organiza-sqlite-import'))")
            cursor.execute(f'CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE} (source_digest varchar(64) PRIMARY KEY, imported_at timestamptz NOT NULL DEFAULT now(), reconciliation jsonb NOT NULL)')
            cursor.execute(f'SELECT source_digest,reconciliation FROM {RECEIPT_TABLE}')
            receipts = cursor.fetchall()
            if receipts:
                if len(receipts) != 1 or receipts[0][0] != fingerprint:
                    raise RuntimeError('O destino já recebeu outra origem; nada foi sobrescrito.')
                return {'result': 'already_imported', 'source_digest': fingerprint, 'duplicate_prevented': True}
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND (table_name LIKE 'finance_%%' OR table_name LIKE 'auth_%%' OR table_name='django_session')")
            business = sorted(row[0] for row in cursor.fetchall() if row[0] != 'auth_permission')
            schemas = {}
            for table in business:
                cursor.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(quote(table)))
                if cursor.fetchone()[0]:
                    raise RuntimeError('O destino contém usuários ou dados. A importação exige um banco migrado e vazio; nada foi sobrescrito.')
                target_schema = columns(cursor, table)
                # Missing new tables in an older source represent zero rows.
                source_fields = set(source[table][0]) if source.get(table) else set(target_schema)
                if not source_fields <= set(target_schema):
                    raise RuntimeError('Esquema de origem incompatível; nada foi importado.')
                schemas[table] = {key: value for key, value in target_schema.items() if key in source_fields}
            permission_map = import_metadata(cursor, source)
            ordered = [name for name in STANDARD if name in business] + [name for name in business if name not in STANDARD]
            for table in ordered:
                for row in source.get(table, []):
                    row = dict(row)
                    if table in ('auth_group_permissions', 'auth_user_user_permissions'):
                        row['permission_id'] = permission_map[row['permission_id']]
                    execute_insert(cursor, table, row, schemas[table])
                if after_table:
                    after_table(table)
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            actual = destination_data(cursor, schemas)
            expected_tables = canonical_tables(source, schemas)
            actual_tables = canonical_tables(actual, schemas)
            if expected_tables != actual_tables:
                raise RuntimeError('A reconciliação dos registros falhou; a transação foi revertida.')
            financial_equal = financial_summary(source, as_of) == financial_summary(actual, as_of)
            if not financial_equal:
                raise RuntimeError('A reconciliação financeira/projeção falhou; a transação foi revertida.')
            reset_sequences(cursor, [*business, 'django_content_type', 'auth_permission'])
            report = {'result': 'imported', 'source_digest': fingerprint,
                      'model_counts': {name: len(rows) for name, rows in expected_tables.items()},
                      'records_equal': True, 'password_hashes_preserved': True, 'references_valid': True,
                      'financial_snapshots_and_60_month_projection_equal': True,
                      'sequences_reset': True, 'as_of': as_of.isoformat()}
            from psycopg.types.json import Jsonb
            cursor.execute(f'INSERT INTO {RECEIPT_TABLE}(source_digest,reconciliation) VALUES(%s,%s)', [fingerprint, Jsonb(report)])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--env-file')
    parser.add_argument('--as-of')
    parser.add_argument('--source-frozen', action='store_true', help='Confirma cópia consistente sem gravações durante o corte.')
    parser.add_argument('--approved-real-import', action='store_true', help='Somente após aprovação final do conjunto e corte autorizado.')
    args = parser.parse_args()
    try:
        load_env_file(args.env_file)
        path = Path(args.source).resolve()
        if not args.source_frozen:
            raise RuntimeError('Confirme a cópia consistente com --source-frozen; nunca importe uma base oficial recebendo gravações.')
        if not args.approved_real_import:
            marker = path.parent / 'fictitious-source-marker.json'
            try:
                definition = json.loads(marker.read_text(encoding='utf-8'))
                fictitious = (path.is_relative_to(ROOT / 'test-results')
                              and definition.get('kind') == 'organiza-fictitious-rehearsal'
                              and definition.get('source') == path.name
                              and definition.get('sha256') == hashlib.sha256(path.read_bytes()).hexdigest())
            except (OSError, ValueError):
                fictitious = False
            if not fictitious:
                raise RuntimeError('Importação real exige aprovação final e --approved-real-import. O padrão aceita somente fixture marcada pelo ensaio fictício.')
        print(json.dumps(migrate(path, as_of=args.as_of), ensure_ascii=True))
        return 0
    except Exception as error:
        print(json.dumps({'error': management_error(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
