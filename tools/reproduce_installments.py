"""Capture original installment behavior on an isolated fictitious database."""
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.browser-cache')
from playwright.sync_api import sync_playwright, expect

def main():
    folder = ROOT / 'test-results'
    candidates = sorted(folder.glob('installments-baseline-*'))
    baseline = next((x for x in candidates if (x/'domain.py').exists()), None)
    if not baseline:
        raise RuntimeError('A cópia anterior à correção é necessária para esta reprodução histórica.')
    env = dict(os.environ, APP_DB_PATH=str(folder / ('baseline-repro-' + uuid.uuid4().hex + '.sqlite3')), APP_PORT='8768')
    subprocess.run([sys.executable,'manage.py','migrate','--noinput'], cwd=ROOT, env=env, check=True, capture_output=True)
    server = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve-baseline',str(baseline)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    base = 'http://127.0.0.1:8768'
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base+'/api/session', timeout=1).close(); break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.goto(base)
            def post(url,data):
                return page.evaluate("async args=>{const s=await(await fetch('/api/session')).json();const r=await fetch(args.url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':s.csrf_token},body:JSON.stringify(args.data)});return {status:r.status,data:await r.json()};}",{'url':url,'data':data})
            assert post('/api/auth/register',{'username':'baseline_fictitious','password':'Example-baseline-only-52739!','display_name':'Teste fictício'})['status']==201
            space=post('/api/spaces',{'name':'Investigação fictícia'})['data']['space']['id']
            revision=0
            def action(action,data):
                nonlocal revision
                r=post(f'/api/spaces/{space}/actions',{'action':action,'data':data,'expected_revision':revision,'request_id':str(uuid.uuid4())})
                assert r['status']==200,r
                revision=r['data']['revision'];return r['data']
            account=action('account.create',{'name':'Conta fictícia','opening_balance_cents':0,'reference_date':'2026-01-01'})['result']['id']
            card=action('card.create',{'name':'Cartão fictício','closing_day':10,'due_day':31,'limit_cents':500000,'account_id':account})['result']['id']
            page.reload();expect(page.locator('.nav-item[data-page="debts"]')).to_be_visible()
            page.locator('.nav-item[data-page="debts"]').click()
            page.locator('[data-action="installment-entry"]').first.click()
            form=page.locator('#dialog-form')
            form.locator('[name="description"]').fill('Conta fictícia fora do cartão')
            form.locator('[name="method"]').select_option('pix')
            form.locator('[name="amount_cents"]').fill('1.000')
            form.locator('[name="installments"]').fill('3')
            form.locator('[name="due_date"]').fill('2027-01-31')
            form.locator('[name="paid_installments"]').fill('1')
            form.locator('button[type="submit"]').click()
            expect(page.locator('#form-error')).not_to_be_empty()
            error=page.locator('#form-error').inner_text()
            kept=form.locator('[name="amount_cents"]').input_value()
            page.screenshot(path=str(folder/'installments-baseline-format.png'),full_page=True)
            form.locator('[name="amount_cents"]').fill('1.000,00')
            form.locator('button[type="submit"]').click()
            expect(page.locator('#modal')).not_to_be_visible()
            saved=page.evaluate("async url=>await(await fetch(url)).json()",f'/api/spaces/{space}/state')
            outside=next(x for x in saved['entries'] if x['description']=='Conta fictícia fora do cartão')
            schedule=[{k:o[k] for k in ('amount_cents','due_date','initial_paid_cents')} for o in saved['obligations'] if o['entry_id']==outside['id']]
            revision=saved['revision']
            card_entry=action('entry.create',{'kind':'expense','method':'credit','card_id':card,'description':'Teste vencimento cartão 31','amount_cents':100000,'installments':3,'purchase_date':'2027-01-15'})
            eid=card_entry['result']['id']
            card_dates=[o['due_date'] for o in card_entry['state']['obligations'] if o['entry_id']==eid]
            evidence={'reported_hugo_error_exactly_reproduced':False,'exact_user_error_not_provided':True,'browser_format_case':{'input':'1.000','error':error,'form_preserved':kept=='1.000'},'outside_with_brazilian_decimal':{'saved':True,'schedule':schedule,'historical_cash_rows':len(saved['ledger'])},'card_auto_due_day_31':{'purchase_date':'2027-01-15','actual_dates':card_dates,'expected_dates':['2027-02-28','2027-03-31','2027-04-30']},'fictitious_data_only':True}
            (folder/'installments-baseline-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(evidence,ensure_ascii=False,indent=2))
            browser.close()
    finally:
        server.terminate();server.wait(timeout=10)

def serve_baseline():
    import importlib.util
    sys.path.insert(0,str(ROOT))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
    from config.wsgi import application
    from config.urls import urlpatterns
    from django.http import FileResponse
    baseline=Path(sys.argv[-1])
    spec=importlib.util.spec_from_file_location('baseline_financial_domain',baseline/'domain.py')
    old_domain=importlib.util.module_from_spec(spec);spec.loader.exec_module(old_domain)
    spec=importlib.util.spec_from_file_location('finance.baseline_views',baseline/'views.py')
    old_views=importlib.util.module_from_spec(spec);spec.loader.exec_module(old_views)
    old_views.domain=old_domain
    original_static=old_views.static_asset
    def assets(request,asset):
        if asset in ('app.js','app.css'):
            return FileResponse((baseline/asset).open('rb'),content_type='text/javascript' if asset.endswith('.js') else 'text/css')
        return original_static(request,asset)
    for route in urlpatterns:
        if route.callback.__module__=='finance.views':
            route.callback=assets if route.callback.__name__=='static_asset' else getattr(old_views,route.callback.__name__)
    from waitress import serve
    serve(application,host='127.0.0.1',port=8768,threads=2)

if __name__=='__main__':
    serve_baseline() if '--serve-baseline' in sys.argv else main()
