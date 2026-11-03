"""Real-browser installment acceptance using only an isolated fictitious database.

Run with the project Python after installing requirements-dev.txt and Chromium in
.browser-cache. No production database, account or financial entry is read.
"""

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.browser-cache')
from playwright.sync_api import expect, sync_playwright

BASE = 'http://127.0.0.1:8767'
PASSWORD = 'Fictitious-browser-acceptance-34782!'


def request(page, path, payload=None):
    """Use the browser's real session and CSRF token, never bypass permissions."""
    return page.evaluate("""async ({path,payload}) => {
        const session = await (await fetch('/api/session')).json();
        const response = await fetch(path, {
            method: payload === null ? 'GET' : 'POST',
            headers: {'Content-Type':'application/json','X-CSRFToken':session.csrf_token},
            ...(payload === null ? {} : {body:JSON.stringify(payload)})
        });
        return {status:response.status,body:await response.json()};
    }""", {'path': path, 'payload': payload})


def current(page, space, start=None):
    suffix = '?months=60' + ('&start=' + start if start else '')
    result = request(page, f'/api/spaces/{space}/state{suffix}')
    assert result['status'] == 200, result
    return result['body']


def action(page, space, name, data, *, expected=200):
    before = current(page, space)
    payload = {'action': name, 'data': data, 'request_id': str(uuid.uuid4()),
               'expected_revision': before['revision']}
    result = request(page, f'/api/spaces/{space}/actions', payload)
    assert result['status'] == expected, result
    return result


def register(browser, username, *, mobile=False):
    context = browser.new_context(
        viewport={'width': 390 if mobile else 1440, 'height': 844 if mobile else 1000},
        locale='pt-BR', is_mobile=mobile, has_touch=mobile)
    page = context.new_page()
    page.goto(BASE)
    result = request(page, '/api/auth/register', {
        'username': username, 'display_name': 'Pessoa fictícia ' + username,
        'password': PASSWORD})
    assert result['status'] == 201, result
    return context, page


def navigate(page, name):
    item = page.locator(f'.nav-item[data-page="{name}"]')
    bounds = item.bounding_box()
    if not item.is_visible() or (bounds and bounds['x'] < 0):
        page.locator('[data-action="menu"]').click()
    item.click()


def field(page, name, value):
    page.locator(f'#dialog-form [name="{name}"]').fill(str(value))


def choose(page, name, value):
    page.locator(f'#dialog-form select[name="{name}"]').select_option(value=str(value))


def begin(page, description, modality, *, card=None):
    navigate(page, 'debts')
    page.locator('[data-action="installment-entry"]').first.click()
    expect(page.locator('#dialog-form')).to_be_visible()
    field(page, 'description', description)
    choose(page, 'modality', modality)
    if card is not None:
        choose(page, 'card_id', card)
    page.locator('#installment-next').click()
    expect(page.locator('#f-amount_cents')).to_be_visible()


def preview(page, amount, count, due, *, paid=0, mode='total', credit=False):
    choose(page, 'value_mode', mode)
    field(page, 'amount_cents', amount)
    field(page, 'installments', count)
    field(page, 'paid_installments', paid)
    field(page, 'first_invoice_month' if credit else 'due_date', due)
    page.locator('#installment-next').click()
    expect(page.locator('#installment-schedule tbody tr')).to_have_count(count)
    expect(page.locator('#installment-confirm')).to_be_visible()


def confirm(page):
    page.locator('#installment-confirm').click()
    try:
        expect(page.locator('#modal')).not_to_be_visible(timeout=15000)
    except Exception:
        raise AssertionError('Installment save failed: ' + page.locator('#form-error').inner_text())


def entry_with(state, description):
    entries = [item for item in state['entries'] if item['description'] == description]
    assert len(entries) == 1, (description, len(entries))
    entry = entries[0]
    parts = sorted((item for item in state['obligations'] if item['entry_id'] == entry['id']),
                   key=lambda item: item['installment'])
    return entry, parts


def assert_no_cash(before, after):
    for name in ('ledger', 'payments'):
        assert after[name] == before[name], f'Historical installment changed {name}'
    assert after['balance_cents'] == before['balance_cents'], 'Creation changed cash balance'


