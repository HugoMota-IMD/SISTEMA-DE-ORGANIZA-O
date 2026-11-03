"""Browser regressions for payment confirmation using a disposable fictitious DB.

The real application database is never accessed. Playwright and Chromium use the
same project-local setup as tools/verify_ui.py. Evidence is ignored by Git.
"""

import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.browser-cache')
from playwright.sync_api import expect, sync_playwright
import verify_installments as helpers

BASE = 'http://127.0.0.1:8769'
helpers.BASE = BASE
TODAY = datetime.now(ZoneInfo('America/Manaus')).date().isoformat()
CURRENT_MONTH = TODAY[:7]
request, current, action = helpers.request, helpers.current, helpers.action
field, navigate = helpers.field, helpers.navigate


def by_id(state, collection, object_id):
    return next(item for item in state[collection] if item['id'] == object_id)


def obligations(state, entry_id):
    return sorted((item for item in state['obligations'] if item['entry_id'] == entry_id),
                  key=lambda item: item['installment'])


def create_expense(page, space, description, amount, account, *, installments=1,
                   paid=0, card=None, purchase_date=None, due_date='2020-01-15'):
    payload = {'kind':'expense','description':description,'amount_cents':amount,
               'method':'credit' if card else 'pix','account_id':account,
               'installments':installments,'paid_installments':paid,
               'purchase_date':purchase_date or TODAY,'due_date':due_date}
    if card:
        payload['card_id'] = card
        payload['first_invoice_month'] = CURRENT_MONTH
        payload.pop('due_date')
    result = action(page, space, 'entry.create', payload)
    return result['body']['result']['id']


def detail(page, entry_id):
    navigate(page, 'entries')
    page.locator(f'[data-action="entry-detail"][data-id="{entry_id}"]').first.click()
    expect(page.locator('#modal')).to_be_visible()


def open_payment(page, entry_id, target_id, *, invoice=False, amount=None):
    detail(page, entry_id)
    kind = 'pay-invoice' if invoice else 'pay-obligation'
    page.locator(f'#modal [data-action="{kind}"][data-id="{target_id}"]').first.click()
    expect(page.locator('#payment-confirm')).to_be_enabled(timeout=10000)
    if amount is not None:
        expect(page.locator('#payment-preview')).to_have_attribute('data-amount-cents', str(amount))


def partial(page, amount_text, amount_cents):
    page.locator('#payment-partial').click()
    field(page, 'amount_cents', amount_text)
    expect(page.locator('#payment-preview')).to_have_attribute('data-amount-cents', str(amount_cents))
    expect(page.locator('#payment-confirm')).to_be_enabled(timeout=10000)


def confirm(page):
    page.locator('#payment-confirm').click()
    try:
        expect(page.locator('#modal')).not_to_be_visible(timeout=15000)
    except Exception:
        raise AssertionError('Payment confirmation failed: ' + page.locator('#form-error').inner_text())


def assert_effect(before, after, paid_cents):
    assert after['balance_cents'] == before['balance_cents'] - paid_cents, 'Cash changed by another amount'
    assert after['debt_cents'] == before['debt_cents'] - paid_cents, 'Debt changed by another amount'
    assert {item['id']:item['amount_cents'] for item in after['entries']} == {
        item['id']:item['amount_cents'] for item in before['entries']}, 'Payment changed original purchase totals'
    assert after['reports']['expense_cents'] == before['reports']['expense_cents'], 'Payment duplicated consumption expense'
    added_ledger = after['ledger'][len(before['ledger']):]
    assert sum(item['amount_cents'] for item in added_ledger) == -paid_cents, 'Ledger did not represent the cash effect exactly once'


def assert_summary_amount(page, label, amount):
    row = page.locator('#payment-preview dt').filter(has_text=re.compile('^'+re.escape(label)+'$')).locator('..')
    expect(row.locator('dd')).to_have_text(re.compile(r'R\$\s*'+re.escape(amount)))


