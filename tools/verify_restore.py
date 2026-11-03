"""Exercise a real backup and restored app in separate processes, fictitious data only."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    run_dir = ROOT / 'test-results' / ('restore-' + uuid.uuid4().hex)
    run_dir.mkdir(parents=True)
    original = run_dir / 'original.sqlite3'
    env = dict(os.environ, APP_DB_PATH=str(original), APP_ALLOWED_HOSTS='testserver,localhost,127.0.0.1', DJANGO_SETTINGS_MODULE='config.settings')
    prepared = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--prepare'], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    expected = json.loads(prepared.stdout)
    from tools.backup import copy_database, verify
    backup = run_dir / 'backup.sqlite3'
    restored = run_dir / 'restored.sqlite3'
    counts = copy_database(original, backup)
    copy_database(backup, restored)
    env['APP_DB_PATH'] = str(restored)
    restored_check = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--read', expected['state']['space']['id']], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    actual = json.loads(restored_check.stdout)
    assert actual == expected, (actual, expected)
    try:
        copy_database(backup, restored)
    except ValueError:
        overwrite_refused = True
    else:
        raise AssertionError('Restore overwrote an existing file')
    state = actual['state']
    result = {
        'backup_integrity': verify(backup),
        'restored_integrity': verify(restored),
        'separate_process_login_and_balance': actual == expected,
        'complete_financial_snapshot_equal': actual == expected,
        'restored_reader_access': actual['reader_access'],
        'projection_months_compared': len(state['projection']),
        'financial_rows_compared': {key: len(state[key]) for key in (
            'accounts', 'cards', 'entries', 'obligations', 'payments', 'ledger',
            'recurrences', 'budgets', 'audit', 'members',
        )},
        'balance_cents': state['balance_cents'],
        'debt_cents': state['debt_cents'],
        'overwrite_refused': overwrite_refused,
        'fictitious_data_only': True,
    }
    evidence = ROOT / 'test-results' / 'restore-evidence.json'
    evidence.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

def child():
    sys.path.insert(0, str(ROOT))
    import django
    django.setup()
    from django.core.management import call_command
    from django.test import Client
    from django.utils import timezone
    from finance.domain import add_months
    from io import StringIO
    client = Client()
    def post(url, data):
        response = client.post(url, data=json.dumps(data), content_type='application/json')
        assert response.status_code in (200,201), response.content
        return response.json()
    if '--prepare' in sys.argv:
        call_command('migrate', verbosity=0, stdout=StringIO())
        post('/api/auth/register', {'username': 'restore_fictitious', 'display_name': 'Teste fictício', 'password': 'Restore-example-only-93642!'})
        space = post('/api/spaces', {'name': 'Ensaio de restauração'})['space']['id']
        reader = Client()
        response = reader.post('/api/auth/register', data=json.dumps({
            'username': 'restore_reader', 'display_name': 'Leitor fictício',
            'password': 'Restore-reader-only-45921!',
        }), content_type='application/json')
        assert response.status_code == 201, response.content
        post(f'/api/spaces/{space}/members', {'username': 'restore_reader', 'role': 'reader'})
        revision = 0
        today = timezone.localdate()

        def action(name, data):
            nonlocal revision
            saved = post(f'/api/spaces/{space}/actions', {
                'action': name, 'data': data, 'expected_revision': revision,
                'request_id': str(uuid.uuid4()),
            })
            revision = saved['revision']
            return saved

        account = action('account.create', {
            'name': 'Conta fictícia', 'opening_balance_cents': 123456,
            'reference_date': today.isoformat(),
        })['result']['id']
        wallet = action('account.create', {'name': 'Carteira fictícia'})['result']['id']
        card_result = action('card.create', {
            'name': 'Cartão fictício', 'account_id': account, 'closing_day': 10,
            'due_day': 20, 'limit_cents': 500000, 'last_four': '1234',
        })
        card = card_result['result']['id']
        category = next(row['id'] for row in card_result['state']['categories'] if row['name'] == 'Alimentação')
        action('entry.create', {
            'kind': 'income', 'description': 'Receita Pix fictícia', 'method': 'pix',
            'amount_cents': 50000, 'account_id': account, 'paid': True,
            'paid_on': today.isoformat(),
        })
        action('entry.create', {
            'kind': 'expense', 'description': 'Refeição fictícia', 'merchant': 'Local fictício',
            'method': 'pix', 'amount_cents': 10000, 'account_id': account,
            'category_id': category, 'paid': True, 'paid_on': today.isoformat(),
        })
        purchase = action('entry.create', {
            'kind': 'expense', 'description': 'Compra parcelada fictícia', 'method': 'credit',
            'amount_cents': 100000, 'card_id': card, 'category_id': category,
            'installments': 3, 'due_date': today.isoformat(),
        })
        obligation = next(row for row in purchase['state']['obligations'] if row['entry_id'] == purchase['result']['id'])
        action('invoice.pay', {
            'invoice_id': obligation['invoice_id'], 'account_id': account,
            'amount_cents': 10000, 'paid_on': today.isoformat(),
        })
        action('entry.create', {
            'kind': 'transfer', 'description': 'Transferência fictícia', 'method': 'pix',
            'amount_cents': 5000, 'account_id': account, 'destination_account_id': wallet,
            'paid_on': today.isoformat(),
        })
        action('budget.set', {'category_id': category, 'month': today.strftime('%Y-%m'), 'amount_cents': 200000})
        action('entry.create', {
            'kind': 'expense', 'description': 'Recorrência fictícia', 'method': 'pix',
            'amount_cents': 2000, 'account_id': account, 'category_id': category,
            'due_date': today.isoformat(),
            'recurrence': {'frequency': 'monthly', 'end_date': add_months(today, 3).isoformat()},
        })
    else:
        space = sys.argv[-1]
        post('/api/auth/login', {'username': 'restore_fictitious', 'password': 'Restore-example-only-93642!'})
    state_response = client.get(f'/api/spaces/{space}/state')
    assert state_response.status_code == 200, state_response.content
    state = state_response.json()
    if '--prepare' not in sys.argv:
        reader = Client()
        response = reader.post('/api/auth/login', data=json.dumps({
            'username': 'restore_reader', 'password': 'Restore-reader-only-45921!',
        }), content_type='application/json')
        assert response.status_code == 200, response.content
    reader_response = reader.get(f'/api/spaces/{space}/state')
    assert reader_response.status_code == 200, reader_response.content
    reader_state = reader_response.json()
    assert reader_state['space']['role'] == 'reader'
    for key in ('accounts', 'cards', 'entries', 'obligations', 'payments', 'ledger', 'projection', 'audit'):
        assert reader_state[key] == state[key], key
    print(json.dumps({'state': state, 'reader_access': True}))

if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    if '--prepare' in sys.argv or '--read' in sys.argv:
        child()
    else:
        main()
