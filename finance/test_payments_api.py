"""Payment confirmation regression: atomic writes, no duplicate cash, isolation."""
import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import AuditEvent, FinancialState, Operation

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PaymentsApiTests(TestCase):
    def post(self,client,url,data,expected=200):
        response=client.post(url,data=json.dumps(data),content_type='application/json')
        self.assertEqual(response.status_code,expected,response.content[:1000])
        return response.json()

    def setUp(self):
        self.admin,self.collaborator,self.reader,self.other=[Client() for _ in range(4)]
        for client,name in [(self.admin,'payments_admin'),(self.collaborator,'payments_collab'),(self.reader,'payments_reader'),(self.other,'payments_other')]:
            client.force_login(get_user_model().objects.create_user(username=name,password='Fictitious-payment-checks-73264!'))
        self.space=self.post(self.admin,'/api/spaces',{'name':'Confirmações fictícias'},201)['space']['id']
        self.url=f'/api/spaces/{self.space}/actions'
        self.today=timezone.localdate().isoformat()
        self.account=self.call('account.create',{'name':'Conta fictícia','opening_balance_cents':200000,'reference_date':'2026-01-01'})['result']['id']
        for username,role in [('payments_collab','collaborator'),('payments_reader','reader')]:
            self.post(self.admin,f'/api/spaces/{self.space}/members',{'username':username,'role':role})

    def state(self):
        return self.admin.get(f'/api/spaces/{self.space}/state').json()

    def call(self,action,data,client=None,expected=200,revision=None,key=None):
        return self.post(client or self.admin,self.url,{'action':action,'data':data,'expected_revision':self.state()['revision'] if revision is None else revision,'request_id':key or str(uuid.uuid4())},expected)

    def purchase(self,amount=100000,parts=1,card=None,**extra):
        data={'kind':'expense','method':'credit' if card else 'pix','description':'Dívida fictícia','amount_cents':amount,'installments':parts,'due_date':self.today,'account_id':self.account,'paid':False}
        if card:data['card_id']=card
        data.update(extra)
        result=self.call('entry.create',data)
        entry_id=result['result']['id']
        return [o for o in result['state']['obligations'] if o['entry_id']==entry_id]

    def test_full_without_amount_then_reverse_keeps_original_and_restores_cash(self):
        obligation=self.purchase()[0]
        before=self.state()
        preview=self.call('payment.preview',{'obligation_id':obligation['id'],'mode':'full','account_id':self.account})['result']
        self.assertEqual(preview['amount_cents'],100000)
        self.assertEqual(self.state(),before)
        result=self.call('obligation.pay',{'obligation_id':obligation['id'],'mode':'full','expected_remaining_cents':100000,'account_id':self.account,'paid_on':self.today})
        after=result['state'];entry=after['entries'][0]
        self.assertEqual((entry['amount_cents'],entry['paid_cents'],entry['debt_cents']),(100000,100000,0))
        self.assertEqual((entry['paid_installments'],entry['remaining_installments']),(1,0))
        self.assertEqual(after['balance_cents'],100000)
        payment=result['result']['payment']
        reversed_state=self.call('payment.reverse',{'payment_id':payment['id'],'reason':'Ensaio fictício de estorno','occurred_on':self.today})['state']
        self.assertEqual(reversed_state['balance_cents'],200000)
        self.assertEqual(reversed_state['debt_cents'],100000)
        self.assertTrue(reversed_state['payments'][0]['reversed'])
        self.assertEqual(len(reversed_state['payments']),1)

    def test_partial_then_full_rest_preserves_original_and_150_850_example(self):
        obligation=self.purchase()[0]
        result=self.call('obligation.pay',{'obligation_id':obligation['id'],'mode':'partial','amount_cents':15000,'account_id':self.account,'paid_on':self.today})['state']
        entry=result['entries'][0]
        self.assertEqual((entry['amount_cents'],entry['paid_cents'],entry['debt_cents']),(100000,15000,85000))
        self.assertEqual((entry['paid_installments'],entry['remaining_installments']),(0,1))
        self.assertEqual(result['balance_cents'],185000)
        final=self.call('obligation.pay',{'obligation_id':obligation['id'],'mode':'full','account_id':self.account})['state']
        self.assertEqual(final['debt_cents'],0)
        self.assertEqual(final['balance_cents'],100000)
        self.assertEqual(final['entries'][0]['amount_cents'],100000)

    def test_card_routes_invoice_no_direct_part_pay_and_no_double_expense(self):
        card=self.call('card.create',{'name':'Cartão fictício','closing_day':10,'due_day':25,'account_id':self.account,'limit_cents':500000})['result']['id']
        parts=self.purchase(amount=30000,card=card)
        second=self.purchase(amount=20000,card=card)
        invoice=parts[0]['invoice_id']
        before=self.state()
        self.call('obligation.pay',{'obligation_id':parts[0]['id'],'account_id':self.account},expected=400)
        self.assertEqual(self.state(),before)
        preview=self.call('payment.preview',{'invoice_id':invoice,'mode':'partial','amount_cents':10000,'account_id':self.account})['result']
        self.assertEqual(preview['pending_cents'],50000)
        partial=self.call('invoice.pay',{'invoice_id':invoice,'mode':'partial','amount_cents':10000,'expected_remaining_cents':50000,'account_id':self.account})['state']
        self.assertEqual(partial['debt_cents'],40000)
        self.assertEqual(partial['balance_cents'],190000)
        self.assertEqual(partial['reports']['expense_cents'],50000)
        self.assertEqual(sum(p['paid_cents'] for p in partial['obligations']),10000)
        self.assertEqual(sum(p['remaining_cents']>0 for p in partial['obligations']),2)
        full=self.call('invoice.pay',{'invoice_id':invoice,'mode':'full','expected_remaining_cents':40000,'account_id':self.account})['state']
        self.assertEqual((full['debt_cents'],full['balance_cents'],full['reports']['expense_cents']),(0,150000,50000))

    def test_replay_and_second_session_old_revision_do_not_double_pay(self):
        obligation=self.purchase(amount=10000)[0]
        before=self.state();key=str(uuid.uuid4())
        data={'obligation_id':obligation['id'],'mode':'full','account_id':self.account}
        first=self.call('obligation.pay',data,revision=before['revision'],key=key)
        replay=self.call('obligation.pay',data,revision=before['revision'],key=key)
        self.assertEqual(first['result'],replay['result'])
        self.call('obligation.pay',data,client=self.collaborator,revision=before['revision'],expected=409)
        final=self.state()
        self.assertEqual(len(final['payments']),1)
        self.assertEqual(final['balance_cents'],190000)

    def test_failure_after_state_update_rolls_back_payment_ledger_audit(self):
        obligation=self.purchase(amount=10000)[0]
        before=self.state();operations=Operation.objects.count();events=AuditEvent.objects.count()
        with patch('finance.views.Operation.objects.create',side_effect=IntegrityError('synthetic payment failure')):
            self.call('obligation.pay',{'obligation_id':obligation['id'],'mode':'full','account_id':self.account},expected=409)
        self.assertEqual(self.state(),before)
        self.assertEqual(Operation.objects.count(),operations)
        self.assertEqual(AuditEvent.objects.count(),events)
        self.assertEqual(FinancialState.objects.get(workspace_id=self.space).revision,before['revision'])

    def test_invalid_amount_or_stale_pending_never_alters_state(self):
        obligation=self.purchase(amount=10000)[0]
        before=self.state()
        for changes in [{'mode':'partial','amount_cents':10001},{'mode':'partial','amount_cents':0},{'mode':'partial','amount_cents':1.2},{'mode':'full','amount_cents':5000},{'mode':'full','expected_remaining_cents':9999}]:
            with self.subTest(changes=changes):
                self.call('obligation.pay',{'obligation_id':obligation['id'],'account_id':self.account,**changes},expected=400)
                self.assertEqual(self.state(),before)

    def test_permission_preview_reader_allowed_payment_denied_other_space_hidden(self):
        obligation=self.purchase(amount=10000)[0]
        payload={'obligation_id':obligation['id'],'mode':'full','account_id':self.account}
        self.call('payment.preview',payload,client=self.reader)
        self.call('obligation.pay',payload,client=self.reader,expected=403)
        self.call('payment.preview',payload,client=self.other,expected=404)
        self.call('obligation.pay',payload,client=self.other,expected=404)
        self.call('obligation.pay',payload,client=self.collaborator)

    def test_account_must_be_explicit_or_valid_preference(self):
        parts=self.purchase(amount=10000,account_id=None)
        self.call('obligation.pay',{'obligation_id':parts[0]['id'],'mode':'full'},expected=400)
        self.call('payment.preview',{'obligation_id':parts[0]['id'],'mode':'full'})
        self.call('obligation.pay',{'obligation_id':parts[0]['id'],'mode':'full','account_id':self.account})

    def test_future_month_requires_dedicated_advance_and_keeps_history(self):
        from .domain import add_months
        due=add_months(timezone.localdate(),1).isoformat()
        obligation=self.purchase(amount=5000,due_date=due)[0]
        before=self.state()
        payload={'obligation_id':obligation['id'],'mode':'full','account_id':self.account,'paid_on':self.today}
        preview=self.call('payment.preview',payload)['result']
        self.assertTrue(preview['requires_advance'])
        self.assertFalse(preview['can_confirm'])
        self.call('obligation.pay',payload,expected=400)
        self.assertEqual(self.state(),before)
        preview=self.call('payment.preview',{**payload,'operation':'advance'})['result']
        self.assertTrue(preview['can_confirm'])
        advanced=self.call('payment.advance',payload)['state']
        self.assertEqual(advanced['debt_cents'],0)
        self.assertEqual(advanced['balance_cents'],195000)
        self.assertEqual(advanced['payments'][0]['operation'],'advance')
        self.assertEqual(advanced['entries'][0]['amount_cents'],5000)
