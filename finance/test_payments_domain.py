"""Payment confirmation regression scenarios use fictitious in-memory data only."""

import unittest
from copy import deepcopy
from datetime import date
from unittest.mock import patch

from finance import domain


class PaymentConfirmationTests(unittest.TestCase):
    today = date(2026, 10, 21)

    def setUp(self):
        self.state = domain.new_state()
        self.account = self.act("account.create", name="Conta fictícia", opening_balance_cents=500000,
                                reference_date="2026-01-01")["account"]

    def act(self, action, **data):
        return domain.mutate(self.state, action, data, actor_id=1, today=self.today)

    def view(self):
        return domain.snapshot(self.state, self.today)

    def expense(self, **data):
        return self.act("entry.create", **{
            "description": "Compra fictícia", "amount_cents": 100000, "installments": 3,
            "method": "transfer", "account_id": self.account["id"],
            "purchase_date": "2026-10-01", "due_date": "2026-10-20", **data,
        })["entry"]

    def part(self, entry, index=0):
        return [item for item in self.state["obligations"] if item["entry_id"] == entry["id"]][index]

    def card(self):
        return self.act("card.create", name="Cartão fictício", closing_day=10, due_day=20,
                        account_id=self.account["id"], limit_cents=1000000)["card"]

    def test_full_payment_reuses_exact_pending_and_preserves_original(self):
        entry = self.expense()
        part = self.part(entry)
        original = deepcopy(entry)
        paid = self.act("obligation.pay", obligation_id=part["id"], mode="full")["payment"]
        self.assertEqual(paid["amount_cents"], 33334)
        self.assertEqual(entry, original)
        view = self.view()
        self.assertEqual(view["debt_cents"], 66666)
        self.assertEqual(view["balance_cents"], 466666)
        self.assertEqual(view["entries"][0]["paid_installments"], 1)
        self.assertEqual(view["entries"][0]["remaining_installments"], 2)
        self.assertEqual(view["entries"][0]["amount_cents"], 100000)
        self.assertEqual(view["entries"][0]["paid_cents"], 33334)

    def test_partial_then_full_uses_only_remainder_and_keeps_partial_overdue_visible(self):
        entry = self.expense()
        part = self.part(entry)
        self.act("obligation.pay", obligation_id=part["id"], mode="partial", amount_cents=12345)
        view = self.view()
        current = next(item for item in view["obligations"] if item["id"] == part["id"])
        self.assertEqual(current["status"], "overdue")
        self.assertEqual(current["payment_status"], "partial")
        self.assertTrue(current["is_overdue"])
        self.assertEqual(view["entries"][0]["paid_installments"], 0)
        preview = self.act("payment.preview", obligation_id=part["id"], mode="full")
        self.assertEqual(preview["amount_cents"], 20989)
        self.assertEqual(preview["pending_cents"], 20989)
        self.assertEqual(preview["remaining_after_cents"], 0)
        self.assertEqual(preview["paid_installments_after"], 1)
        self.assertNotIn("amount_cents", preview["commit_data"])
        self.act("obligation.pay", **preview["commit_data"])
        self.assertEqual(self.view()["debt_cents"], 66666)
        self.assertEqual(sum(item["amount_cents"] for item in self.state["payments"]), 33334)

    def test_payment_preview_is_read_only_and_shows_cash_debt_counts(self):
        entry = self.expense()
        before = deepcopy(self.state)
        preview = self.act("payment.preview", obligation_id=self.part(entry)["id"], mode="full")
        self.assertEqual(self.state, before)
        self.assertEqual(preview["original_cents"], 33334)
        self.assertEqual(preview["paid_before_cents"], 0)
        self.assertEqual(preview["paid_after_cents"], 33334)
        self.assertEqual(preview["account"]["id"], self.account["id"])
        self.assertEqual(preview["account_balance_before_cents"], 500000)
        self.assertEqual(preview["account_balance_after_cents"], 466666)
        self.assertEqual(preview["entry_debt_before_cents"], 100000)
        self.assertEqual(preview["entry_debt_after_cents"], 66666)
        self.assertEqual(preview["total_debt_after_cents"], 66666)
        self.assertEqual(preview["remaining_installments_before"], 3)
        self.assertEqual(preview["remaining_installments_after"], 2)

    def test_partial_modes_and_expected_pending_are_validated_atomically(self):
        entry = self.expense()
        part = self.part(entry)
        before = deepcopy(self.state)
        cases = ({"mode": "full", "amount_cents": 1}, {"mode": "partial"},
                 {"mode": "partial", "amount_cents": 0}, {"mode": "partial", "amount_cents": -1},
                 {"mode": "partial", "amount_cents": 33335}, {"mode": "partial", "amount_cents": 1.5},
                 {"mode": "partial", "amount_cents": True}, {"mode": "unknown"},
                 {"expected_remaining_cents": 33333})
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.act("obligation.pay", obligation_id=part["id"], **payload)
            self.assertEqual(self.state, before)

    def test_stale_confirmation_does_not_pay_newer_pending(self):
        entry = self.expense()
        part = self.part(entry)
        preview = self.act("payment.preview", obligation_id=part["id"], mode="full")
        self.act("obligation.pay", obligation_id=part["id"], mode="partial", amount_cents=1)
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "mudou"):
            self.act("obligation.pay", **preview["commit_data"])
        self.assertEqual(self.state, before)

    def test_card_obligation_requires_invoice_in_preview_and_commit(self):
        card = self.card()
        entry = self.expense(method="credit", card_id=card["id"])
        before = deepcopy(self.state)
        for action in ("payment.preview", "obligation.pay", "payment.advance"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "fatura vinculada"):
                self.act(action, obligation_id=self.part(entry)["id"])
            self.assertEqual(self.state, before)

    def test_full_invoice_payment_is_single_debt_and_single_cash_effect(self):
        card = self.card()
        entry = self.expense(method="credit", card_id=card["id"])
        invoice_id = self.part(entry)["invoice_id"]
        preview = self.act("payment.preview", invoice_id=invoice_id, mode="full")
        self.assertEqual(preview["amount_cents"], 33334)
        result = self.act("invoice.pay", **preview["commit_data"])
        self.assertEqual(sum(item["amount_cents"] for item in result["payments"]), 33334)
        self.assertTrue(all(item["invoice_id"] == invoice_id for item in result["payments"]))
        self.assertEqual(self.view()["debt_cents"], 66666)
        self.assertEqual(self.view()["balance_cents"], 466666)
        self.assertEqual(self.view()["reports"]["expense_cents"], 100000)
        self.assertEqual(len(self.state["entries"]), 1)
        self.assertEqual(len(self.state["ledger"]), 1)

    def test_invoice_partial_allocation_is_oldest_purchase_first_and_one_account(self):
        card = self.card()
        other = self.act("account.create", name="Outra fictícia", reference_date="2026-01-01")["account"]
        newer = self.expense(description="Mais recente", method="credit", card_id=card["id"],
                             amount_cents=10000, installments=1, purchase_date="2026-10-12", account_id=other["id"])
        older = self.expense(description="Mais antiga", method="credit", card_id=card["id"],
                             amount_cents=10000, installments=1, purchase_date="2026-10-02")
        invoice_id = self.part(newer)["invoice_id"]
        preview = self.act("payment.preview", invoice_id=invoice_id, mode="partial", amount_cents=15000)
        self.assertEqual([item["entry_id"] for item in preview["allocations"]], [older["id"], newer["id"]])
        self.assertEqual([item["amount_cents"] for item in preview["allocations"]], [10000, 5000])
        self.assertEqual(preview["account_id"], self.account["id"])
        self.act("invoice.pay", **preview["commit_data"])
        self.assertTrue(all(item["account_id"] == self.account["id"] for item in self.state["payments"]))
        invoice = next(item for item in self.view()["invoices"] if item["id"] == invoice_id)
        self.assertEqual(invoice["payment_status"], "partial")
        self.assertEqual(invoice["remaining_cents"], 5000)
        self.act("invoice.pay", invoice_id=invoice_id, mode="full", account_id=self.account["id"])
        self.assertEqual(self.view()["debt_cents"], 0)
        self.assertEqual(self.view()["balance_cents"], 480000)

    def test_no_implicit_arbitrary_account_and_archived_default_not_suggested(self):
        entry = self.expense(account_id=None)
        part = self.part(entry)
        preview = self.act("payment.preview", obligation_id=part["id"])
        self.assertIsNone(preview["account"])
        self.assertIsNone(preview["account_balance_after_cents"])
        self.assertNotIn("account_id", preview["commit_data"])
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "conta ativa"):
            self.act("obligation.pay", **preview["commit_data"])
        self.assertEqual(self.state, before)
        self.act("account.update", account_id=self.account["id"], status="archived")
        with self.assertRaisesRegex(ValueError, "arquivado"):
            self.act("payment.preview", obligation_id=part["id"], account_id=self.account["id"])

    def test_explicit_advance_has_separate_history_and_can_be_reversed(self):
        entry = self.expense(due_date="2026-11-30")
        part = self.part(entry)
        preview = self.act("payment.preview", obligation_id=part["id"], operation="advance")
        self.assertTrue(preview["requires_advance"])
        self.assertEqual(preview["operation"], "advance")
        payment = self.act("payment.advance", **preview["commit_data"])["payment"]
        self.assertEqual(payment["operation"], "advance")
        self.assertTrue(any(item["action"] == "obligation.advance" for item in self.state["audit"]))
        self.assertEqual(self.view()["debt_cents"], 66666)
        self.act("payment.reverse", payment_id=payment["id"], reason="Correção fictícia")
        self.assertEqual(self.view()["debt_cents"], 100000)
        self.assertEqual(self.view()["balance_cents"], 500000)
        self.assertEqual(self.view()["entries"][0]["paid_installments"], 0)
        self.assertEqual(self.state["payments"][0]["operation"], "advance")

    def test_invoice_advance_uses_invoice_and_normal_invoice_can_be_paid_early(self):
        card = self.card()
        entry = self.expense(method="credit", card_id=card["id"], due_date="2026-11-20")
        invoice_id = self.part(entry)["invoice_id"]
        preview = self.act("payment.preview", invoice_id=invoice_id, operation="advance")
        payments = self.act("payment.advance", **preview["commit_data"])["payments"]
        self.assertTrue(all(item["operation"] == "advance" and item["invoice_id"] == invoice_id for item in payments))
        current = self.expense(method="credit", card_id=card["id"], due_date="2026-10-28", installments=1)
        current_invoice = self.part(current)["invoice_id"]
        ordinary = self.act("invoice.pay", invoice_id=current_invoice, mode="full", account_id=self.account["id"])
        self.assertTrue(all(item["operation"] == "payment" for item in ordinary["payments"]))

    def test_future_month_normal_payment_rejected_but_preview_offers_explicit_advance(self):
        card = self.card()
        outside = self.expense(due_date="2026-11-30")
        credit = self.expense(method="credit", card_id=card["id"], due_date="2026-11-20")
        targets = (("obligation.pay", {"obligation_id": self.part(outside)["id"]}),
                   ("invoice.pay", {"invoice_id": self.part(credit)["invoice_id"]}))
        for action, target in targets:
            before = deepcopy(self.state)
            preview = self.act("payment.preview", **target, operation="payment")
            self.assertTrue(preview["requires_advance"])
            self.assertFalse(preview["can_confirm"])
            self.assertEqual(self.state, before)
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "operação de antecipação"):
                self.act(action, **preview["commit_data"])
            self.assertEqual(self.state, before)
            advanced = self.act("payment.preview", **target, operation="advance")
            self.assertTrue(advanced["can_confirm"])
            self.act("payment.advance", **advanced["commit_data"])

    def test_advance_rejects_due_or_overdue_and_receivables_atomically(self):
        entry = self.expense(due_date="2026-10-21")
        income = self.act("entry.create", kind="income", description="Receita fictícia", amount_cents=10000,
                          account_id=self.account["id"], due_date="2026-11-21")["entry"]
        before = deepcopy(self.state)
        for target in (self.part(entry)["id"], self.part(income)["id"]):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "Antecipação"):
                self.act("payment.advance", obligation_id=target)
            self.assertEqual(self.state, before)

    def test_adjustment_history_reconciles_original_paid_and_pending(self):
        entry = self.expense()
        part = self.part(entry)
        self.act("obligation.adjust", obligation_id=part["id"], kind="discount", amount_cents=334,
                 reason="Desconto fictício informado")
        preview = self.act("payment.preview", obligation_id=part["id"], mode="partial", amount_cents=10000)
        self.assertEqual(preview["original_amount_cents"], 33334)
        self.assertEqual(preview["adjustment_cents"], -334)
        self.assertEqual(preview["adjusted_cents"], 33000)
        self.assertEqual(preview["remaining_after_cents"], 23000)
        self.act("obligation.pay", **preview["commit_data"])
        view = self.view()
        obligation = next(item for item in view["obligations"] if item["id"] == part["id"])
        self.assertEqual(obligation["original_amount_cents"] + obligation["adjustment_cents"],
                         obligation["paid_cents"] + obligation["remaining_cents"])
        self.assertEqual(view["entries"][0]["amount_cents"], 100000)
        self.assertEqual(view["entries"][0]["adjustment_cents"], -334)

    def test_historical_paid_installments_not_repaid_or_cash_recreated(self):
        entry = self.expense(paid_installments=1, due_date="2026-09-20")
        before = self.view()
        self.assertEqual(before["debt_cents"], 66666)
        with self.assertRaisesRegex(ValueError, "quitado"):
            self.act("obligation.pay", obligation_id=self.part(entry)["id"])
        preview = self.act("payment.preview", obligation_id=self.part(entry, 1)["id"])
        self.assertEqual(preview["paid_installments_before"], 1)
        self.assertEqual(preview["paid_installments_after"], 2)
        self.act("obligation.pay", **preview["commit_data"])
        self.assertEqual(self.view()["balance_cents"], 466667)
        self.assertEqual(self.view()["entries"][0]["paid_cents"], 66667)
        self.assertEqual(len(self.state["payments"]), 1)

    def test_receiving_income_has_positive_cash_and_no_expense_debt(self):
        entry = self.act("entry.create", kind="income", description="Receita fictícia", amount_cents=12345,
                         account_id=self.account["id"], due_date="2026-10-21")["entry"]
        preview = self.act("payment.preview", obligation_id=self.part(entry)["id"], mode="full")
        self.assertEqual(preview["account_balance_after_cents"], 512345)
        self.assertEqual(preview["total_debt_before_cents"], 0)
        self.assertEqual(preview["total_debt_after_cents"], 0)
        self.act("obligation.pay", **preview["commit_data"])
        self.assertEqual(self.view()["balance_cents"], 512345)
        self.assertEqual(self.view()["income_pending_cents"], 0)

    def test_future_payment_date_and_cash_before_reference_are_rejected(self):
        entry = self.expense()
        recent = self.act("account.create", name="Conta recente fictícia", reference_date="2026-10-20")["account"]
        before = deepcopy(self.state)
        for values in ({"paid_on": "2026-10-22"}, {"paid_on": "2026-10-19", "account_id": recent["id"]}):
            for action in ("payment.preview", "obligation.pay"):
                with self.subTest(action=action, values=values), self.assertRaises(ValueError):
                    self.act(action, obligation_id=self.part(entry)["id"], **values)
                self.assertEqual(self.state, before)

    def test_failed_invoice_allocation_leaves_no_partial_payments_or_cash(self):
        card = self.card()
        first = self.expense(method="credit", card_id=card["id"], amount_cents=10000, installments=1)
        self.expense(method="credit", card_id=card["id"], amount_cents=20000, installments=1)
        before = deepcopy(self.state)
        real_ledger = domain._ledger
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise ValueError("Falha fictícia na segunda gravação")
            return real_ledger(*args, **kwargs)
        with patch("finance.domain._ledger", side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, "Falha fictícia"):
                self.act("invoice.pay", invoice_id=self.part(first)["invoice_id"], mode="full")
        self.assertEqual(self.state, before)

    def test_reversal_restores_partial_pending_cash_and_installment_count(self):
        entry = self.expense()
        part = self.part(entry)
        first = self.act("obligation.pay", obligation_id=part["id"], mode="partial", amount_cents=10000)["payment"]
        second = self.act("obligation.pay", obligation_id=part["id"], mode="full")["payment"]
        self.assertEqual(self.view()["entries"][0]["paid_installments"], 1)
        self.act("payment.reverse", payment_id=second["id"], reason="Correção fictícia")
        view = self.view()
        self.assertEqual(view["entries"][0]["paid_installments"], 0)
        self.assertEqual(view["entries"][0]["paid_cents"], 10000)
        self.assertEqual(view["debt_cents"], 90000)
        self.assertEqual(view["balance_cents"], 490000)
        self.assertFalse(next(p for p in self.state["payments"] if p["id"] == first["id"])["reversed"])
        self.assertEqual(self.state["entries"][0]["amount_cents"], 100000)

    def test_overdue_read_never_auto_pays_or_changes_state(self):
        self.expense(due_date="2026-01-31")
        before = deepcopy(self.state)
        view = self.view()
        self.assertEqual(self.state, before)
        self.assertEqual(view["debt_cents"], 100000)
        self.assertEqual(view["balance_cents"], 500000)
        self.assertTrue(all(item["is_overdue"] for item in view["obligations"]))
        self.assertTrue(all(item["payment_status"] == "pending" for item in view["obligations"]))
        self.assertEqual(self.state["payments"], [])


if __name__ == "__main__":
    unittest.main()
