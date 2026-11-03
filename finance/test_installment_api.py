"""Installment regression checks: preview, transactional failure and permissions."""
import copy
import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings

from .models import AuditEvent, FinancialState, Operation

@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class InstallmentApiTests(TestCase):
    def post(self, client, url, data, expected=200):
        response=client.post(url,data=json.dumps(data),content_type='application/json')
        self.assertEqual(response.status_code,expected,response.content[:1000])
        return response.json()

    def setUp(self):
        self.admin=Client();self.collaborator=Client();self.reader=Client();self.stranger=Client()
        for client,name in [(self.admin,'installment_admin'),(self.collaborator,'installment_collaborator'),(self.reader,'installment_reader'),(self.stranger,'installment_other')]:
            client.force_login(get_user_model().objects.create_user(username=name,password='Fictitious-passphrase-only-321!'))
        self.space=self.post(self.admin,'/api/spaces',{'name':'Teste de parcelas fictícias'},201)['space']['id']
        self.url=f'/api/spaces/{self.space}/actions'
        for username,role in [('installment_collaborator','collaborator'),('installment_reader','reader')]:
            self.post(self.admin,f'/api/spaces/{self.space}/members',{'username':username,'role':role})
        self.account=self.call('account.create',{'name':'Conta fictícia','reference_date':'2026-01-01','opening_balance_cents':0})['result']['id']
        self.card=self.call('card.create',{'name':'Cartão fictício','closing_day':10,'due_day':31,'limit_cents':500000,'account_id':self.account})['result']['id']

    def state(self):
        return self.admin.get(f'/api/spaces/{self.space}/state').json()

    def call(self,action,data,client=None,expected=200,revision=None,request_id=None):
        return self.post(client or self.admin,self.url,{'action':action,'data':data,'expected_revision':self.state()['revision'] if revision is None else revision,'request_id':request_id or str(uuid.uuid4())},expected)

    def purchase(self,credit=False,**changes):
        data={'kind':'expense','description':'Parcelamento fictício','method':'transfer','amount_cents':100000,'installments':3,'paid_installments':0,'paid':False,'due_date':'2027-01-31','value_mode':'total'}
        if credit:
            data.update(method='credit',card_id=self.card,first_invoice_month='2027-02')
            data.pop('due_date')
        data.update(changes)
        return data

    def test_preview_exact_card_schedule_and_no_persistence(self):
        before=self.state()
        result=self.call('entry.preview',self.purchase(True))['result']
        self.assertEqual([p['amount_cents'] for p in result['schedule']],[33334,33333,33333])
        self.assertEqual([p['due_date'] for p in result['schedule']],['2027-02-28','2027-03-31','2027-04-30'])
        self.assertEqual(result['initial_debt_cents'],100000)
        self.assertEqual(self.state(),before)

    def test_outside_installments_need_no_card_or_account_and_history_has_no_cash(self):
        data=self.purchase(paid_installments=1)
        preview=self.call('entry.preview',data)['result']
        saved=self.call('entry.create',data)['state']
        self.assertEqual(preview['initial_debt_cents'],66666)
        self.assertEqual(saved['debt_cents'],66666)
        self.assertFalse(saved['invoices'])
        self.assertFalse(saved['ledger'])
        self.assertEqual([x['due_date'] for x in saved['obligations']],['2027-01-31','2027-02-28','2027-03-31'])

    def test_installment_value_mode_is_explicit_and_total_cannot_disagree(self):
        data=self.purchase(value_mode='installment',installment_amount_cents=33333,amount_cents=99999)
        result=self.call('entry.preview',data)['result']
        self.assertEqual(result['total_cents'],99999)
        self.assertEqual([x['amount_cents'] for x in result['schedule']],[33333]*3)
        data['amount_cents']=100000
        self.call('entry.create',data,expected=400)
        self.assertFalse(self.state()['entries'])

    def test_invalid_inputs_are_clear_and_preserve_all_state(self):
        cases=[{'amount_cents':0},{'amount_cents':1.2},{'installments':3.5},{'installments':True},{'installments':0},{'paid_installments':4},{'paid_installments':-1},{'due_date':'2027-02-31'},{'description':''}]
        before=self.state()
        for changes in cases:
            with self.subTest(changes=changes):
                result=self.call('entry.preview',self.purchase(**changes),expected=400)
                self.assertTrue(result['error'])
                self.assertIsInstance(result.get('field_errors'),dict)
                self.assertNotIn('Traceback',result['error'])
                self.assertEqual(self.state(),before)

    def test_create_replay_does_not_duplicate_obligations_or_invoices(self):
        revision=self.state()['revision'];key=str(uuid.uuid4());data=self.purchase(True)
        first=self.call('entry.create',data,revision=revision,request_id=key)
        second=self.call('entry.create',data,revision=revision,request_id=key)
        self.assertEqual(first['result']['id'],second['result']['id'])
        state=self.state()
        self.assertEqual(len(state['entries']),1)
        self.assertEqual(len(state['obligations']),3)
        self.assertEqual(len(state['invoices']),3)
        self.assertEqual(state['debt_cents'],100000)

    def test_failure_after_state_update_rolls_back_purchase_parts_and_audit(self):
        before=self.state();operations=Operation.objects.count();audits=AuditEvent.objects.count()
        with patch('finance.views.Operation.objects.create',side_effect=IntegrityError('synthetic write failure')):
            self.call('entry.create',self.purchase(True),expected=409)
        self.assertEqual(self.state(),before)
        self.assertEqual(Operation.objects.count(),operations)
        self.assertEqual(AuditEvent.objects.count(),audits)
        self.assertEqual(FinancialState.objects.get(workspace_id=self.space).revision,before['revision'])

    def test_collaborator_can_create_reader_only_preview_and_other_space_is_denied(self):
        self.call('entry.preview',self.purchase(),client=self.reader)
        self.call('entry.create',self.purchase(),client=self.reader,expected=403)
        self.call('entry.preview',self.purchase(),client=self.stranger,expected=404)
        result=self.call('entry.create',self.purchase(),client=self.collaborator)
        self.assertEqual(result['state']['debt_cents'],100000)

    def test_preview_revision_conflict_preserves_database(self):
        before=self.state()
        self.call('entry.preview',self.purchase(),revision=before['revision']-1,expected=409)
        self.assertEqual(self.state(),before)

    def test_legacy_card_and_outside_payloads_remain_valid(self):
        for credit in (False,True):
            data=self.purchase(credit)
            data.pop('value_mode')
            if credit:
                data.pop('first_invoice_month')
                data['due_date']='2027-01-31'
            self.call('entry.create',data)
        self.assertEqual(len(self.state()['entries']),2)
