"""Fictitious financial acceptance cases; runnable without Django or a database."""

import json
import unittest
from copy import deepcopy
from datetime import date

from finance.domain import add_months, mutate, new_state, preview_entry, snapshot


class FinancialRulesTests(unittest.TestCase):
    today = date(2026, 10, 19)

    def setUp(self):
        self.state = new_state()
        self.account = self.act("account.create", name="Conta fictícia", institution="Banco de teste",
                                opening_balance_cents=500000, reference_date="2026-01-01")["account"]
        self.food = next(item for item in self.state["categories"] if item["name"] == "Alimentação")

    def act(self, action, **data):
        return mutate(self.state, action, data, actor_id=1, today=self.today)

    def view(self, **kwargs):
        return snapshot(self.state, as_of=self.today, **kwargs)

    def expense(self, **kwargs):
        return self.act("entry.create", **{
            "kind": "expense", "description": "Despesa fictícia", "amount_cents": 10000,
            "category_id": self.food["id"], "account_id": self.account["id"], "method": "pix",
            "purchase_date": "2026-10-10", "due_date": "2026-10-20", **kwargs,
        })["entry"]

    def card(self, **kwargs):
        return self.act("card.create", **{
            "name": "Cartão fictício", "institution": "Teste", "holder_id": 1,
            "last_four": "1234", "limit_cents": 1000000,
            "closing_day": 25, "due_day": 5, "account_id": self.account["id"], **kwargs,
        })["card"]

    def obligation(self, entry, index=0):
        return [item for item in self.state["obligations"] if item["entry_id"] == entry["id"]][index]

    def pay(self, obligation, **kwargs):
        return self.act("obligation.pay", **{
            "obligation_id": obligation["id"], "account_id": self.account["id"],
            "paid_on": self.today.isoformat(), **kwargs,
        })["payment"]

    def test_food_groups_merchant_and_method_without_duplicate_records(self):
        self.expense(description="iFood", merchant="iFood", amount_cents=10000, method="pix")
        self.expense(description="Crepes", merchant="Crepes e Crepes", amount_cents=18500, method="debit")
        view = self.view()
        self.assertEqual(view["reports"]["by_category"][0]["amount_cents"], 28500)
        self.assertEqual(view["reports"]["expense_cents"], 28500)
        self.assertEqual(len(view["entries"]), 2)
        self.assertEqual(len(view["reports"]["by_merchant"]), 2)
        self.assertEqual(len(view["reports"]["by_method"]), 2)

    def test_thousand_in_three_preserves_every_cent(self):
        entry = self.expense(amount_cents=100000, installments=3)
        parts = [item["amount_cents"] for item in self.state["obligations"] if item["entry_id"] == entry["id"]]
        self.assertEqual(parts, [33334, 33333, 33333])
        self.assertEqual(sum(parts), 100000)
        self.assertEqual(self.view()["debt_cents"], 100000)

    def preview(self, **kwargs):
        return preview_entry(self.state, {
            "kind": "expense", "description": "Parcelamento fictício",
            "amount_cents": 100000, "installments": 3, "method": "transfer",
            "purchase_date": "2026-10-10", "due_date": "2026-10-31", **kwargs,
        }, actor_id=1, today=self.today)

    def test_installment_preview_preserves_exact_total_and_never_mutates(self):
        before = deepcopy(self.state)
        preview = self.preview()
        self.assertEqual(self.state, before)
        self.assertEqual([item["amount_cents"] for item in preview["schedule"]], [33334, 33333, 33333])
        self.assertEqual(preview["total_cents"], 100000)
        self.assertEqual(preview["initial_debt_cents"], 100000)
        self.assertEqual(preview["paid_installments"], 0)
        self.assertEqual(preview["remaining_installments"], 3)
        self.assertEqual(preview["last_due_date"], "2026-12-31")
        self.assertEqual(preview["modality"], "outside")
        self.assertIsNone(preview["card"])

    def test_installment_value_mode_means_equal_parts_and_validates_total(self):
        result = self.preview(value_mode="installment", installment_amount_cents=33333, amount_cents=99999)
        self.assertEqual([item["amount_cents"] for item in result["schedule"]], [33333] * 3)
        self.assertEqual(result["value_mode"], "installment")
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "multiplicado"):
            self.preview(value_mode="installment", installment_amount_cents=33333, amount_cents=100000)
        self.assertEqual(self.state, before)

    def test_installment_invalid_modes_and_amounts_are_rejected(self):
        cases = (
            ({"value_mode": "unknown"}, "valor total"),
            ({"value_mode": "total", "installment_amount_cents": 10000}, "somente"),
            ({"value_mode": "installment", "installment_amount_cents": 0}, "positivo"),
            ({"value_mode": "installment", "installment_amount_cents": 1.1}, "centavos inteiros"),
            ({"amount_cents": 0}, "positivo"),
            ({"amount_cents": 2}, "um centavo"),
        )
        before = deepcopy(self.state)
        for values, message in cases:
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, message):
                self.preview(**values)
            self.assertEqual(self.state, before)

    def test_installment_invalid_count_history_and_date_leave_state_intact(self):
        cases = (
            ({"installments": 2.5}, "inteiro"),
            ({"installments": True}, "inteiro"),
            ({"installments": 0}, "inteiro"),
            ({"paid_installments": 4}, "Parcelas já pagas"),
            ({"paid_installments": -1}, "Parcelas já pagas"),
            ({"paid_installments": 1.1}, "Parcelas já pagas"),
            ({"due_date": "2026-02-30"}, "data válida"),
            ({"description": " "}, "descrição"),
        )
        before = deepcopy(self.state)
        for values, message in cases:
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, message):
                self.preview(**values)
            self.assertEqual(self.state, before)

    def test_previous_paid_unequal_installments_preview_matches_saved_initial_debt(self):
        payload = {"kind": "expense", "description": "Dívida fictícia anterior", "amount_cents": 100000,
                   "installments": 3, "paid_installments": 1, "method": "transfer",
                   "due_date": "2026-08-31", "paid": False}
        before = deepcopy(self.state)
        preview = preview_entry(self.state, payload, 1, self.today)
        self.assertEqual(preview["initial_paid_cents"], 33334)
        self.assertEqual(preview["initial_debt_cents"], 66666)
        self.assertEqual(preview["remaining_installments"], 2)
        self.assertEqual([item["already_paid"] for item in preview["schedule"]], [True, False, False])
        self.assertEqual(before, self.state)
        entry = self.act("entry.create", **payload)["entry"]
        self.assertIsNone(entry["account_id"])
        self.assertIsNone(entry["card_id"])
        self.assertEqual(self.view()["debt_cents"], preview["initial_debt_cents"])
        self.assertEqual(self.view()["balance_cents"], 500000)
        self.assertEqual(self.state["ledger"], [])
        self.assertEqual(self.state["payments"], [])
        self.assertEqual(self.state["invoices"], [])

    def test_pending_outside_installments_can_choose_account_when_payment_happens(self):
        entry = self.expense(method="transfer", account_id=None, installments=3, amount_cents=100000)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "Conta"):
            self.act("obligation.pay", obligation_id=self.obligation(entry)["id"])
        self.assertEqual(self.state, before)
        self.pay(self.obligation(entry))
        self.assertEqual(self.view()["debt_cents"], 66666)
        self.assertEqual(self.view()["balance_cents"], 466666)

    def test_cash_confirmation_still_requires_account(self):
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "Conta"):
            self.expense(account_id=None, paid=True, installments=3)
        self.assertEqual(self.state, before)

    def test_outside_dates_29_30_31_resume_original_anchor(self):
        for day, march in ((29, 29), (30, 30), (31, 31)):
            with self.subTest(day=day):
                preview = self.preview(due_date=f"2027-01-{day}")
                self.assertEqual([item["due_date"] for item in preview["schedule"]],
                                 [f"2027-01-{day}", "2027-02-28", f"2027-03-{march}"])

    def test_card_default_february_due_restores_configured_day(self):
        # Before this regression fix the schedule was 28/02, 28/03, 28/04.
        card = self.card(closing_day=10, due_day=31)
        entry = self.expense(method="credit", card_id=card["id"], installments=3,
                             purchase_date="2026-02-01", due_date=None)
        dates = [item["due_date"] for item in self.state["obligations"] if item["entry_id"] == entry["id"]]
        self.assertEqual(dates, ["2026-02-28", "2026-03-31", "2026-04-30"])

    def test_card_first_invoice_month_29_30_31_matches_preview_and_creation(self):
        for day in (29, 30, 31):
            with self.subTest(day=day):
                card = self.card(name=f"Cartão fictício dia {day}", closing_day=10, due_day=day)
                data = {"description": "Compra fictícia", "amount_cents": 100000, "installments": 3,
                        "method": "credit", "card_id": card["id"], "first_invoice_month": "2027-02",
                        "paid_installments": 1}
                before = deepcopy(self.state)
                preview = preview_entry(self.state, data, 1, self.today)
                self.assertEqual(before, self.state)
                expected = ["2027-02-28", f"2027-03-{day}", f"2027-04-{min(day, 30)}"]
                self.assertEqual([item["due_date"] for item in preview["schedule"]], expected)
                self.assertEqual(preview["card"], {"id": card["id"], "name": card["name"]})
                self.assertEqual(preview["modality"], "credit")
                created = self.act("entry.create", **data)["entry"]
                obligations = [item for item in self.state["obligations"] if item["entry_id"] == created["id"]]
                self.assertEqual([item["due_date"] for item in obligations], expected)
                self.assertEqual(sum(item["amount_cents"] - item["initial_paid_cents"] for item in obligations),
                                 preview["initial_debt_cents"])
                self.assertTrue(all(item["card_id"] == card["id"] and item["invoice_id"] for item in obligations))

    def test_explicit_legacy_card_due_keeps_user_anchor(self):
        card = self.card(closing_day=10, due_day=31)
        preview = self.preview(method="credit", card_id=card["id"], due_date="2027-02-27")
        self.assertEqual([item["due_date"] for item in preview["schedule"]],
                         ["2027-02-27", "2027-03-27", "2027-04-27"])

    def test_card_preview_respects_existing_manually_adjusted_invoice(self):
        card = self.card(closing_day=10, due_day=31)
        existing = self.expense(method="credit", card_id=card["id"], due_date="2026-11-30")
        self.act("invoice.update", invoice_id=self.obligation(existing)["invoice_id"], due_date="2026-11-27")
        preview = self.preview(method="credit", card_id=card["id"], due_date=None, first_invoice_month="2026-11")
        self.assertEqual(preview["schedule"][0]["due_date"], "2026-11-27")
        self.assertEqual(preview["schedule"][1]["due_date"], "2026-12-31")

    def test_first_invoice_month_cannot_link_outside_or_conflicting_due_date(self):
        card = self.card()
        before = deepcopy(self.state)
        for kwargs in ({"first_invoice_month": "2026-11"},
                       {"method": "credit", "card_id": card["id"], "first_invoice_month": "2026-11", "due_date": "2026-11-06"}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "fatura"):
                self.preview(**kwargs)
            self.assertEqual(self.state, before)

    def test_preview_is_read_only_mutate_action_and_disallows_actual_cash_or_recurrence(self):
        before = deepcopy(self.state)
        preview = self.act("entry.preview", description="Prévia fictícia", amount_cents=100000,
                           installments=3, method="transfer")
        self.assertEqual(preview["initial_debt_cents"], 100000)
        self.assertEqual(before, self.state)
        for kwargs in ({"paid": True}, {"recurrence": "monthly"}, {"kind": "income"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.preview(**kwargs)
            self.assertEqual(before, self.state)

    def test_last_october_installment_releases_150_from_1000_to_850(self):
        self.expense(description="Parcela final", amount_cents=30000, installments=2,
                     due_date="2026-09-20", paid_installments=1)
        self.expense(description="Compromissos constantes", amount_cents=85000,
                     purchase_date="2026-10-01", due_date="2026-10-25", recurrence="monthly")
        rows = self.view()["projection"]
        self.assertEqual(rows[0]["month"], "2026-10")
        self.assertEqual(rows[0]["commitment_cents"], 100000)
        self.assertEqual(rows[1]["commitment_cents"], 85000)
        self.assertEqual(rows[1]["released_cents"], 15000)
        self.assertEqual(rows[0]["ending_debts"][0]["released_cents"], 15000)

    def test_overdue_never_means_paid_or_forgiven(self):
        self.expense(due_date="2026-01-10", installments=2)
        view = self.view()
        self.assertEqual(view["debt_cents"], 10000)
        self.assertTrue(all(item["status"] == "overdue" for item in view["obligations"]))
        self.assertEqual(view["projection"][0]["commitment_cents"], 10000)
        self.assertEqual(view["balance_cents"], 500000)
        self.assertEqual(len(view["payments"]), 0)

    def test_pay_150_reduces_1000_debt_to_850(self):
        entry = self.expense(amount_cents=100000)
        self.pay(self.obligation(entry), amount_cents=15000)
        view = self.view()
        self.assertEqual(view["debt_cents"], 85000)
        self.assertEqual(view["balance_cents"], 485000)
        self.assertEqual(view["obligations"][0]["paid_cents"], 15000)
        self.assertEqual(view["obligations"][0]["status"], "partial")

    def test_invoice_payment_does_not_count_consumption_twice(self):
        card = self.card()
        self.expense(method="credit", card_id=card["id"], amount_cents=80000)
        invoice = self.state["invoices"][0]
        self.act("invoice.pay", invoice_id=invoice["id"], amount_cents=80000,
                 account_id=self.account["id"], paid_on=self.today.isoformat())
        view = self.view()
        self.assertEqual(view["reports"]["expense_cents"], 80000)
        self.assertEqual(view["reports"]["cash_expense_cents"], 80000)
        self.assertEqual(view["debt_cents"], 0)
        self.assertEqual(view["invoices"][0]["remaining_cents"], 0)
        self.assertEqual(len(view["entries"]), 1)

    def test_invoice_partial_allocates_and_preserves_remaining(self):
        card = self.card()
        self.expense(method="credit", card_id=card["id"], amount_cents=10000)
        self.expense(method="credit", card_id=card["id"], amount_cents=18500)
        self.act("invoice.pay", invoice_id=self.state["invoices"][0]["id"],
                 amount_cents=15000, account_id=self.account["id"])
        view = self.view()
        self.assertEqual(view["invoices"][0]["remaining_cents"], 13500)
        self.assertEqual(sum(item["amount_cents"] for item in view["payments"]), 15000)
        self.assertEqual(view["debt_cents"], 13500)
        self.assertEqual(view["cards"][0]["available_cents"], 986500)

    def test_invoice_cannot_overpay_or_repeat_payment(self):
        card = self.card()
        self.expense(method="credit", card_id=card["id"])
        invoice_id = self.state["invoices"][0]["id"]
        with self.assertRaisesRegex(ValueError, "excede"):
            self.act("invoice.pay", invoice_id=invoice_id, amount_cents=10001)
        self.act("invoice.pay", invoice_id=invoice_id, amount_cents=10000)
        with self.assertRaises(ValueError):
            self.act("invoice.pay", invoice_id=invoice_id, amount_cents=10000)
        self.assertEqual(len(self.state["payments"]), 1)

    def test_invoice_partial_payment_allocates_oldest_purchase_first(self):
        card = self.card()
        newer = self.expense(description="Mais recente", method="credit", card_id=card["id"],
                             purchase_date="2026-10-12", amount_cents=10000)
        older = self.expense(description="Mais antiga", method="credit", card_id=card["id"],
                             purchase_date="2026-10-02", amount_cents=10000)
        self.act("invoice.pay", invoice_id=self.obligation(newer)["invoice_id"], amount_cents=15000)
        view = self.view()
        pending = {item["entry_id"]: item["remaining_cents"] for item in view["obligations"]}
        self.assertEqual(pending[older["id"]], 0)
        self.assertEqual(pending[newer["id"]], 5000)

    def test_transfer_changes_accounts_without_income_or_expense(self):
        other = self.act("account.create", name="Carteira fictícia", reference_date="2026-01-01")["account"]
        self.act("entry.create", kind="transfer", description="Pix entre contas", method="pix",
                 amount_cents=30000, account_id=self.account["id"], destination_account_id=other["id"])
        view = self.view()
        balances = {item["id"]: item["balance_cents"] for item in view["accounts"]}
        self.assertEqual(balances[self.account["id"]], 470000)
        self.assertEqual(balances[other["id"]], 30000)
        self.assertEqual(view["balance_cents"], 500000)
        self.assertEqual(view["reports"]["income_cents"], 0)
        self.assertEqual(view["reports"]["expense_cents"], 0)
        self.assertEqual(view["reports"]["cash_income_cents"], 0)
        self.assertEqual(view["reports"]["cash_expense_cents"], 0)

    def test_transfer_cancellation_leaves_reversal_history(self):
        other = self.act("account.create", name="Outra conta", reference_date="2026-01-01")["account"]
        entry = self.act("entry.create", kind="transfer", description="Transferência", amount_cents=10000,
                         account_id=self.account["id"], destination_account_id=other["id"])["entry"]
        self.act("entry.cancel", entry_id=entry["id"], reason="Transferência desfeita")
        self.assertEqual(len(self.state["ledger"]), 4)
        self.assertEqual(self.view()["accounts"][0]["balance_cents"], 500000)
        with self.assertRaisesRegex(ValueError, "já está cancelada"):
            self.act("entry.cancel", entry_id=entry["id"], reason="Repetição")

    def test_different_cards_keep_installments_and_invoice_links(self):
        first, second = self.card(name="Cartão A"), self.card(name="Cartão B")
        entry_a = self.expense(card_id=first["id"], method="credit", amount_cents=30000, installments=3)
        entry_b = self.expense(card_id=second["id"], method="credit", amount_cents=20000, installments=2)
        for entry, card in ((entry_a, first), (entry_b, second)):
            for obligation in self.state["obligations"]:
                if obligation["entry_id"] == entry["id"]:
                    self.assertEqual(obligation["card_id"], card["id"])
                    invoice = next(item for item in self.state["invoices"] if item["id"] == obligation["invoice_id"])
                    self.assertEqual(invoice["card_id"], card["id"])
        self.assertEqual(self.view()["debt_cents"], 50000)

    def test_previous_debt_paid_parts_create_no_fictional_cash(self):
        self.expense(amount_cents=100000, installments=10, paid_installments=7, due_date="2026-03-10")
        view = self.view()
        self.assertEqual(view["debt_cents"], 30000)
        self.assertEqual(view["balance_cents"], 500000)
        self.assertEqual(view["ledger"], [])
        self.assertEqual(view["payments"], [])
        self.assertEqual(view["entries"][0]["paid_installments"], 7)
        self.assertEqual(view["entries"][0]["remaining_installments"], 3)
        self.assertEqual(view["entries"][0]["current_installment"], 8)

    def test_payment_reverse_preserves_rows_and_restores_debt(self):
        entry = self.expense()
        payment = self.pay(self.obligation(entry))
        self.act("payment.reverse", payment_id=payment["id"], reason="Confirmação incorreta")
        view = self.view()
        self.assertEqual(view["debt_cents"], 10000)
        self.assertEqual(view["balance_cents"], 500000)
        self.assertEqual(len(view["ledger"]), 2)
        self.assertTrue(view["payments"][0]["reversed"])
        self.assertTrue(any(item["action"] == "payment.reverse" for item in view["audit"]))
        with self.assertRaisesRegex(ValueError, "já foi estornado"):
            self.act("payment.reverse", payment_id=payment["id"], reason="Repetido")

    def test_cancel_unpaid_preserves_source_and_audit(self):
        entry = self.expense(amount_cents=30000, installments=3)
        self.act("entry.cancel", entry_id=entry["id"], reason="Compra cancelada")
        view = self.view()
        self.assertEqual(view["debt_cents"], 0)
        self.assertEqual(view["reports"]["expense_cents"], 0)
        self.assertEqual(len(view["entries"]), 1)
        self.assertEqual(len(view["obligations"]), 3)
        self.assertTrue(all(item["status"] == "cancelled" for item in view["obligations"]))

    def test_cannot_cancel_paid_history_without_reversal(self):
        entry = self.expense(paid=True)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "liquidadas"):
            self.act("entry.cancel", entry_id=entry["id"], reason="Não pode")
        self.assertEqual(before, self.state)

    def test_discount_prepayment_and_fee_leave_auditable_changes(self):
        entry = self.expense(amount_cents=100000, installments=2, due_date="2026-12-20")
        first = self.obligation(entry)
        self.act("obligation.adjust", obligation_id=first["id"], kind="discount",
                 amount_cents=5000, reason="Desconto de antecipação informado")
        self.act("payment.advance", obligation_id=first["id"], amount_cents=45000,
                 account_id=self.account["id"], paid_on=self.today.isoformat())
        self.act("obligation.adjust", obligation_id=self.obligation(entry, 1)["id"], kind="fee",
                 amount_cents=1000, reason="Encargo efetivamente informado")
        view = self.view()
        self.assertEqual(view["debt_cents"], 51000)
        self.assertEqual(view["balance_cents"], 455000)
        self.assertEqual(view["reports"]["expense_cents"], 96000)
        self.assertEqual(len(view["adjustments"]), 2)
        self.assertEqual(view["payments"][0]["paid_on"], "2026-10-19")

    def test_refund_paid_expense_restores_cash_and_consumption(self):
        entry = self.expense(amount_cents=10000, paid=True)
        obligation = self.obligation(entry)
        self.act("obligation.adjust", obligation_id=obligation["id"], kind="refund", amount_cents=3000,
                 reason="Devolução parcial", account_id=self.account["id"])
        view = self.view()
        self.assertEqual(view["balance_cents"], 493000)
        self.assertEqual(view["debt_cents"], 0)
        self.assertEqual(view["reports"]["expense_cents"], 7000)
        self.assertEqual(view["reports"]["cash_expense_cents"], 7000)
        self.assertEqual(view["obligations"][0]["paid_cents"], 7000)
        self.assertEqual(len(view["payments"]), 1)
        self.assertEqual(len(view["adjustments"]), 1)

    def test_refund_pending_expense_reduces_debt_without_fake_cash(self):
        entry = self.expense(amount_cents=10000)
        self.act("obligation.adjust", obligation_id=self.obligation(entry)["id"], kind="refund", amount_cents=3000,
                 reason="Cancelamento parcial antes do pagamento")
        self.assertEqual(self.view()["debt_cents"], 7000)
        self.assertEqual(self.view()["balance_cents"], 500000)
        self.assertEqual(self.state["ledger"], [])

    def test_refund_partial_payment_splits_pending_and_confirmed_cash(self):
        entry = self.expense(amount_cents=10000)
        obligation = self.obligation(entry)
        self.pay(obligation, amount_cents=6000)
        self.act("obligation.adjust", obligation_id=obligation["id"], kind="refund", amount_cents=7000,
                 reason="Reembolso superior à parte pendente", account_id=self.account["id"])
        view = self.view()
        self.assertEqual(view["debt_cents"], 0)
        self.assertEqual(view["balance_cents"], 497000)
        self.assertEqual(view["adjustments"][0]["cash_refund_cents"], 3000)
        self.assertEqual(view["obligations"][0]["paid_cents"], 3000)

    def test_refund_paid_requires_cash_account_and_cannot_fake_discount(self):
        entry = self.expense(paid=True)
        obligation = self.obligation(entry)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "conta"):
            self.act("obligation.adjust", obligation_id=obligation["id"], kind="refund", amount_cents=3000, reason="Teste")
        self.assertEqual(self.state, before)
        with self.assertRaisesRegex(ValueError, "Desconto"):
            self.act("obligation.adjust", obligation_id=obligation["id"], kind="discount", amount_cents=3000, reason="Teste")

    def test_cannot_reverse_full_payment_after_partial_cash_refund(self):
        entry = self.expense(paid=True)
        payment = self.state["payments"][0]
        self.act("obligation.adjust", obligation_id=self.obligation(entry)["id"], kind="refund", amount_cents=1000,
                 reason="Reembolso", account_id=self.account["id"])
        with self.assertRaisesRegex(ValueError, "reembolso"):
            self.act("payment.reverse", payment_id=payment["id"], reason="Inconsistente")

    def test_closing_day_and_year_transition(self):
        card = self.card()
        before = self.expense(method="credit", card_id=card["id"], purchase_date="2026-12-25", due_date=None)
        after = self.expense(method="credit", card_id=card["id"], purchase_date="2026-12-26", due_date=None)
        self.assertEqual(self.obligation(before)["due_date"], "2027-01-05")
        self.assertEqual(self.obligation(after)["due_date"], "2027-02-05")
        self.assertNotEqual(self.obligation(before)["invoice_id"], self.obligation(after)["invoice_id"])

    def test_same_month_card_due_when_due_day_follows_close(self):
        card = self.card(closing_day=10, due_day=20)
        entry = self.expense(method="credit", card_id=card["id"], purchase_date="2026-10-09", due_date=None)
        self.assertEqual(self.obligation(entry)["due_date"], "2026-10-20")

    def test_month_end_clamping_restores_anchor_and_handles_leap_year(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 1, 31), 2), date(2026, 3, 31))
        self.assertEqual(add_months(date(2028, 1, 31), 1), date(2028, 2, 29))
        entry = self.expense(due_date="2027-01-31", installments=3)
        dates = [item["due_date"] for item in self.state["obligations"] if item["entry_id"] == entry["id"]]
        self.assertEqual(dates, ["2027-01-31", "2027-02-28", "2027-03-31"])

    def test_override_invoice_dates_and_reassign_near_closing(self):
        card = self.card()
        first = self.expense(method="credit", card_id=card["id"], due_date="2026-11-05")
        second = self.expense(method="credit", card_id=card["id"], due_date="2026-12-05")
        invoice_id = self.obligation(second)["invoice_id"]
        self.act("invoice.update", invoice_id=invoice_id, obligation_ids=[self.obligation(first)["id"]],
                 due_date="2026-12-07", closing_date="2026-11-27")
        self.assertEqual(self.obligation(first)["invoice_id"], invoice_id)
        self.assertEqual(self.obligation(first)["due_date"], "2026-12-07")
        self.assertEqual(self.obligation(second)["due_date"], "2026-12-07")
        self.assertTrue(any(item["action"] == "invoice.reassign" for item in self.state["audit"]))

    def test_paid_invoice_correction_rejected_without_mutation(self):
        card = self.card()
        entry = self.expense(method="credit", card_id=card["id"])
        self.act("invoice.pay", invoice_id=self.obligation(entry)["invoice_id"], amount_cents=1000,
                 account_id=self.account["id"], paid_on=self.today.isoformat())
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "histórico"):
            self.act("invoice.update", invoice_id=self.obligation(entry)["invoice_id"], due_date="2026-10-21")
        self.assertEqual(self.state, before)

    def test_income_expected_and_received_separate_cash(self):
        entry = self.act("entry.create", kind="income", description="Receita fictícia", amount_cents=200000,
                         account_id=self.account["id"], method="pix", due_date="2026-10-30")["entry"]
        self.assertEqual(self.view()["balance_cents"], 500000)
        self.assertEqual(self.view()["income_pending_cents"], 200000)
        self.assertEqual(self.view()["projection"][0]["projected_balance_cents"], 700000)
        self.pay(self.obligation(entry), amount_cents=50000)
        self.assertEqual(self.view()["balance_cents"], 550000)
        self.assertEqual(self.view()["income_pending_cents"], 150000)
        self.assertEqual(self.view()["projection"][0]["projected_balance_cents"], 700000)

    def test_initial_balance_reference_blocks_duplicate_historical_cash(self):
        account = self.act("account.create", name="Saldo recente", reference_date="2026-10-15")["account"]
        entry = self.expense(account_id=account["id"], due_date="2026-10-10")
        with self.assertRaisesRegex(ValueError, "saldo inicial"):
            self.pay(self.obligation(entry), account_id=account["id"], paid_on="2026-10-10")

    def test_future_payment_not_allowed(self):
        entry = self.expense()
        with self.assertRaisesRegex(ValueError, "futura"):
            self.pay(self.obligation(entry), paid_on="2026-10-20")
        self.assertEqual(self.state["payments"], [])

    def test_recurring_occurrences_do_not_duplicate_after_reads_and_writes(self):
        self.expense(amount_cents=12000, due_date="2026-10-31", recurrence="monthly")
        original = deepcopy(self.state)
        view_a, view_b = self.view(), self.view()
        self.assertEqual(view_a, view_b)
        self.assertEqual(self.state, original)
        self.act("category.create", name="Categoria extra")
        obligations = self.state["obligations"]
        self.assertEqual(len({item["id"] for item in obligations}), len(obligations))
        self.assertEqual(self.view()["projection"][0]["commitment_cents"], 12000)
        self.assertEqual(self.view()["projection"][1]["commitment_cents"], 12000)

    def test_recurrence_finite_end_preserves_month_end_anchor(self):
        self.expense(amount_cents=3000, due_date="2026-10-31", recurrence={"frequency": "monthly", "end_date": "2027-01-31"})
        dates = sorted(item["due_date"] for item in self.state["obligations"])
        self.assertEqual(dates, ["2026-10-31", "2026-11-30", "2026-12-31", "2027-01-31"])
        self.assertEqual(self.view()["projection"][4]["commitment_cents"], 0)

    def test_future_recurring_estimates_do_not_change_actual_debt_with_horizon(self):
        self.expense(amount_cents=5000, recurrence="monthly")
        short = self.view(months=12)
        long = self.view(months=36)
        self.assertEqual(short["debt_cents"], 5000)
        self.assertEqual(long["debt_cents"], short["debt_cents"])
        self.assertTrue(any("sem término" in text for text in short["assumptions"]))

    def test_virtual_future_recurring_occurrence_can_be_paid_without_duplicate(self):
        self.expense(amount_cents=5000, recurrence="monthly")
        projected = self.view(months=36)
        future = next(item for item in projected["obligations"] if item["due_date"][:7] == "2028-11")
        self.act("payment.advance", obligation_id=future["id"], account_id=self.account["id"],
                 paid_on=self.today.isoformat())
        actual = self.view(months=36)
        self.assertEqual(next(item for item in actual["obligations"] if item["id"] == future["id"])["remaining_cents"], 0)
        self.assertEqual(len(actual["obligations"]), len({item["id"] for item in actual["obligations"]}))

    def test_recurrence_occurrence_change_does_not_change_following_month(self):
        entry = self.expense(amount_cents=10000, recurrence="monthly")
        self.act("recurrence.update", recurrence_id=entry["recurrence_id"], scope="occurrence",
                 entry_id=entry["id"], changes={"amount_cents": 15000})
        rows = self.view()["projection"]
        self.assertEqual(rows[0]["commitment_cents"], 15000)
        self.assertEqual(rows[1]["commitment_cents"], 10000)

    def test_recurrence_future_change_persists_into_unmaterialized_horizon(self):
        entry = self.expense(amount_cents=10000, recurrence="monthly")
        self.act("recurrence.update", recurrence_id=entry["recurrence_id"], scope="future",
                 from_date="2026-11-01", changes={"amount_cents": 15000})
        rows = self.view(months=36)["projection"]
        self.assertEqual(rows[0]["commitment_cents"], 10000)
        self.assertTrue(all(row["commitment_cents"] == 15000 for row in rows[1:]))

    def test_recurrence_cannot_modify_paid_occurrence(self):
        entry = self.expense(amount_cents=10000, recurrence="monthly", paid=True)
        with self.assertRaisesRegex(ValueError, "liquidada"):
            self.act("recurrence.update", recurrence_id=entry["recurrence_id"], scope="occurrence",
                     entry_id=entry["id"], changes={"amount_cents": 20000})

    def test_simulation_does_not_change_actual_state_or_debt(self):
        before = deepcopy(self.state)
        result = self.act("simulation", amount_cents=120000, installments=6, due_date="2026-10-25")
        self.assertEqual(self.state, before)
        self.assertEqual([row["commitment_cents"] for row in result["projection"][:7]], [20000] * 6 + [0])
        self.assertEqual(result["projection"][5]["projected_balance_cents"], 380000)
        self.assertEqual(self.view()["debt_cents"], 0)

    def test_forecast_late_window_keeps_earlier_cash_flows(self):
        self.expense(amount_cents=50000, due_date="2026-10-20")
        rows = self.view(start_month="2026-12", months=2)["projection"]
        self.assertEqual(rows[0]["commitment_cents"], 0)
        self.assertEqual(rows[0]["projected_balance_cents"], 450000)

    def test_category_subcategory_and_budget_aggregate_correctly(self):
        sub = self.act("category.create", name="Delivery", parent_id=self.food["id"])["category"]
        self.expense(category_id=sub["id"], amount_cents=12000)
        self.act("budget.set", category_id=self.food["id"], month="2026-10", amount_cents=10000)
        self.act("budget.set", category_id=self.food["id"], month="2026-10", amount_cents=11000)
        view = self.view()
        self.assertEqual(view["reports"]["by_category"][0]["id"], self.food["id"])
        self.assertEqual(view["reports"]["by_category"][0]["amount_cents"], 12000)
        self.assertEqual(view["reports"]["by_subcategory"][0]["amount_cents"], 12000)
        self.assertEqual(len(view["budgets"]), 1)
        self.assertEqual(view["budgets"][0]["spent_cents"], 12000)
        self.assertTrue(any(item["kind"] == "budget_reached" for item in view["alerts"]))

    def test_purchase_competence_and_cash_bases_are_explicit(self):
        self.expense(purchase_date="2026-09-01", competence_date="2026-10-01", amount_cents=7000, paid=True)
        view = self.view()
        self.assertEqual(view["reports"]["basis"], "purchase")
        self.assertEqual(view["reports"]["monthly"][0]["month"], "2026-09")
        self.assertEqual(view["reports_by_basis"]["competence"]["monthly"][0]["month"], "2026-10")
        self.assertEqual(view["reports"]["cash_monthly"][0]["month"], "2026-10")

    def test_internal_alerts_due_overdue_final_negative(self):
        self.expense(description="Vencida", due_date="2026-10-10", amount_cents=500000)
        self.expense(description="Final", due_date="2026-09-20", installments=2, paid_installments=1)
        kinds = {item["kind"] for item in self.view()["alerts"]}
        self.assertIn("overdue", kinds)
        self.assertIn("due_soon", kinds)
        self.assertIn("last_installment", kinds)
        self.assertIn("negative_projection", kinds)

    def test_bad_money_or_reference_errors_are_atomic(self):
        for amount in (10.5, "100", True, -1, 0, 10**15):
            before = deepcopy(self.state)
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.expense(amount_cents=amount)
            self.assertEqual(before, self.state)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "neste espaço"):
            self.expense(account_id="foreign-account")
        self.assertEqual(before, self.state)

    def test_failure_after_partial_work_rolls_back_everything(self):
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "futura"):
            self.expense(installments=3, paid=True, paid_on="2027-01-01")
        self.assertEqual(self.state, before)

    def test_card_never_accepts_sensitive_data(self):
        for key in ("number", "card_number", "cvv", "pin", "password"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.card(**{key: "do-not-store"})
        with self.assertRaises(ValueError):
            self.card(last_four="12345")
        self.assertEqual(self.state["cards"], [])

    def test_own_account_transfer_rejected(self):
        with self.assertRaisesRegex(ValueError, "diferente"):
            self.act("entry.create", kind="transfer", description="Inválida", amount_cents=1000,
                     account_id=self.account["id"], destination_account_id=self.account["id"])

    def test_serializable_state_round_trip_preserves_balances_and_projection(self):
        card = self.card()
        entry = self.expense(method="credit", card_id=card["id"], amount_cents=100000, installments=3)
        self.act("invoice.pay", invoice_id=self.obligation(entry)["invoice_id"], amount_cents=15000,
                 account_id=self.account["id"], paid_on=self.today.isoformat())
        restored = json.loads(json.dumps(self.state))
        self.assertEqual(snapshot(restored, self.today), self.view())

    def test_authorship_and_paid_by_are_separate_from_expense_owner(self):
        entry = self.expense(person_id=4)
        payment = self.pay(self.obligation(entry), paid_by=2)
        self.assertEqual(entry["created_by"], 1)
        self.assertEqual(entry["person_id"], 4)
        self.assertEqual(payment["paid_by"], 2)
        self.assertEqual(payment["created_by"], 1)

    def test_over_limit_card_is_estimate_and_not_cash(self):
        card = self.card(limit_cents=5000)
        self.expense(method="credit", card_id=card["id"], amount_cents=10000)
        view = self.view()
        self.assertEqual(view["cards"][0]["available_cents"], 0)
        self.assertEqual(view["cards"][0]["over_limit_cents"], 5000)
        self.assertEqual(view["balance_cents"], 500000)

    def test_report_month_filters_consumption_and_cash_independently(self):
        september = self.expense(description="Compra setembro paga em outubro", amount_cents=7000,
                                 purchase_date="2026-09-10", competence_date="2026-10-01")
        self.pay(self.obligation(september), paid_on="2026-10-10")
        self.expense(description="Compra outubro paga em outubro", amount_cents=11000, paid=True,
                     purchase_date="2026-10-11", paid_on="2026-10-11")
        october = self.view(report_month="2026-10")
        self.assertEqual(october["reports"]["expense_cents"], 11000)
        self.assertEqual(october["reports"]["cash_expense_cents"], 18000)
        self.assertEqual(october["reports"]["by_category"][0]["amount_cents"], 11000)
        self.assertEqual(october["reports_by_basis"]["competence"]["expense_cents"], 18000)
        september_view = self.view(report_month="2026-09")
        self.assertEqual(september_view["reports"]["expense_cents"], 7000)
        self.assertEqual(september_view["reports"]["cash_expense_cents"], 0)
        self.assertEqual(september_view["reports"]["period"], {"start": "2026-09-01", "end": "2026-09-30"})
        self.assertEqual(september_view["balance_cents"], october["balance_cents"])

    def test_future_report_month_has_no_actual_consumption_or_cash(self):
        self.expense(amount_cents=10000, recurrence="monthly")
        view = self.view(report_month="2026-12")
        self.assertEqual(view["reports"]["expense_cents"], 0)
        self.assertEqual(view["reports"]["cash_expense_cents"], 0)
        self.assertEqual(view["debt_cents"], 10000)

    def test_account_archive_preserves_cash_and_prevents_new_use(self):
        self.act("account.update", account_id=self.account["id"], name="Conta renomeada", status="archived")
        self.assertEqual(self.view()["balance_cents"], 500000)
        self.assertEqual(self.view()["accounts"][0]["name"], "Conta renomeada")
        with self.assertRaisesRegex(ValueError, "arquivado"):
            self.expense()
        self.act("account.update", account_id=self.account["id"], status="active")
        self.expense()
        self.assertEqual(self.view()["debt_cents"], 10000)

    def test_account_opening_history_cannot_be_rewritten(self):
        with self.assertRaisesRegex(ValueError, "histórico"):
            self.act("account.update", account_id=self.account["id"], opening_balance_cents=900000)
        self.assertEqual(self.view()["balance_cents"], 500000)

    def test_category_rename_archive_and_cycle_protection(self):
        self.act("category.update", category_id=self.food["id"], name="Alimentação familiar")
        self.expense()
        self.assertEqual(self.view()["reports"]["by_category"][0]["label"], "Alimentação familiar")
        sub = self.act("category.create", name="Delivery", parent_id=self.food["id"])["category"]
        with self.assertRaisesRegex(ValueError, "principal"):
            self.act("category.update", category_id=self.food["id"], parent_id=sub["id"])
        self.act("category.update", category_id=self.food["id"], status="archived")
        with self.assertRaisesRegex(ValueError, "arquivado"):
            self.expense()
        self.assertEqual(self.view()["reports"]["expense_cents"], 10000)

    def test_card_edit_rules_only_before_first_purchase_and_archive_history(self):
        card = self.card()
        self.act("card.update", card_id=card["id"], name="Renomeado", closing_day=20, due_day=28)
        self.expense(method="credit", card_id=card["id"], due_date=None)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "histórico"):
            self.act("card.update", card_id=card["id"], closing_day=21)
        self.assertEqual(before, self.state)
        self.act("card.update", card_id=card["id"], limit_cents=2000000, status="archived")
        view = self.view()
        self.assertEqual(view["cards"][0]["committed_cents"], 10000)
        self.assertEqual(view["cards"][0]["available_cents"], 1990000)
        with self.assertRaisesRegex(ValueError, "arquivado"):
            self.expense(method="credit", card_id=card["id"])

    def test_archive_future_recurrence_reference_is_rejected_until_changed(self):
        entry = self.expense(recurrence="monthly")
        with self.assertRaisesRegex(ValueError, "recorrência futura"):
            self.act("account.update", account_id=self.account["id"], status="archived")
        other = self.act("account.create", name="Conta substituta", reference_date="2026-01-01")["account"]
        self.act("recurrence.update", recurrence_id=entry["recurrence_id"], scope="future",
                 from_date=self.today.isoformat(), changes={"account_id": other["id"]})
        self.act("account.update", account_id=self.account["id"], status="archived")
        self.assertEqual(len(self.view(months=36)["projection"]), 36)

    def test_recurring_income_current_receivable_is_invariant_across_horizons(self):
        self.act("entry.create", kind="income", description="Salário fictício", amount_cents=200000,
                 account_id=self.account["id"], due_date="2026-10-30", recurrence="monthly")
        short, long = self.view(months=12), self.view(months=36)
        self.assertEqual(short["income_pending_cents"], 200000)
        self.assertEqual(long["income_pending_cents"], 200000)
        self.assertEqual(short["income_forecast_cents"], 2400000)
        self.assertEqual(long["income_forecast_cents"], 7200000)


if __name__ == "__main__":
    unittest.main()
