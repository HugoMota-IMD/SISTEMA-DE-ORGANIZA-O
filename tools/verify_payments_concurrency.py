"""Two simultaneous authenticated HTTP sessions, isolated fictitious SQLite DB."""
import concurrent.futures
import http.cookiejar
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent.parent
BASE='http://127.0.0.1:8770'

class Session:
    def __init__(self):
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf=None

    def call(self,path,payload=None):
        headers={'Accept':'application/json'}
        if payload is not None:
            headers.update({'Content-Type':'application/json','X-CSRFToken':self.csrf or ''})
        request=urllib.request.Request(BASE+path,data=None if payload is None else json.dumps(payload).encode(),headers=headers)
        try:
            response=self.opener.open(request,timeout=30)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            body=json.load(response)
            if 'csrf_token' in body:self.csrf=body['csrf_token']
            return response.status,body

def main():
    results=ROOT/'test-results';results.mkdir(exist_ok=True)
    tag=uuid.uuid4().hex
    env=dict(os.environ,APP_DB_PATH=str(results/f'payments-concurrency-{tag}.sqlite3'),APP_SECRET_KEY=secrets.token_urlsafe(64),APP_PORT='8770',APP_LOCAL_MODE='true',APP_ALLOWED_HOSTS='localhost,127.0.0.1')
    subprocess.run([sys.executable,'manage.py','migrate','--noinput'],cwd=ROOT,env=env,check=True,capture_output=True)
    server=subprocess.Popen([sys.executable,'serve.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for _ in range(100):
            try:urllib.request.urlopen(BASE+'/api/session',timeout=1).close();break
            except OSError:time.sleep(.1)
        first,second=Session(),Session()
        for client,name in [(first,'concurrent_admin'),(second,'concurrent_collaborator')]:
            assert client.call('/api/session')[0]==200
            assert client.call('/api/auth/register',{'username':name,'password':'Fictitious-concurrency-only-68521!'})[0]==201
        status,created=first.call('/api/spaces',{'name':'Concorrência fictícia'})
        assert status==201,created
        space=created['space']['id'];url=f'/api/spaces/{space}/actions'
        assert first.call(f'/api/spaces/{space}/members',{'username':'concurrent_collaborator','role':'collaborator'})[0]==200
        def state():
            status,body=first.call(f'/api/spaces/{space}/state');assert status==200,body;return body
        def action(action,data):
            status,result=first.call(url,{'action':action,'data':data,'expected_revision':state()['revision'],'request_id':str(uuid.uuid4())})
            assert status==200,result
            return result
        today=datetime.now(ZoneInfo('America/Manaus')).date().isoformat()
        account=action('account.create',{'name':'Conta fictícia','opening_balance_cents':100000,'reference_date':today})['result']['id']
        created=action('entry.create',{'kind':'expense','method':'pix','description':'Parcela fictícia concorrente','amount_cents':10000,'account_id':account,'due_date':today})
        obligation=next(o for o in created['state']['obligations'] if o['entry_id']==created['result']['id'])
        initial=state();revision=initial['revision']
        payloads=[]
        for client in (first,second):
            status,preview=client.call(url,{'action':'payment.preview','data':{'obligation_id':obligation['id'],'mode':'full','account_id':account},'expected_revision':revision})
            assert status==200,preview
            assert preview['result']['amount_cents']==10000
            payloads.append({'action':'obligation.pay','data':{'obligation_id':obligation['id'],'mode':'full','expected_remaining_cents':10000,'account_id':account,'paid_on':today},'expected_revision':revision,'request_id':str(uuid.uuid4())})
        barrier=threading.Barrier(2)
        def simultaneous(index):
            barrier.wait(timeout=10)
            return (first,second)[index].call(url,payloads[index])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures=[executor.submit(simultaneous,index) for index in (0,1)]
            responses=[future.result(timeout=40) for future in futures]
        statuses=[item[0] for item in responses]
        assert sorted(statuses)==[200,409],statuses
        final=state()
        assert len(final['payments'])==1 and len(final['ledger'])==1
        assert final['debt_cents']==0 and final['balance_cents']==90000
        assert final['entries'][0]['amount_cents']==10000
        winner=statuses.index(200)
        replay=(first,second)[winner].call(url,payloads[winner])
        assert replay[0]==200 and replay[1]['duplicate']
        assert state()==final
        evidence={'simultaneous_authenticated_sessions':2,'response_statuses':statuses,'payments_created':len(final['payments']),'cash_movements_created':len(final['ledger']),'cash_debit_cents':10000,'remaining_debt_cents':0,'original_preserved':True,'winner_retry_no_duplicate':True,'fictitious_data_only':True,'production_database_accessed':False}
        (results/'payments-concurrency-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(json.dumps(evidence,indent=2))
    finally:
        server.terminate();server.wait(timeout=10)

if __name__=='__main__':main()