def main():
    results = ROOT / 'test-results'
    results.mkdir(exist_ok=True)
    run_id = uuid.uuid4().hex
    test_database = results / f'installments-{run_id}.sqlite3'
    env = dict(os.environ, APP_DB_PATH=str(test_database), APP_PORT='8767',
               APP_SECRET_KEY=secrets.token_urlsafe(48), APP_LOCAL_MODE='true')
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    server_log = (results / f'installments-server-{run_id}.log').open('w', encoding='utf-8')
    server = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env,
                              stdout=server_log, stderr=server_log,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    errors = []
    checks = []
    page = None
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(BASE + '/api/session', timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('The isolated acceptance server did not start.')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                admin_context, page = register(browser, 'installment_admin')
                page.on('pageerror', lambda error: errors.append(str(error)))
                created = request(page, '/api/spaces', {'name': 'Parcelas fictícias QA'})
                assert created['status'] == 201, created
                space = created['body']['space']['id']
                action(page, space, 'account.create', {
                    'name': 'Conta fictícia QA', 'opening_balance_cents': 500000,
                    'reference_date': '2020-01-01'})
                account = current(page, space)['accounts'][0]['id']
                action(page, space, 'card.create', {
                    'name': 'Cartão fictício QA', 'account_id': account,
                    'closing_day': 20, 'due_day': 31, 'limit_cents': 2000000})
                card = current(page, space)['cards'][0]['id']
                page.reload()
                expect(page.locator('.summary-grid')).to_be_visible()

                # Outside a card, no credit-card field or historic cash movement is required.
                before = current(page, space)
                begin(page, 'Fora do cartão fictícia 1000 em 3', 'outside')
                preview(page, 'R$ 1.000,00', 3, '2028-01-31')
                text = page.locator('#installment-preview').inner_text()
                assert '333,34' in text and '333,33' in text and '1.000,00' in text, text
                assert '31/01/2028' in text and '29/02/2028' in text and '31/03/2028' in text, text
                assert current(page, space) == before, 'Preview persisted financial data'
                page.screenshot(path=str(results / 'installments-outside-desktop.png'), full_page=True)
                confirm(page)
                after = current(page, space)
                entry, parts = entry_with(after, 'Fora do cartão fictícia 1000 em 3')
                assert entry['amount_cents'] == 100000
                assert [part['amount_cents'] for part in parts] == [33334, 33333, 33333]
                assert [part['due_date'] for part in parts] == ['2028-01-31', '2028-02-29', '2028-03-31']
                assert all(not part.get('card_id') and not part.get('invoice_id') for part in parts)
                assert all(part['status'] == 'pending' for part in parts)
                assert_no_cash(before, after)
                checks.append('outside_brazilian_currency_exact_1000_split_preview_no_cash')

                # A past debt with previous payments is an opening debt, not new expenses in cash.
                before = after
                begin(page, 'Dívida anterior fictícia', 'outside')
                preview(page, '100,50', 4, '2025-01-30', paid=2, mode='installment')
                text = page.locator('#installment-preview').inner_text()
                assert '402,00' in text and '201,00' in text, text
                confirm(page)
                after = current(page, space)
                entry, parts = entry_with(after, 'Dívida anterior fictícia')
                assert entry['amount_cents'] == 40200 and entry['debt_cents'] == 20100
                assert entry['paid_installments'] == 2 and entry['remaining_installments'] == 2
                assert [part['due_date'] for part in parts] == ['2025-01-30','2025-02-28','2025-03-30','2025-04-30']
                assert [part['status'] for part in parts] == ['paid','paid','overdue','overdue']
                assert_no_cash(before, after)
                checks.append('per_installment_mode_prior_paid_exact_balance_no_historic_cash')

                # Browser validation must preserve entered content and point at the invalid field.
                begin(page, 'Validação fictícia preservada', 'outside')
                field(page, 'amount_cents', '1.000,00')
                field(page, 'installments', '3')
                field(page, 'paid_installments', '4')
                page.locator('#installment-next').click()
                expect(page.locator('#f-paid_installments')).to_have_attribute('aria-invalid', 'true')
                expect(page.locator('#f-amount_cents')).to_have_value('1.000,00')
                expect(page.locator('#f-paid_installments')).to_have_value('4')
                assert page.locator('#modal').is_visible()
                assert current(page, space) == after, 'Invalid fields changed persisted data'
                page.screenshot(path=str(results / 'installments-validation-desktop.png'), full_page=True)
                page.locator('[data-action="close-modal"]').first.click()
                checks.append('invalid_paid_count_inline_message_and_preserved_values')

                # Installment preview and final entry must agree on card, invoice and integer cents.
                before = current(page, space)
                begin(page, 'Cartão fictícia 1000 em 3', 'credit', card=card)
                preview(page, '1.000,00', 3, '2028-01', credit=True)
                text = page.locator('#installment-preview').inner_text()
                assert 'Cartão fictício QA' in text and '333,34' in text, text
                page.screenshot(path=str(results / 'installments-card-desktop.png'), full_page=True)
                saved_requests = []
                def remember(request_item):
                    if request_item.method == 'POST' and request_item.url.endswith('/actions'):
                        payload = request_item.post_data_json
                        if payload.get('action') == 'entry.create':
                            saved_requests.append(payload)
                page.on('request', remember)
                # Dispatch two submits before a response; the UI must disable the second one.
                page.locator('#installment-confirm').evaluate("button => {button.click();button.click();}")
                expect(page.locator('#modal')).not_to_be_visible(timeout=15000)
                page.remove_listener('request', remember)
                assert len(saved_requests) == 1, f'Double click sent {len(saved_requests)} operations'
                after = current(page, space)
                entry, parts = entry_with(after, 'Cartão fictícia 1000 em 3')
                assert entry['amount_cents'] == 100000 and entry['card_id'] == card
                assert sum(part['amount_cents'] for part in parts) == 100000
                assert all(part['card_id'] == card and part['invoice_id'] for part in parts)
                invoices = [item for item in after['invoices'] if item['card_id'] == card]
                assert sum(item['remaining_cents'] for item in invoices) == 100000
                assert after['debt_cents'] - before['debt_cents'] == 100000, 'Card invoice duplicated debt'
                assert_no_cash(before, after)
                duplicate = request(page, f'/api/spaces/{space}/actions', saved_requests[0])
                assert duplicate['status'] == 200 and duplicate['body'].get('duplicate') is True, duplicate
                assert current(page, space) == after, 'Replayed request duplicated the purchase'
                checks.append('card_invoice_debt_and_double_click_request_replay')

                # Drop a successful save response: a retry must reuse the key and find one purchase.
                begin(page, 'Resposta perdida fictícia', 'outside')
                preview(page, '600,00', 3, '2028-04-30')
                lost_responses = []
                def lose_first_response(route):
                    payload = route.request.post_data_json
                    if payload.get('action') == 'entry.create':
                        lost_responses.append(payload)
                        if len(lost_responses) == 1:
                            response = route.fetch()
                            assert response.status == 200, 'The controlled save did not commit'
                            route.abort('failed')
                            return
                    route.continue_()
                page.route('**/api/spaces/*/actions', lose_first_response)
                page.locator('#installment-confirm').click()
                expect(page.locator('#form-error')).not_to_have_text('')
                expect(page.locator('#installment-confirm')).to_be_enabled()
                expect(page.locator('#installment-schedule tbody tr')).to_have_count(3)
                committed = current(page, space)
                entry_with(committed, 'Resposta perdida fictícia')
                confirm(page)
                page.unroute('**/api/spaces/*/actions', lose_first_response)
                assert len(lost_responses) == 2 and lost_responses[0] == lost_responses[1], 'Retry changed immutable request'
                assert current(page, space) == committed, 'Retry duplicated or changed the purchase'
                checks.append('lost_save_response_retry_preserves_form_and_request_id')

                # A concurrent edit invalidates the displayed schedule; preserve fields and re-preview.
                begin(page, 'Revisão concorrente fictícia', 'outside')
                preview(page, '321,00', 3, '2028-07-31')
                independent = browser.new_context(viewport={'width':1440,'height':1000}, locale='pt-BR')
                concurrent_page = independent.new_page()
                concurrent_page.goto(BASE)
                logged_in = request(concurrent_page, '/api/auth/login', {
                    'username':'installment_admin','password':PASSWORD})
                assert logged_in['status'] == 200, logged_in
                action(concurrent_page, space, 'account.update', {
                    'account_id':account,'name':'Conta fictícia QA atualizada'})
                concurrent_state = current(concurrent_page, space)
                page.locator('#installment-confirm').click()
                expect(page.locator('#f-amount_cents')).to_be_visible()
                expect(page.locator('#f-amount_cents')).to_have_value('321,00')
                expect(page.locator('#f-installments')).to_have_value('3')
                expect(page.locator('#form-error')).not_to_have_text('')
                assert current(page, space) == concurrent_state, 'Stale preview saved an entry'
                assert not any(item['description'] == 'Revisão concorrente fictícia'
                               for item in concurrent_state['entries'])
                page.locator('#installment-next').click()
                expect(page.locator('#installment-schedule tbody tr')).to_have_count(3)
                confirm(page)
                entry, parts = entry_with(current(page, space), 'Revisão concorrente fictícia')
                assert sum(item['amount_cents'] for item in parts) == 32100
                independent.close()
                checks.append('concurrent_revision_409_preserves_fields_and_requires_fresh_preview')

                # Due-date anchors survive February and use the original day in March.
                for day in (29, 30):
                    begin(page, f'Âncora fictícia dia {day}', 'outside')
                    preview(page, '300,00', 3, f'2027-01-{day}')
                    text = page.locator('#installment-preview').inner_text()
                    assert '28/02/2027' in text and f'{day}/03/2027' in text, text
                    confirm(page)
                    _, parts = entry_with(current(page, space), f'Âncora fictícia dia {day}')
                    assert [part['due_date'] for part in parts] == [f'2027-01-{day}', '2027-02-28', f'2027-03-{day}']
                checks.append('month_end_29_30_31_and_february_anchor')

                # Independent participants exercise authorization in their own browser cookies.
                collaborator_context, collaborator = register(browser, 'installment_collaborator', mobile=True)
                reader_context, reader = register(browser, 'installment_reader', mobile=True)
                for username, role in [('installment_collaborator','collaborator'),('installment_reader','reader')]:
                    result = request(page, f'/api/spaces/{space}/members', {'username':username,'role':role})
                    assert result['status'] == 200, result
                collaborator.reload()
                expect(collaborator.locator('.summary-grid')).to_be_visible()
                collaborator.on('pageerror', lambda error: errors.append(str(error)))
                before = current(collaborator, space)
                begin(collaborator, 'Colaborador celular fictícia', 'outside')
                preview(collaborator, '150,25', 2, '2028-01-31', mode='installment')
                assert collaborator.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page overflow'
                assert collaborator.locator('#modal').evaluate('el => el.scrollWidth <= el.clientWidth'), 'Mobile dialog overflow'
                collaborator.screenshot(path=str(results / 'installments-preview-mobile.png'), full_page=True)
                confirm(collaborator)
                after = current(collaborator, space)
                entry, parts = entry_with(after, 'Colaborador celular fictícia')
                assert entry['amount_cents'] == 30050 and entry['created_by'] != after['members'][0]['user_id']
                assert_no_cash(before, after)
                before = after
                begin(collaborator, 'Cartão celular fictícia', 'credit', card=card)
                preview(collaborator, '240,00', 2, '2029-01', credit=True)
                assert 'Cartão fictício QA' in collaborator.locator('#installment-preview').inner_text()
                collaborator.screenshot(path=str(results / 'installments-card-mobile.png'), full_page=True)
                confirm(collaborator)
                after = current(collaborator, space)
                entry, parts = entry_with(after, 'Cartão celular fictícia')
                assert entry['card_id'] == card and entry['debt_cents'] == 24000
                assert sum(part['remaining_cents'] for part in parts) == 24000
                assert_no_cash(before, after)
                reader.reload()
                expect(reader.locator('.summary-grid')).to_be_visible()
                navigate(reader, 'debts')
                expect(reader.locator('[data-action="installment-entry"]')).to_have_count(0)
                forbidden = request(reader, f'/api/spaces/{space}/actions', saved_requests[0])
                assert forbidden['status'] == 403 and 'consultar' in forbidden['body']['error'], forbidden
                readonly_state = current(reader, space)
                assert readonly_state['space']['role'] == 'reader'
                assert {key:value for key,value in readonly_state.items() if key != 'space'} == {
                    key:value for key,value in after.items() if key != 'space'}, 'Reader write changed financial data'
                reader.screenshot(path=str(results / 'installments-reader-mobile.png'), full_page=True)
                checks.append('administrator_collaborator_mobile_and_reader_server_permission')

                # Projection represents each pending obligation once, including overdue pending debt.
                snap = current(page, space, '2028-01')
                future_parts = [item for item in snap['obligations'] if item['due_date'] >= '2028-01-01']
                projected = sum(row['commitment_cents'] for row in snap['projection'])
                assert projected == sum(item['remaining_cents'] for item in future_parts), 'Projection duplicated or lost future installments'
                checks.append('projection_and_persisted_debt_consistent')
                assert not errors, errors
                evidence = {
                    'checks': checks, 'checks_passed': len(checks),
                    'desktop_viewport': '1440x1000', 'mobile_viewport': '390x844',
                    'separate_sessions': ['admin','collaborator','reader'],
                    'fictitious_database': test_database.name,
                    'fictitious_data_only': True, 'production_database_accessed': False,
                    'physical_devices_tested': False, 'page_errors': errors,
                }
                (results / 'installments-ui-evidence.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
                print(json.dumps(evidence, indent=2, ensure_ascii=False))
            except Exception:
                if page is not None:
                    page.screenshot(path=str(results / 'installments-failure.png'), full_page=True)
                    (results / 'installments-failure.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        server_log.close()


if __name__ == '__main__':
    main()