def main():
    results = ROOT / 'test-results'
    results.mkdir(exist_ok=True)
    run_id = uuid.uuid4().hex
    database = results / f'payments-{run_id}.sqlite3'
    env = dict(os.environ, APP_DB_PATH=str(database), APP_PORT='8769',
               APP_LOCAL_MODE='true', APP_SECRET_KEY=secrets.token_urlsafe(48))
    subprocess.run([sys.executable,'manage.py','migrate','--noinput'], cwd=ROOT,
                   env=env, check=True, capture_output=True)
    log = (results / f'payments-server-{run_id}.log').open('w', encoding='utf-8')
    server = subprocess.Popen([sys.executable,'serve.py'], cwd=ROOT, env=env,
        stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    page = None
    checks, errors = [], []
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(BASE+'/api/session',timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('The isolated payment server did not start.')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                admin_context, page = helpers.register(browser,'payment_admin')
                page.on('pageerror',lambda error:errors.append(str(error)))
                result = request(page,'/api/spaces',{'name':'Pagamentos fictícios QA'})
                assert result['status'] == 201, result
                space = result['body']['space']['id']
                result = action(page,space,'account.create',{
                    'name':'Conta fictícia de pagamentos','opening_balance_cents':1000000,
                    'reference_date':'2020-01-01'})
                account = result['body']['result']['id']
                result = action(page,space,'card.create',{
                    'name':'Cartão fictício de pagamentos','account_id':account,
                    'closing_day':5,'due_day':15,'limit_cents':2000000})
                card = result['body']['result']['id']
                final_entry = create_expense(page,space,'Última parcela fictícia',30000,account,installments=3,paid=2)
                partial_entry = create_expense(page,space,'Parcial fictícia',90000,account,installments=3)
                card_entry = create_expense(page,space,'Compra cartão fictícia A',90000,account,installments=3,card=card,purchase_date=CURRENT_MONTH+'-01')
                card_other = create_expense(page,space,'Compra cartão fictícia B',60000,account,installments=3,card=card,purchase_date=CURRENT_MONTH+'-02')
                retry_entry = create_expense(page,space,'Resposta perdida fictícia',10000,account)
                conflict_entry = create_expense(page,space,'Pagamento concorrente fictício',10000,account)
                mobile_entry = create_expense(page,space,'Pagamento colaborador fictício',15000,account)
                advance_entry = create_expense(page,space,'Antecipação explícita fictícia',20000,account,
                    installments=2,due_date=f'{int(TODAY[:4])+1}-01-15')
                scope_entry = create_expense(page,space,'Escopo fictício terceira de dez',100000,account,
                    installments=10,paid=2)
                page.reload()
                expect(page.locator('.summary-grid')).to_be_visible()

                # The installment being paid must be distinguished from its complete purchase.
                before = current(page,space)
                third = obligations(before,scope_entry)[2]
                detail(page,scope_entry)
                row = page.locator(f'#modal .obligation-item[data-obligation-id="{third["id"]}"]')
                expect(row).to_contain_text('3/10')
                row.locator('[data-action="pay-obligation"]').click()
                expect(page.locator('#payment-confirm')).to_be_enabled(timeout=10000)
                expect(page.locator('#modal .modal-header')).to_contain_text('Parcela 3/10')
                expect(page.locator('#modal .payment-target')).to_contain_text('Saldo pendente da parcela 3/10')
                assert_summary_amount(page,'Valor original da parcela','100,00')
                assert_summary_amount(page,'Valor original da compra','1.000,00')
                assert_summary_amount(page,'Valor liquidado da parcela','0,00')
                assert_summary_amount(page,'Valor liquidado da compra antes','200,00')
                assert_summary_amount(page,'Valor liquidado da compra depois','300,00')
                assert_summary_amount(page,'Dívida da compra antes','800,00')
                assert_summary_amount(page,'Dívida da compra depois','700,00')
                page.screenshot(path=str(results/'payments-scope-desktop.png'),full_page=True)
                page.locator('#modal [data-action="close-modal"]').first.click()
                assert current(page,space) == before, 'Inspecting installment scope persisted a payment'
                checks.append('installment_3_of_10_labels_separate_piece_purchase_original_and_settled_values')

                # A past due date remains pending; the final piece can be paid at the default value.
                before = current(page,space)
                target = obligations(before,final_entry)[-1]
                assert target['status'] == 'overdue' and target['remaining_cents'] == 10000
                assert by_id(before,'entries',final_entry)['paid_installments'] == 2
                open_payment(page,final_entry,target['id'],amount=10000)
                expect(page.locator('#f-amount_cents')).not_to_be_visible()
                expect(page.locator('#f-account_id')).to_have_value(account)
                assert current(page,space) == before, 'Payment preview persisted a transaction'
                page.screenshot(path=str(results/'payments-full-desktop.png'),full_page=True)
                confirm(page)
                after = current(page,space)
                assert_effect(before,after,10000)
                entry = by_id(after,'entries',final_entry)
                assert entry['amount_cents'] == 30000 and entry['debt_cents'] == 0
                assert entry['paid_installments'] == 3 and entry['remaining_installments'] == 0
                assert len(after['payments']) == len(before['payments']) + 1
                final_payment = after['payments'][-1]['id']
                checks.append('default_full_without_amount_typing_expired_pending_final_installment')

                # Paying part of a piece preserves its original total, then only the rest is offered.
                before = after
                target = obligations(before,partial_entry)[0]
                open_payment(page,partial_entry,target['id'],amount=30000)
                page.locator('#payment-partial').click()
                field(page,'amount_cents','500,00')
                expect(page.locator('#f-amount_cents')).to_have_attribute('aria-invalid','true')
                expect(page.locator('#f-amount_cents')).to_have_value('500,00')
                expect(page.locator('#payment-confirm')).to_be_disabled()
                assert current(page,space) == before, 'Invalid partial amount changed financial data'
                page.screenshot(path=str(results/'payments-invalid-desktop.png'),full_page=True)
                field(page,'amount_cents','100,00')
                expect(page.locator('#payment-preview')).to_have_attribute('data-amount-cents','10000')
                expect(page.locator('#payment-confirm')).to_be_enabled(timeout=10000)
                page.screenshot(path=str(results/'payments-partial-desktop.png'),full_page=True)
                confirm(page)
                after = current(page,space)
                assert_effect(before,after,10000)
                entry = by_id(after,'entries',partial_entry)
                assert entry['amount_cents'] == 90000 and entry['debt_cents'] == 80000
                assert entry['paid_installments'] == 0 and entry['remaining_installments'] == 3
                assert by_id(after,'obligations',target['id'])['remaining_cents'] == 20000
                before = after
                open_payment(page,partial_entry,target['id'],amount=20000)
                confirm(page)
                after = current(page,space)
                assert_effect(before,after,20000)
                assert by_id(after,'entries',partial_entry)['paid_installments'] == 1
                assert by_id(after,'entries',partial_entry)['debt_cents'] == 60000
                checks.append('partial_then_only_rest_preserves_original_paid_and_remaining_counts')

                # Card piece opens its invoice; partial invoice allocates only money actually paid.
                before = after
                first_card = obligations(before,card_entry)[0]
                other_card = obligations(before,card_other)[0]
                invoice = first_card['invoice_id']
                assert invoice == other_card['invoice_id']
                open_payment(page,card_entry,invoice,invoice=True,amount=50000)
                assert page.locator('#modal [data-action="pay-obligation"]').count() == 0
                assert 'fatura' in page.locator('#modal-title').inner_text().lower()
                partial(page,'100,00',10000)
                page.screenshot(path=str(results/'payments-invoice-desktop.png'),full_page=True)
                confirm(page)
                after = current(page,space)
                assert_effect(before,after,10000)
                assert by_id(after,'invoices',invoice)['remaining_cents'] == 40000
                assert by_id(after,'obligations',first_card['id'])['remaining_cents'] == 20000
                assert by_id(after,'obligations',other_card['id'])['remaining_cents'] == 20000
                assert by_id(after,'entries',card_entry)['paid_installments'] == 0
                before = after
                open_payment(page,card_entry,invoice,invoice=True,amount=40000)
                confirm(page)
                after = current(page,space)
                assert_effect(before,after,40000)
                assert by_id(after,'invoices',invoice)['remaining_cents'] == 0
                assert by_id(after,'entries',card_entry)['debt_cents'] == 60000
                assert by_id(after,'entries',card_other)['debt_cents'] == 40000
                checks.append('card_detail_routes_invoice_partial_allocations_no_double_debt_or_consumption')

                # A successful response deliberately lost in transit must be safely replayed.
                before = after
                target = obligations(before,retry_entry)[0]
                open_payment(page,retry_entry,target['id'],amount=10000)
                payments = []
                def lose_response(route):
                    payload = route.request.post_data_json
                    if payload.get('action') in ('obligation.pay','invoice.pay'):
                        payments.append(payload)
                        if len(payments) == 1:
                            response = route.fetch()
                            assert response.status == 200
                            route.abort('failed')
                            return
                    route.continue_()
                page.route('**/api/spaces/*/actions',lose_response)
                page.locator('#payment-confirm').evaluate('button => {button.click();button.click();}')
                expect(page.locator('#form-error')).not_to_have_text('')
                expect(page.locator('#payment-confirm')).to_be_enabled()
                committed = current(page,space)
                assert_effect(before,committed,10000)
                assert len(committed['payments']) == len(before['payments']) + 1
                confirm(page)
                page.unroute('**/api/spaces/*/actions',lose_response)
                assert len(payments) == 2 and payments[0] == payments[1], 'Retry changed the original payment operation'
                assert current(page,space) == committed, 'Double submit or retry duplicated payment'
                checks.append('double_click_lost_success_response_same_request_replay_no_duplicate_cash')

                # Another browser pays part after the first browser has already viewed a full preview.
                before = current(page,space)
                target = obligations(before,conflict_entry)[0]
                open_payment(page,conflict_entry,target['id'],amount=10000)
                independent = browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
                other = independent.new_page()
                other.goto(BASE)
                logged_in = request(other,'/api/auth/login',{
                    'username':'payment_admin','password':helpers.PASSWORD})
                assert logged_in['status'] == 200
                action(other,space,'obligation.pay',{
                    'obligation_id':target['id'],'amount_cents':4000,
                    'account_id':account,'paid_on':TODAY})
                concurrent = current(other,space)
                page.locator('#payment-confirm').click()
                expect(page.locator('#form-error')).not_to_have_text('')
                expect(page.locator('#payment-preview-button')).to_be_visible()
                assert current(page,space) == concurrent, 'Stale preview caused another cash movement'
                page.locator('#payment-preview-button').click()
                expect(page.locator('#payment-preview')).to_have_attribute('data-amount-cents','6000')
                expect(page.locator('#payment-confirm')).to_be_enabled()
                confirm(page)
                after = current(page,space)
                assert_effect(before,after,10000)
                assert by_id(after,'obligations',target['id'])['remaining_cents'] == 0
                independent.close()
                checks.append('independent_session_concurrent_partial_rejects_stale_full_requires_refresh')

                # Reversal needs an explicit reason and restores the same cash/debt, retaining history.
                before = after
                detail(page,final_entry)
                page.locator(f'#modal [data-action="reverse-payment"][data-id="{final_payment}"]').click()
                page.locator('#dialog-form button[type="submit"]').click()
                assert current(page,space) == before, 'Empty reversal reason changed state'
                field(page,'reason','Estorno de ensaio fictício')
                page.locator('#dialog-form button[type="submit"]').click()
                expect(page.locator('#modal')).not_to_be_visible(timeout=10000)
                after = current(page,space)
                assert_effect(before,after,-10000)
                assert by_id(after,'payments',final_payment)['reversed'] is True
                assert by_id(after,'entries',final_entry)['paid_installments'] == 2
                assert by_id(after,'entries',final_entry)['debt_cents'] == 10000
                assert len(after['payments']) == len(before['payments']), 'Reversal discarded or recreated payment history'
                checks.append('explicit_reason_reversal_restores_cash_debt_and_reopens_final_installment')

                # A future-month obligation needs an explicit advance choice, not a normal confirmation.
                before = after
                target = obligations(before,advance_entry)[0]
                detail(page,advance_entry)
                page.locator(f'#modal [data-action="pay-obligation"][data-id="{target["id"]}"]').first.click()
                expect(page.locator('#payment-preview')).to_have_attribute('data-amount-cents','10000')
                expect(page.locator('#payment-confirm')).to_be_disabled()
                expect(page.locator('#payment-advance')).to_be_visible()
                assert current(page,space) == before, 'Opening future obligation moved cash'
                page.locator('#payment-advance').click()
                expect(page.locator('#payment-confirm')).to_be_enabled(timeout=10000)
                confirm(page)
                after = current(page,space)
                assert_effect(before,after,10000)
                assert after['payments'][-1]['operation'] == 'advance'
                assert by_id(after,'entries',advance_entry)['remaining_installments'] == 1
                checks.append('future_month_requires_explicit_advance_without_changing_other_installments')

                # Independent mobile collaborator may pay; reader sees no confirmation and is refused server-side.
                collab_context, mobile = helpers.register(browser,'payment_collaborator',mobile=True)
                reader_context, reader = helpers.register(browser,'payment_reader',mobile=True)
                for username,role in [('payment_collaborator','collaborator'),('payment_reader','reader')]:
                    joined = request(page,f'/api/spaces/{space}/members',{'username':username,'role':role})
                    assert joined['status'] == 200, joined
                mobile.reload()
                expect(mobile.locator('.summary-grid')).to_be_visible()
                mobile.on('pageerror',lambda error:errors.append(str(error)))
                before = current(mobile,space)
                target = obligations(before,mobile_entry)[0]
                open_payment(mobile,mobile_entry,target['id'],amount=15000)
                assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert mobile.locator('#modal').evaluate('el => el.scrollWidth <= el.clientWidth')
                mobile.screenshot(path=str(results/'payments-full-mobile.png'),full_page=True)
                mobile.locator('#modal .modal-body').evaluate('el => el.scrollTop = el.scrollHeight')
                mobile.screenshot(path=str(results/'payments-result-mobile.png'),full_page=True)
                confirm(mobile)
                after = current(mobile,space)
                assert_effect(before,after,15000)
                assert by_id(after,'obligations',target['id'])['remaining_cents'] == 0
                reader.reload()
                expect(reader.locator('.summary-grid')).to_be_visible()
                detail(reader,final_entry)
                expect(reader.locator('#modal [data-action="pay-obligation"]')).to_have_count(0)
                expect(reader.locator('#modal [data-action="pay-invoice"]')).to_have_count(0)
                forbidden = request(reader,f'/api/spaces/{space}/actions',{
                    'action':'obligation.pay','data':{'obligation_id':target['id'],
                        'amount_cents':100,'account_id':account,'paid_on':TODAY},
                    'expected_revision':after['revision'],'request_id':str(uuid.uuid4())})
                assert forbidden['status'] == 403, forbidden
                readonly = current(reader,space)
                assert readonly['revision'] == after['revision'] and readonly['ledger'] == after['ledger']
                reader.screenshot(path=str(results/'payments-reader-mobile.png'),full_page=True)
                checks.append('mobile_collaborator_payment_reader_hidden_actions_and_server_denial')
                assert not errors, errors
                evidence = {'checks':checks,'checks_passed':len(checks),
                    'desktop_viewport':'1440x1000','mobile_viewport':'390x844',
                    'fictitious_data_only':True,'production_database_accessed':False,
                    'fictitious_database':database.name,'physical_devices_tested':False,
                    'page_errors':errors}
                (results/'payments-ui-evidence.json').write_text(
                    json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
                print(json.dumps(evidence,indent=2,ensure_ascii=False))
            except Exception:
                if page is not None:
                    page.screenshot(path=str(results/'payments-failure.png'),full_page=True)
                    (results/'payments-failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()


if __name__ == '__main__':
    main()
