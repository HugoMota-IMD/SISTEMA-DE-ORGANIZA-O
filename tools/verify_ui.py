"""Browser acceptance on an isolated server/database; no production data is touched."""
import json
import os
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
from playwright.sync_api import sync_playwright, expect

def main():
    results = ROOT / 'test-results'
    results.mkdir(exist_ok=True)
    run_id = uuid.uuid4().hex
    env = dict(os.environ, APP_DB_PATH=str(results / f'ui-{run_id}.sqlite3'), APP_PORT='8766')
    subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'], cwd=ROOT, env=env, check=True, capture_output=True)
    server = subprocess.Popen([sys.executable, 'serve.py'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    base = 'http://127.0.0.1:8766'
    today = datetime.now(ZoneInfo('America/Manaus')).date().isoformat()
    failures = []
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/api/session', timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width':1440,'height':1000}, locale='pt-BR')
            page = context.new_page()
            page.on('pageerror', lambda error: failures.append(str(error)))
            page.on('console', lambda message: failures.append(message.text) if message.type == 'error' else None)
            def field(name, value):
                page.locator(f'#modal [name="{name}"]').fill(str(value))
            def choose(name, value):
                page.locator(f'#modal select[name="{name}"]').select_option(value=value)
            def click_action(action):
                page.locator(f'[data-action="{action}"]').first.click()
            def nav(name):
                page.locator(f'.nav-item[data-page="{name}"]').click()
            def save():
                page.locator('#dialog-form button[type="submit"]').click()
                try:
                    expect(page.locator('#modal')).not_to_be_visible(timeout=10000)
                except Exception:
                    raise AssertionError('Dialog save failed: ' + page.locator('#form-error').inner_text())
            def state():
                return page.evaluate("async()=>{const s=await(await fetch('/api/session')).json();return await(await fetch('/api/spaces/'+s.spaces[0].id+'/state')).json();}")
            try:
                page.goto(base)
                expect(page.locator('#auth-form')).to_be_visible()
                page.screenshot(path=str(results/'ui-login-desktop.png'), full_page=True)
                click_action('auth-toggle')
                page.locator('[name="display_name"]').fill('Pessoa fictícia QA')
                page.locator('[name="username"]').fill('ui_fictitious')
                page.locator('[name="password"]').fill('Browser-example-only-83751!')
                page.locator('#auth-form button[type="submit"]').click()
                expect(page.locator('[data-action="new-space"]').first).to_be_visible()
                click_action('new-space')
                field('name','Família fictícia QA')
                save()
                click_action('new-account')
                field('name','Conta fictícia QA')
                field('institution','Banco de teste')
                field('opening_balance_cents','1.000,00')
                save()
                nav('cards')
                click_action('new-card')
                field('name','Cartão fictício QA')
                field('institution','Banco de teste')
                field('last_four','1234')
                field('limit_cents','5.000,00')
                save()
                nav('entries')
                click_action('new-entry')
                choose('kind','income')
                field('description','Receita fictícia QA')
                field('amount_cents','2.000,00')
                page.locator('#f-paid').check()
                save()
                assert state()['balance_cents'] == 300000
                click_action('pix-entry') if page.locator('[data-action="pix-entry"]').count() else click_action('new-entry')
                field('description','iFood fictício QA')
                field('merchant','iFood')
                field('amount_cents','100,00')
                page.locator('#f-category_id').select_option(label='Alimentação')
                page.locator('#f-paid').check()
                save()
                assert state()['balance_cents'] == 290000
                nav('debts')
                click_action('installment-entry')
                field('description','Compra fictícia QA')
                choose('modality','credit')
                choose('card_id',state()['cards'][0]['id'])
                page.locator('#installment-next').click()
                field('amount_cents','1.000,00')
                field('installments',3)
                field('first_invoice_month',today[:7])
                page.locator('#installment-next').click()
                expect(page.locator('#installment-schedule tbody tr')).to_have_count(3)
                page.locator('#installment-confirm').click()
                expect(page.locator('#modal')).not_to_be_visible(timeout=10000)
                snap = state()
                assert snap['debt_cents'] == 100000
                assert sum(o['amount_cents'] for o in snap['obligations'] if o.get('card_id')) == 100000
                nav('cards')
                page.locator('[data-action="pay-invoice"]').first.click()
                expect(page.locator('#payment-confirm')).to_be_enabled(timeout=10000)
                page.locator('#payment-partial').click()
                field('amount_cents','100,00')
                expect(page.locator('#payment-preview')).to_have_attribute('data-amount-cents','10000')
                expect(page.locator('#payment-confirm')).to_be_enabled(timeout=10000)
                save()
                assert state()['debt_cents'] == 90000
                assert state()['balance_cents'] == 280000
                nav('home')
                page.screenshot(path=str(results/'ui-home-desktop.png'), full_page=True)
                nav('future')
                expect(page.locator('.projection-table tbody tr')).to_have_count(12)
                before_horizon = state()['debt_cents']
                page.locator('#projection-months').select_option('60')
                expect(page.locator('.projection-table tbody tr')).to_have_count(60)
                assert state()['debt_cents'] == before_horizon
                page.locator('#projection-months').select_option('12')
                expect(page.locator('.projection-table tbody tr')).to_have_count(12)
                before_sim = state()
                click_action('simulate')
                field('amount_cents','1.200,00')
                field('installments',6)
                save()
                assert state() == before_sim, 'Simulation modified persisted state'
                page.screenshot(path=str(results/'ui-future-desktop.png'), full_page=True)
                nav('reports')
                expect(page.get_by_role('heading', name='Relatórios e orçamento', exact=True)).to_be_visible()
                # The same persisted space is loaded in an independent browser session.
                second = browser.new_context(viewport={'width':390,'height':844}, locale='pt-BR', is_mobile=True, has_touch=True)
                mobile = second.new_page()
                mobile.on('pageerror', lambda error: failures.append(str(error)))
                mobile.goto(base)
                mobile.locator('[name="username"]').fill('ui_fictitious')
                mobile.locator('[name="password"]').fill('Browser-example-only-83751!')
                mobile.locator('#auth-form button[type="submit"]').click()
                expect(mobile.locator('.summary-grid')).to_be_visible()
                assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile page has horizontal overflow'
                mobile.screenshot(path=str(results/'ui-home-mobile.png'), full_page=True)
                mobile.locator('[data-action="menu"]').click()
                mobile.locator('.nav-item[data-page="future"]').click()
                expect(mobile.locator('.projection-table tbody tr')).to_have_count(12)
                mobile.screenshot(path=str(results/'ui-future-mobile.png'), full_page=True)
                assert not failures, failures
                evidence = {'stage2_flow':True,'desktop_viewport':'1440x1000','mobile_viewport':'390x844','independent_browser_session':True,'projection_12_and_60_months':True,'simulation_does_not_persist':True,'mobile_no_page_overflow':True,'browser_errors':failures,'fictitious_data_only':True,'physical_devices_tested':False}
                (results/'ui-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
                print(json.dumps(evidence,indent=2))
            except Exception:
                page.screenshot(path=str(results/'ui-failure.png'), full_page=True)
                (results/'ui-failure.txt').write_text(page.locator('body').inner_text()+'\n'+json.dumps(failures),encoding='utf-8')
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

if __name__ == '__main__':
    main()
