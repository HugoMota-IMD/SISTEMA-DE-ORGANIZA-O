"""Exact, date-only financial rules. Obligations are the sole source of debt.

All public monetary values are integer BRL cents. The storage layer must lock a
workspace and persist the complete result of ``mutate`` in one transaction.
``snapshot`` is read-only and can project monthly recurrence occurrences without
pretending that any payment happened. No bank interest is inferred.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5


COLLECTIONS = (
    "accounts", "cards", "categories", "entries", "invoices", "obligations",
    "payments", "ledger", "recurrences", "adjustments", "budgets", "audit",
)
DEFAULT_CATEGORIES = (
    "Alimentação", "Moradia", "Transporte", "Saúde", "Educação", "Lazer",
    "Compras", "Assinaturas", "Serviços", "Impostos e taxas", "Outros",
)
METHODS = {"pix", "credit", "debit", "cash", "transfer"}


def new_state():
    state = {key: [] for key in COLLECTIONS}
    state["schema_version"] = 1
    state["categories"] = [
        {"id": str(uuid4()), "name": name, "parent_id": None, "status": "active"}
        for name in DEFAULT_CATEGORIES
    ]
    return state


def _id(seed=None):
    return str(uuid5(NAMESPACE_URL, seed)) if seed else str(uuid4())


def _money(value, label="Valor", allow_zero=False, signed=False):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} deve ser informado em centavos inteiros.")
    if abs(value) > 10**14:
        raise ValueError(f"{label} excede o limite permitido.")
    if not signed and (value < 0 or (value == 0 and not allow_zero)):
        raise ValueError(f"{label} deve ser {'não negativo' if allow_zero else 'positivo'}.")
    return value


def _integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} deve ser um inteiro entre {minimum} e {maximum}.")
    return value


def _date(value, label="Data", default=None):
    if value in (None, "") and default is not None:
        return default if isinstance(default, date) else _date(default, label)
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{label} deve usar AAAA-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        raise ValueError(f"{label} deve ser uma data válida no formato AAAA-MM-DD.") from None


def _text(value, label, required=False, limit=500):
    if value is None:
        value = ""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{label} deve ser um texto com até {limit} caracteres.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Informe {label.lower()}.")
    return value


def _month(value):
    if not isinstance(value, str) or len(value) != 7:
        raise ValueError("Mês deve usar AAAA-MM.")
    return _date(value + "-01", "Mês")


def add_months(value, months):
    """Clamp a missing day to month-end; always shift the original anchor date."""
    total = value.year * 12 + value.month - 1 + months
    year, month = divmod(total, 12)
    month += 1
    if not 1900 <= year <= 9999:
        raise ValueError("Data fora do intervalo financeiro permitido.")
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _day(month, day):
    return date(month.year, month.month, min(day, calendar.monthrange(month.year, month.month)[1]))


def _find(state, collection, object_id, label=None):
    for item in state[collection]:
        if item["id"] == object_id:
            return item
    raise ValueError(f"{label or collection} não encontrado neste espaço financeiro.")


def _optional_ref(state, collection, object_id, label):
    return _find(state, collection, object_id, label) if object_id else None


def _active_ref(state, collection, object_id, label):
    item = _find(state, collection, object_id, label)
    if item.get("status") == "archived":
        raise ValueError(f"{label} está arquivado.")
    return item


def _audit(state, action, actor, today, object_id, details=None):
    item = {"id": _id(), "action": action, "actor_id": actor,
            "occurred_on": today.isoformat(), "object_id": object_id,
            "details": deepcopy(details or {})}
    state["audit"].append(item)
    return item


def _split(amount, count):
    quotient, remainder = divmod(amount, count)
    return [quotient + (index < remainder) for index in range(count)]


def _paid(state, obligation):
    paid = obligation.get("initial_paid_cents", 0)
    paid += sum(payment["amount_cents"] for payment in state["payments"]
                if payment["obligation_id"] == obligation["id"] and not payment.get("reversed"))
    paid -= sum(item.get("cash_refund_cents", 0) for item in state["adjustments"]
                if item.get("obligation_id") == obligation["id"])
    return paid


def _remaining(state, obligation):
    if obligation.get("status") == "cancelled":
        return 0
    return max(0, obligation["amount_cents"] - _paid(state, obligation))


def _incurred(obligation, entries, as_of):
    """Future recurring forecasts are commitments, not incurred card principal."""
    entry = entries[obligation["entry_id"]]
    return not entry.get("recurrence_id") or _date(entry["purchase_date"]) <= as_of


def _ledger(state, account_id, amount, occurred_on, actor, kind, entry_id=None,
            payment_id=None, adjustment_id=None):
    account = _active_ref(state, "accounts", account_id, "Conta")
    if occurred_on < _date(account["reference_date"]):
        raise ValueError("A movimentação efetiva não pode anteceder a data do saldo inicial da conta.")
    row = {"id": _id(), "account_id": account_id, "amount_cents": amount,
           "occurred_on": occurred_on.isoformat(), "created_by": actor,
           "kind": kind, "entry_id": entry_id, "payment_id": payment_id,
           "adjustment_id": adjustment_id}
    state["ledger"].append(row)
    return row


def _invoice_for(state, card, due_date):
    month = due_date.strftime("%Y-%m")
    invoice_id = _id(f"finance/invoice/{card['id']}/{month}")
    for invoice in state["invoices"]:
        if invoice["id"] == invoice_id:
            return invoice
    closing_month = due_date.replace(day=1)
    if card["due_day"] <= card["closing_day"]:
        closing_month = add_months(closing_month, -1)
    invoice = {"id": invoice_id, "card_id": card["id"], "month": month,
               "closing_date": _day(closing_month, card["closing_day"]).isoformat(),
               "due_date": due_date.isoformat()}
    state["invoices"].append(invoice)
    return invoice


def _card_due(card, purchase_date):
    closing_month = purchase_date.replace(day=1)
    if purchase_date > _day(closing_month, card["closing_day"]):
        closing_month = add_months(closing_month, 1)
    due_month = closing_month
    if card["due_day"] <= card["closing_day"]:
        due_month = add_months(due_month, 1)
    return _day(due_month, card["due_day"])


def _entry_obligations(state, entry_id):
    return [item for item in state["obligations"] if item["entry_id"] == entry_id]


def _payment_amount(data, remaining, label="obrigação"):
    """Explicit modes for the confirmation UI; legacy integer callers remain valid."""
    if remaining <= 0:
        raise ValueError("Este item já foi quitado e não possui saldo pendente.")
    if "expected_remaining_cents" in data:
        expected = _money(data["expected_remaining_cents"], "Saldo pendente conferido", allow_zero=True)
        if expected != remaining:
            raise ValueError("O saldo pendente mudou. Atualize os dados e confira novamente antes de confirmar.")
    mode = data.get("mode")
    if mode not in (None, "full", "partial"):
        raise ValueError("Escolha pagamento integral ou pagamento parcial.")
    if mode == "partial" and "amount_cents" not in data:
        raise ValueError("Informe o valor do pagamento parcial.")
    amount = _money(data.get("amount_cents", remaining), "Valor do pagamento")
    if mode == "full" and amount != remaining:
        raise ValueError("No pagamento integral, confirme o saldo pendente completo. Para outro valor, escolha pagamento parcial.")
    if amount > remaining:
        raise ValueError(f"O pagamento excede o saldo pendente da {label}.")
    return amount


def _payment_account(state, entry=None, card=None, requested=None, suggest=False):
    if requested:
        return _active_ref(state, "accounts", requested, "Conta")
    candidates = [(entry or {}).get("account_id"), (card or {}).get("account_id")]
    for account_id in candidates:
        if account_id:
            account = _find(state, "accounts", account_id, "Conta")
            if account.get("status") != "archived":
                return account
    if suggest:
        return None
    raise ValueError("Conta de pagamento: escolha uma conta ativa para confirmar o pagamento ou recebimento.")


def _pay(state, obligation, data, actor, today, allow_card=False, operation="payment"):
    if obligation.get("status") == "cancelled":
        raise ValueError("Não é possível pagar um lançamento cancelado.")
    if obligation.get("card_id") and not allow_card:
        raise ValueError("Esta parcela pertence a um cartão de crédito. Confirme o pagamento pela fatura vinculada.")
    remaining = _remaining(state, obligation)
    amount = _payment_amount(data, remaining)
    entry = _find(state, "entries", obligation["entry_id"], "Movimentação")
    card = _optional_ref(state, "cards", obligation.get("card_id"), "Cartão")
    account = _payment_account(state, entry, card, data.get("account_id"))
    account_id = account["id"]
    paid_on = _date(data.get("paid_on"), "Data do pagamento", today)
    if paid_on > today:
        raise ValueError("A confirmação não pode ter data futura; mantenha a obrigação prevista.")
    if operation == "payment" and obligation["kind"] == "expense" and obligation["due_date"][:7] > paid_on.strftime("%Y-%m"):
        raise ValueError("Use a operação de antecipação para pagar parcelas ou faturas de meses futuros.")
    if operation == "advance" and (obligation["kind"] != "expense" or paid_on >= _date(obligation["due_date"])):
        raise ValueError("Antecipação exige uma despesa com vencimento posterior à data do pagamento.")
    payment = {"id": _id(), "obligation_id": obligation["id"],
               "account_id": account_id, "amount_cents": amount,
               "paid_on": paid_on.isoformat(), "paid_by": data.get("paid_by") or actor,
               "created_by": actor, "created_on": today.isoformat(), "reversed": False,
               "notes": _text(data.get("notes"), "Observações", limit=2000),
               "operation": operation}
    state["payments"].append(payment)
    sign = 1 if obligation["kind"] == "income" else -1
    _ledger(state, account_id, sign * amount, paid_on, actor, obligation["kind"],
            entry_id=entry["id"], payment_id=payment["id"])
    _audit(state, "obligation.advance" if operation == "advance" else "obligation.pay", actor, today, payment["id"],
           {"obligation_id": obligation["id"], "amount_cents": amount, "operation": operation})
    return payment


def _create_entry(state, data, actor, today, entry_id=None, recurrence_id=None, occurrence_index=None):
    kind = data.get("kind", "expense")
    if not isinstance(kind, str) or kind not in {"income", "expense", "transfer"}:
        raise ValueError("Tipo de movimentação inválido.")
    method = data.get("method", "pix")
    if not isinstance(method, str) or method not in METHODS:
        raise ValueError("Forma de pagamento inválida.")
    amount = _money(data.get("amount_cents"))
    description = _text(data.get("description"), "Descrição", required=True)
    purchase = _date(data.get("purchase_date"), "Data da compra", today)
    competence = _date(data.get("competence_date"), "Competência", purchase)
    installments = _integer(data.get("installments", 1), "Número de parcelas", 1, 600)
    paid_installments = _integer(data.get("paid_installments", 0), "Parcelas já pagas", 0, installments)
    value_mode = data.get("value_mode", "total")
    if value_mode not in ("total", "installment"):
        raise ValueError("Escolha informar o valor total ou o valor de cada parcela.")
    if value_mode == "installment":
        installment_amount = _money(data.get("installment_amount_cents"), "Valor da parcela")
        if amount != installment_amount * installments:
            raise ValueError("O valor total deve corresponder ao valor da parcela multiplicado pela quantidade de parcelas.")
    elif data.get("installment_amount_cents") is not None:
        raise ValueError("Informe o valor da parcela somente no modo valor da parcela.")
    if amount < installments:
        raise ValueError("O total não permite parcelas de pelo menos um centavo.")
    if kind != "expense" and installments != 1:
        raise ValueError("Parcelamento está disponível para despesas.")
    if kind == "transfer" and paid_installments:
        raise ValueError("Transferência não possui parcelas históricas.")
    if "paid" in data and not isinstance(data["paid"], bool):
        raise ValueError("Confirmação de pagamento deve ser verdadeira ou falsa.")
    category = _active_ref(state, "categories", data["category_id"], "Categoria") if data.get("category_id") else None
    card = None
    account_id = data.get("account_id") or None
    if kind == "expense" and method == "credit":
        card = _active_ref(state, "cards", data.get("card_id"), "Cartão")
        if account_id:
            _active_ref(state, "accounts", account_id, "Conta")
    else:
        if data.get("card_id"):
            raise ValueError("Cartão só pode ser vinculado a despesa de crédito.")
        if method == "credit":
            raise ValueError("Crédito está disponível apenas para despesas.")
        # A pending expense is a debt before its payment account is known. The
        # account remains mandatory when money actually enters or leaves cash.
        if account_id or kind != "expense" or data.get("paid"):
            _active_ref(state, "accounts", account_id, "Conta")
    first_invoice_month = data.get("first_invoice_month")
    card_day_anchor = bool(card and (first_invoice_month or not data.get("due_date")))
    if first_invoice_month:
        if not card:
            raise ValueError("Primeira fatura só pode ser informada para cartão de crédito.")
        invoice_month = _month(first_invoice_month)
        due = _day(invoice_month, card["due_day"])
        if data.get("due_date") and _date(data["due_date"], "Primeiro vencimento") != due:
            raise ValueError("O primeiro vencimento deve corresponder ao mês da primeira fatura e ao dia do cartão.")
    else:
        due = _date(data.get("due_date"), "Primeiro vencimento", _card_due(card, purchase) if card else purchase)
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(tag, str) or len(tag) > 60 for tag in tags):
        raise ValueError("Etiquetas devem formar uma lista com até 20 textos curtos.")
    channel = data.get("channel") or ""
    if not isinstance(channel, str) or channel not in {"", "online", "presencial"}:
        raise ValueError("Canal deve ser presencial ou online.")
    entry = {"id": entry_id or _id(), "kind": kind, "description": description,
             "amount_cents": amount, "category_id": category["id"] if category else None,
             "merchant": _text(data.get("merchant"), "Estabelecimento"),
             "person_id": data.get("person_id"), "purchase_date": purchase.isoformat(),
             "competence_date": competence.isoformat(), "due_date": due.isoformat(),
             "method": method, "account_id": account_id, "card_id": card["id"] if card else None,
             "destination_account_id": data.get("destination_account_id") or None,
             "installments": installments, "initial_paid_installments": paid_installments,
             "value_mode": value_mode,
             "paid_installments": paid_installments, "notes": _text(data.get("notes"), "Observações", limit=2000),
             "tags": tags, "channel": channel, "created_by": actor,
             "created_on": today.isoformat(), "status": "active",
             "recurrence_id": recurrence_id, "occurrence_index": occurrence_index}
    if kind == "transfer":
        if not data.get("paid", True):
            raise ValueError("Nesta versão, transferências devem ser confirmadas ao registrar.")
        destination = entry["destination_account_id"]
        _active_ref(state, "accounts", destination, "Conta de destino")
        if destination == account_id:
            raise ValueError("A conta de destino deve ser diferente da origem.")
        paid_on = _date(data.get("paid_on"), "Data efetiva", due)
        if paid_on > today:
            raise ValueError("A transferência confirmada não pode ter data futura.")
        entry["paid_on"] = paid_on.isoformat()
        state["entries"].append(entry)
        _ledger(state, account_id, -amount, paid_on, actor, "transfer", entry_id=entry["id"])
        _ledger(state, destination, amount, paid_on, actor, "transfer", entry_id=entry["id"])
        return entry
    state["entries"].append(entry)
    for index, part_amount in enumerate(_split(amount, installments)):
        # A February clamp must not turn a card due on day 31 into a card due
        # on day 28 forever. Explicit legacy due-date overrides keep their
        # original anchor; existing invoice corrections still take precedence.
        part_due = (_day(add_months(due.replace(day=1), index), card["due_day"])
                    if card_day_anchor else add_months(due, index))
        invoice = _invoice_for(state, card, part_due) if card else None
        if invoice:
            part_due = _date(invoice["due_date"])
        obligation = {"id": _id(f"finance/obligation/{entry['id']}/{index}"),
                      "entry_id": entry["id"], "kind": kind, "amount_cents": part_amount,
                      "initial_paid_cents": part_amount if index < paid_installments else 0,
                      "installment": index + 1, "total_installments": installments,
                      "due_date": part_due.isoformat(), "card_id": entry["card_id"],
                      "invoice_id": invoice["id"] if invoice else None, "status": "active"}
        state["obligations"].append(obligation)
        if data.get("paid") and index >= paid_installments:
            _pay(state, obligation, {"account_id": account_id, "paid_on": data.get("paid_on"),
                                    "paid_by": data.get("paid_by")}, actor, today)
    return entry


def _occurrence_data(recurrence, index):
    data = deepcopy(recurrence["template"])
    for key in ("purchase_date", "competence_date", "due_date"):
        data[key] = add_months(_date(data[key]), index).isoformat()
    if data.get("first_invoice_month"):
        data["first_invoice_month"] = add_months(_month(data["first_invoice_month"]), index).strftime("%Y-%m")
        # Let the card's configured day determine each month's actual date.
        data.pop("due_date", None)
    for revision in recurrence.get("revisions", []):
        if index >= revision["from_index"]:
            data.update(deepcopy(revision["changes"]))
    data["paid"] = False
    data["paid_installments"] = 0
    return data


def _materialize(state, through, actor, today):
    existing = {entry["id"] for entry in state["entries"]}
    for recurrence in state["recurrences"]:
        start = _date(recurrence["template"]["due_date"])
        end = _date(recurrence["end_date"]) if recurrence.get("end_date") else through
        end = min(end, through)
        if start > end:
            continue
        count = (end.year - start.year) * 12 + end.month - start.month + 1
        if count > 1200:
            raise ValueError("Recorrência excede 100 anos; ajuste a primeira ocorrência.")
        for index in range(count):
            due = add_months(start, index)
            if due > end:
                continue
            entry_id = _id(f"finance/recurrence/{recurrence['id']}/{index}")
            if entry_id not in existing:
                _create_entry(state, _occurrence_data(recurrence, index), recurrence["created_by"],
                              today, entry_id, recurrence["id"], index)
                existing.add(entry_id)


def _resolve_virtual(state, object_id, today):
    """Resolve a UUID exposed by a long-range read-only recurrence projection."""
    if any(item["id"] == object_id for item in state["obligations"] + state["entries"]):
        return
    for recurrence in state["recurrences"]:
        for index in range(1200):
            entry_id = _id(f"finance/recurrence/{recurrence['id']}/{index}")
            obligation_id = _id(f"finance/obligation/{entry_id}/0")
            if object_id in {entry_id, obligation_id}:
                _materialize(state, add_months(_date(recurrence["template"]["due_date"]), index),
                             recurrence["created_by"], today)
                return


def _cancel_entry(state, entry, actor, today, reason):
    if entry["status"] == "cancelled":
        raise ValueError("A movimentação já está cancelada.")
    if entry["kind"] == "transfer":
        for movement in list(state["ledger"]):
            if movement.get("entry_id") == entry["id"] and movement["kind"] == "transfer":
                _ledger(state, movement["account_id"], -movement["amount_cents"], today,
                        actor, "transfer_reversal", entry_id=entry["id"])
    else:
        obligations = _entry_obligations(state, entry["id"])
        if any(_paid(state, item) for item in obligations):
            raise ValueError("Há parcelas liquidadas; estorne os pagamentos antes de cancelar ou registre um reembolso.")
        for obligation in obligations:
            obligation["status"] = "cancelled"
    entry["status"] = "cancelled"
    _audit(state, "entry.cancel", actor, today, entry["id"], {"reason": reason})


def _account_create(state, data, actor, today):
    account = {"id": _id(), "name": _text(data.get("name"), "Nome da conta", True, 100),
               "institution": _text(data.get("institution"), "Instituição", limit=100),
               "owner_id": data.get("owner_id"), "status": "active",
               "opening_balance_cents": _money(data.get("opening_balance_cents", 0), "Saldo inicial", signed=True),
               "reference_date": _date(data.get("reference_date"), "Data do saldo inicial", today).isoformat(),
               "created_by": actor, "created_on": today.isoformat()}
    if _date(account["reference_date"]) > today:
        raise ValueError("A data do saldo inicial não pode ser futura.")
    state["accounts"].append(account)
    return {"account": account, "id": account["id"]}


def _card_create(state, data, actor, today):
    last_four = _text(data.get("last_four"), "Últimos quatro dígitos", limit=4)
    if last_four and (len(last_four) != 4 or not last_four.isascii() or not last_four.isdigit()):
        raise ValueError("Informe somente os quatro últimos dígitos do cartão.")
    if any(key in data for key in ("number", "card_number", "cvv", "cvc", "pan", "password", "pin")):
        raise ValueError("Número completo, CVV e senha de cartão não podem ser armazenados.")
    account_id = data.get("account_id") or None
    if account_id:
        _active_ref(state, "accounts", account_id, "Conta")
    card = {"id": _id(), "name": _text(data.get("name"), "Apelido do cartão", True, 100),
            "institution": _text(data.get("institution"), "Instituição", limit=100),
            "holder_id": data.get("holder_id"), "last_four": last_four,
            "limit_cents": _money(data.get("limit_cents", 0), "Limite", allow_zero=True),
            "closing_day": _integer(data.get("closing_day"), "Dia de fechamento", 1, 31),
            "due_day": _integer(data.get("due_day"), "Dia de vencimento", 1, 31),
            "account_id": account_id, "status": "active", "created_by": actor,
            "created_on": today.isoformat()}
    state["cards"].append(card)
    return {"card": card, "id": card["id"]}


def _category_create(state, data, actor, today):
    name = _text(data.get("name"), "Nome da categoria", True, 100)
    parent_id = data.get("parent_id") or None
    if parent_id:
        parent = _find(state, "categories", parent_id, "Categoria superior")
        if parent.get("parent_id"):
            raise ValueError("A categoria superior deve ser uma categoria principal.")
    if any(item["name"].casefold() == name.casefold() and item.get("parent_id") == parent_id
           for item in state["categories"]):
        raise ValueError("Já existe uma categoria com esse nome e categoria superior.")
    category = {"id": _id(), "name": name, "parent_id": parent_id, "status": "active"}
    state["categories"].append(category)
    return {"category": category, "id": category["id"]}


def _future_recurrence_uses(state, field, object_id, today):
    for recurrence in state["recurrences"]:
        anchor = _date(recurrence["template"]["due_date"])
        index = max(0, (today.year - anchor.year) * 12 + today.month - anchor.month)
        if add_months(anchor, index) < today:
            index += 1
        end = _date(recurrence["end_date"]) if recurrence.get("end_date") else None
        candidates = {index} | {revision["from_index"] for revision in recurrence.get("revisions", [])
                                 if revision["from_index"] >= index}
        for candidate in candidates:
            if end and add_months(anchor, candidate) > end:
                continue
            if _occurrence_data(recurrence, candidate).get(field) == object_id:
                return True
    return False


def _status_change(state, item, collection, field, data, today):
    status = data.get("status", item.get("status", "active"))
    if not isinstance(status, str) or status not in {"active", "archived"}:
        raise ValueError("Situação deve ser ativa ou arquivada.")
    if status == "archived" and _future_recurrence_uses(state, field, item["id"], today):
        raise ValueError("Há recorrência futura vinculada; altere suas próximas ocorrências antes de arquivar.")
    item["status"] = status


def _account_update(state, data, actor, today):
    account = _find(state, "accounts", data.get("account_id"), "Conta")
    allowed = {"account_id", "name", "institution", "owner_id", "status"}
    if set(data) - allowed:
        raise ValueError("Saldo inicial e data de referência não podem ser alterados; preserve o histórico.")
    before = deepcopy(account)
    if "name" in data:
        account["name"] = _text(data["name"], "Nome da conta", True, 100)
    if "institution" in data:
        account["institution"] = _text(data["institution"], "Instituição", limit=100)
    if "owner_id" in data:
        account["owner_id"] = data["owner_id"]
    _status_change(state, account, "accounts", "account_id", data, today)
    _audit(state, "account.update", actor, today, account["id"], {"before": before, "after": account})
    return {"account": account, "id": account["id"]}


def _card_update(state, data, actor, today):
    card = _find(state, "cards", data.get("card_id"), "Cartão")
    allowed = {"card_id", "name", "institution", "holder_id", "last_four", "limit_cents",
               "account_id", "status", "closing_day", "due_day"}
    if set(data) - allowed:
        raise ValueError("Campo de cartão não permitido.")
    before = deepcopy(card)
    if any(key in data and data[key] != card[key] for key in ("closing_day", "due_day")):
        if any(item.get("card_id") == card["id"] for item in state["entries"]):
            raise ValueError("Cartão possui histórico; ajuste fechamento e vencimento na fatura correspondente.")
        for field, label in (("closing_day", "Dia de fechamento"), ("due_day", "Dia de vencimento")):
            if field in data:
                card[field] = _integer(data[field], label, 1, 31)
    if "name" in data:
        card["name"] = _text(data["name"], "Apelido do cartão", True, 100)
    if "institution" in data:
        card["institution"] = _text(data["institution"], "Instituição", limit=100)
    if "holder_id" in data:
        card["holder_id"] = data["holder_id"]
    if "last_four" in data:
        value = _text(data["last_four"], "Últimos quatro dígitos", limit=4)
        if value and (len(value) != 4 or not value.isascii() or not value.isdigit()):
            raise ValueError("Informe somente os quatro últimos dígitos do cartão.")
        card["last_four"] = value
    if "limit_cents" in data:
        card["limit_cents"] = _money(data["limit_cents"], "Limite", allow_zero=True)
    if "account_id" in data:
        account_id = data["account_id"] or None
        if account_id:
            _active_ref(state, "accounts", account_id, "Conta")
        card["account_id"] = account_id
    _status_change(state, card, "cards", "card_id", data, today)
    _audit(state, "card.update", actor, today, card["id"], {"before": before, "after": card})
    return {"card": card, "id": card["id"]}


def _category_update(state, data, actor, today):
    category = _find(state, "categories", data.get("category_id"), "Categoria")
    if set(data) - {"category_id", "name", "parent_id", "status"}:
        raise ValueError("Campo de categoria não permitido.")
    before = deepcopy(category)
    if "name" in data:
        category["name"] = _text(data["name"], "Nome da categoria", True, 100)
    if "parent_id" in data:
        parent_id = data["parent_id"] or None
        if parent_id:
            parent = _active_ref(state, "categories", parent_id, "Categoria superior")
            if parent["id"] == category["id"] or parent.get("parent_id"):
                raise ValueError("A categoria superior deve ser principal e diferente da própria categoria.")
            if any(item.get("parent_id") == category["id"] for item in state["categories"]):
                raise ValueError("Uma categoria com subcategorias não pode virar subcategoria.")
        category["parent_id"] = parent_id
    if any(item["id"] != category["id"] and item["name"].casefold() == category["name"].casefold()
           and item.get("parent_id") == category.get("parent_id") for item in state["categories"]):
        raise ValueError("Já existe uma categoria com esse nome e categoria superior.")
    _status_change(state, category, "categories", "category_id", data, today)
    _audit(state, "category.update", actor, today, category["id"], {"before": before, "after": category})
    return {"category": category, "id": category["id"]}


def _entry_create(state, data, actor, today):
    recurring = data.get("recurrence")
    if not recurring:
        entry = _create_entry(state, data, actor, today)
        return {"entry": entry, "id": entry["id"]}
    if recurring not in (True, "monthly") and not isinstance(recurring, dict):
        raise ValueError("A recorrência disponível é mensal.")
    if isinstance(recurring, dict) and recurring.get("frequency", "monthly") != "monthly":
        raise ValueError("A recorrência disponível é mensal.")
    if data.get("installments", 1) != 1 or data.get("kind") == "transfer":
        raise ValueError("Recorrência deve ser uma receita ou despesa sem parcelamento.")
    recurrence_id = _id()
    entry_id = _id(f"finance/recurrence/{recurrence_id}/0")
    entry = _create_entry(state, data, actor, today, entry_id, recurrence_id, 0)
    end_value = (recurring.get("end_date") if isinstance(recurring, dict) else None) or data.get("end_date")
    end_date = _date(end_value, "Término da recorrência") if end_value else None
    if end_date and end_date < _date(entry["due_date"]):
        raise ValueError("O término da recorrência não pode anteceder a primeira ocorrência.")
    template = deepcopy(data)
    template.pop("recurrence", None)
    template.pop("end_date", None)
    template.update({key: entry[key] for key in ("purchase_date", "competence_date", "due_date")})
    template["paid"] = False
    template["paid_installments"] = 0
    recurrence = {"id": recurrence_id, "entry_id": entry_id, "frequency": "monthly",
                  "template": template, "end_date": end_date.isoformat() if end_date else None,
                  "created_by": actor, "created_on": today.isoformat(), "revisions": []}
    state["recurrences"].append(recurrence)
    _materialize(state, add_months(today, 12), actor, today)
    return {"entry": entry, "recurrence": recurrence, "id": entry["id"]}


def preview_entry(state, data, actor_id, today=None):
    """Validate the very same creation path on an isolated, disposable state.

    The preview is a new pending expense, with historical settlements only.
    It creates no cash movement, operation, audit event or persisted document.
    Existing invoice overrides are resolved by the same helper as creation.
    """
    today = _date(today or date.today())
    if not isinstance(data, dict):
        raise ValueError("Os dados da prévia devem formar um objeto.")
    if data.get("kind", "expense") != "expense":
        raise ValueError("A prévia de parcelamento está disponível para despesas.")
    if data.get("recurrence"):
        raise ValueError("Parcelamento e recorrência mensal são cadastros diferentes; retire a recorrência da prévia.")
    if data.get("paid") not in (None, False):
        raise ValueError("Informe somente as parcelas anteriores já pagas; confirme novos pagamentos após cadastrar a dívida.")
    working = deepcopy(state)
    for key in COLLECTIONS:
        working.setdefault(key, [])
    _materialize(working, add_months(today, 12), actor_id, today)
    entry = _entry_create(working, deepcopy(data), actor_id, today)["entry"]
    invoices = {item["id"]: item for item in working["invoices"]}
    schedule = []
    for obligation in _entry_obligations(working, entry["id"]):
        invoice = invoices.get(obligation["invoice_id"])
        historical = obligation["initial_paid_cents"]
        schedule.append({
            "installment": obligation["installment"],
            "amount_cents": obligation["amount_cents"],
            "due_date": obligation["due_date"],
            "initial_paid_cents": historical,
            "remaining_cents": _remaining(working, obligation),
            "already_paid": historical == obligation["amount_cents"],
            "invoice_month": invoice["month"] if invoice else None,
            "card_id": obligation["card_id"],
        })
    card = _optional_ref(working, "cards", entry["card_id"], "Cartão")
    return {
        "entry": deepcopy(entry), "schedule": schedule,
        "total_cents": entry["amount_cents"],
        "paid_installments": entry["initial_paid_installments"],
        "remaining_installments": entry["installments"] - entry["initial_paid_installments"],
        "initial_paid_cents": sum(item["initial_paid_cents"] for item in schedule),
        "initial_debt_cents": sum(item["remaining_cents"] for item in schedule),
        "last_due_date": max(item["due_date"] for item in schedule),
        "modality": "credit" if card else "outside",
        "card": {"id": card["id"], "name": card["name"]} if card else None,
        "value_mode": entry["value_mode"],
        "date_rule": "Em meses sem o dia escolhido, vence no último dia; nos meses seguintes, o dia original é retomado. Faturas já ajustadas preservam seu vencimento.",
    }


def _invoice_pay(state, data, actor, today, operation="payment"):
    invoice = _find(state, "invoices", data.get("invoice_id"), "Fatura")
    entries = {item["id"]: item for item in state["entries"]}
    obligations = sorted((item for item in state["obligations"]
                          if item.get("invoice_id") == invoice["id"] and _remaining(state, item)),
                         key=lambda item: (item["due_date"], entries[item["entry_id"]]["purchase_date"],
                                           item["installment"], item["id"]))
    total = sum(_remaining(state, item) for item in obligations)
    amount = _payment_amount(data, total, "fatura")
    card = _find(state, "cards", invoice["card_id"], "Cartão")
    account = _payment_account(state, entries[obligations[0]["entry_id"]], card, data.get("account_id"))
    paid_on = _date(data.get("paid_on"), "Data do pagamento", today)
    if operation == "advance" and paid_on >= _date(invoice["due_date"]):
        raise ValueError("Antecipação exige uma fatura com vencimento posterior à data do pagamento.")
    payments = []
    left = amount
    for obligation in obligations:
        if not left:
            break
        part = min(left, _remaining(state, obligation))
        # Invoice-level full/partial and stale-balance checks apply to its total,
        # not to each allocation (which may be smaller than that total).
        part_data = {key: value for key, value in data.items() if key not in {"mode", "expected_remaining_cents"}}
        payment = _pay(state, obligation, {**part_data, "amount_cents": part, "account_id": account["id"]}, actor, today,
                       allow_card=True, operation=operation)
        payment["invoice_id"] = invoice["id"]
        payments.append(payment)
        left -= part
    return {"payments": payments, "invoice_id": invoice["id"], "amount_cents": amount,
            "operation": operation}


def _payment_advance(state, data, actor, today):
    if bool(data.get("invoice_id")) == bool(data.get("obligation_id")):
        raise ValueError("Escolha somente uma fatura ou uma parcela fora do cartão para antecipar.")
    if data.get("invoice_id"):
        return _invoice_pay(state, data, actor, today, operation="advance")
    obligation = _find(state, "obligations", data["obligation_id"], "Obrigação")
    payment = _pay(state, obligation, data, actor, today, operation="advance")
    return {"payment": payment, "id": payment["id"], "operation": "advance"}


def _original_obligation_amount(entry, obligation):
    quotient, remainder = divmod(entry["amount_cents"], entry["installments"])
    return quotient + (obligation["installment"] <= remainder)


def preview_payment(state, data, actor_id, today=None):
    """Read-only payment confirmation with the same exact allocation rules."""
    today = _date(today or date.today())
    if not isinstance(data, dict):
        raise ValueError("Os dados da confirmação devem formar um objeto.")
    if bool(data.get("invoice_id")) == bool(data.get("obligation_id")):
        raise ValueError("Escolha somente uma fatura ou uma obrigação para confirmar.")
    operation = data.get("operation", "payment")
    if operation not in ("payment", "advance"):
        raise ValueError("Escolha confirmação de pagamento ou antecipação.")
    working = deepcopy(state)
    for key in COLLECTIONS:
        working.setdefault(key, [])
    _materialize(working, add_months(today, 12), actor_id, today)
    if data.get("obligation_id"):
        _resolve_virtual(working, data["obligation_id"], today)
    entries = {entry["id"]: entry for entry in working["entries"]}
    invoice = None
    if data.get("invoice_id"):
        invoice = _find(working, "invoices", data["invoice_id"], "Fatura")
        card = _find(working, "cards", invoice["card_id"], "Cartão")
        linked = [item for item in working["obligations"]
                  if item.get("invoice_id") == invoice["id"] and item.get("status") != "cancelled"]
        obligations = sorted((item for item in linked if _remaining(working, item)),
                             key=lambda item: (item["due_date"], entries[item["entry_id"]]["purchase_date"],
                                               item["installment"], item["id"]))
        target_type, target_id, kind = "invoice", invoice["id"], "expense"
        description, due_date = f"{card['name']} · {invoice['month']}", invoice["due_date"]
        preferred_entry = entries[obligations[0]["entry_id"]] if obligations else None
    else:
        obligation = _find(working, "obligations", data["obligation_id"], "Obrigação")
        if obligation.get("status") == "cancelled":
            raise ValueError("Não é possível pagar um lançamento cancelado.")
        if obligation.get("card_id"):
            raise ValueError("Esta parcela pertence a um cartão de crédito. Confirme o pagamento pela fatura vinculada.")
        preferred_entry = entries[obligation["entry_id"]]
        linked, obligations, card = [obligation], [obligation], None
        target_type, target_id, kind = "obligation", obligation["id"], obligation["kind"]
        description, due_date = preferred_entry["description"], obligation["due_date"]
    pending = sum(_remaining(working, item) for item in linked)
    amount = _payment_amount(data, pending, "fatura" if invoice else "obrigação")
    paid_on = _date(data.get("paid_on"), "Data do pagamento", today)
    if paid_on > today:
        raise ValueError("A confirmação não pode ter data futura; mantenha a obrigação prevista.")
    if operation == "advance" and (kind != "expense" or paid_on >= _date(due_date)):
        raise ValueError("Antecipação exige uma despesa com vencimento posterior à data do pagamento.")
    account = _payment_account(working, preferred_entry, card, data.get("account_id"), suggest=True)
    if account and paid_on < _date(account["reference_date"]):
        raise ValueError("A movimentação efetiva não pode anteceder a data do saldo inicial da conta.")
    left, allocations = amount, []
    for obligation in obligations:
        if not left:
            break
        remaining = _remaining(working, obligation)
        part = min(left, remaining)
        allocations.append({"obligation_id": obligation["id"], "entry_id": obligation["entry_id"],
                            "description": entries[obligation["entry_id"]]["description"],
                            "installment": obligation["installment"], "total_installments": obligation["total_installments"],
                            "amount_cents": part, "pending_before_cents": remaining,
                            "pending_after_cents": remaining - part, "due_date": obligation["due_date"]})
        left -= part
    affected_ids = {item["entry_id"] for item in linked}
    affected_obligations = [item for item in working["obligations"]
                            if item["entry_id"] in affected_ids and item.get("status") != "cancelled"]
    allocated = {item["obligation_id"]: item["amount_cents"] for item in allocations}
    debt_before = sum(_remaining(working, item) for item in affected_obligations if item["kind"] == "expense")
    paid_count_before = sum(_remaining(working, item) == 0 for item in affected_obligations)
    paid_count_after = sum(_remaining(working, item) - allocated.get(item["id"], 0) == 0 for item in affected_obligations)
    total_debt = sum(_remaining(working, item) for item in working["obligations"]
                     if item["kind"] == "expense" and _incurred(item, entries, today))
    obligations_by_id = {item["id"]: item for item in obligations}
    incurred_payment = sum(item["amount_cents"] for item in allocations
                           if kind == "expense" and _incurred(obligations_by_id[item["obligation_id"]], entries, today))
    original = sum(_original_obligation_amount(entries[item["entry_id"]], item) for item in linked)
    adjusted = sum(item["amount_cents"] for item in linked)
    paid = sum(_paid(working, item) for item in linked)
    mode = data.get("mode") or ("full" if amount == pending else "partial")
    commit_data = {"invoice_id" if invoice else "obligation_id": target_id,
                   "mode": mode, "expected_remaining_cents": pending,
                   "paid_on": paid_on.isoformat(), "paid_by": data.get("paid_by") or actor_id}
    if mode == "partial":
        commit_data["amount_cents"] = amount
    if account:
        commit_data["account_id"] = account["id"]
    notes = _text(data.get("notes"), "Observações", limit=2000)
    if notes:
        commit_data["notes"] = notes
    account_balance = _balance(working, account, today) if account else None
    return {
        "target_type": target_type, "target_id": target_id, "kind": kind, "description": description,
        "due_date": due_date, "original_cents": original, "original_amount_cents": original,
        "adjusted_cents": adjusted, "adjustment_cents": adjusted - original,
        "paid_before_cents": paid, "paid_after_cents": paid + amount,
        "pending_cents": pending, "amount_cents": amount, "remaining_after_cents": pending - amount,
        "account_id": account["id"] if account else None,
        "account": {"id": account["id"], "name": account["name"]} if account else None,
        "account_balance_before_cents": account_balance,
        "account_balance_after_cents": account_balance + (amount if kind == "income" else -amount) if account else None,
        "paid_on": paid_on.isoformat(), "entry_id": preferred_entry["id"] if not invoice else None,
        "entry_debt_before_cents": debt_before,
        "entry_debt_after_cents": debt_before - amount if kind == "expense" else debt_before,
        "paid_installments_before": paid_count_before, "paid_installments_after": paid_count_after,
        "remaining_installments_before": len(affected_obligations) - paid_count_before,
        "remaining_installments_after": len(affected_obligations) - paid_count_after,
        "total_debt_before_cents": total_debt, "total_debt_after_cents": total_debt - incurred_payment,
        "allocations": allocations, "operation": operation, "mode": mode,
        "requires_advance": kind == "expense" and due_date[:7] > paid_on.strftime("%Y-%m"),
        "can_confirm": bool(account) and (operation == "advance" or kind != "expense" or due_date[:7] <= paid_on.strftime("%Y-%m")),
        "commit_data": commit_data,
    }


def _payment_reverse(state, data, actor, today):
    payment = _find(state, "payments", data.get("payment_id"), "Pagamento")
    if payment.get("reversed"):
        raise ValueError("Esse pagamento já foi estornado.")
    obligation = _find(state, "obligations", payment["obligation_id"], "Obrigação")
    if _paid(state, obligation) - payment["amount_cents"] < 0:
        raise ValueError("Há reembolso vinculado; o estorno integral excederia o valor pago líquido.")
    occurred_on = _date(data.get("occurred_on") or data.get("paid_on"), "Data do estorno", today)
    if occurred_on < _date(payment["paid_on"]) or occurred_on > today:
        raise ValueError("Data do estorno deve estar entre o pagamento e hoje.")
    reason = _text(data.get("reason"), "Motivo do estorno", required=True)
    sign = -1 if obligation["kind"] == "income" else 1
    _ledger(state, payment["account_id"], sign * payment["amount_cents"], occurred_on,
            actor, "payment_reversal", entry_id=obligation["entry_id"], payment_id=payment["id"])
    payment.update({"reversed": True, "reversed_on": occurred_on.isoformat(),
                    "reversed_by": actor, "reversal_reason": reason})
    _audit(state, "payment.reverse", actor, today, payment["id"], {"reason": reason})
    return {"payment": payment, "id": payment["id"]}


def _obligation_adjust(state, data, actor, today):
    obligation = _find(state, "obligations", data.get("obligation_id"), "Obrigação")
    if obligation.get("status") == "cancelled" or obligation["kind"] != "expense":
        raise ValueError("Ajustes exigem uma despesa ativa.")
    kind = data.get("kind") or data.get("type")
    if not isinstance(kind, str) or kind not in {"discount", "fee", "refund"}:
        raise ValueError("Ajuste deve ser desconto, encargo ou reembolso.")
    amount = _money(data.get("amount_cents"))
    reason = _text(data.get("reason"), "Motivo do ajuste", required=True)
    before = obligation["amount_cents"]
    remaining = _remaining(state, obligation)
    cash_refund = 0
    if kind == "fee":
        obligation["amount_cents"] += amount
    else:
        if amount > before:
            raise ValueError("O ajuste excede o valor da obrigação.")
        if kind == "discount" and amount > remaining:
            raise ValueError("Desconto não pode alterar valor já pago; use reembolso.")
        cash_refund = max(0, amount - remaining)
        obligation["amount_cents"] -= amount
    adjustment = {"id": _id(), "obligation_id": obligation["id"], "entry_id": obligation["entry_id"],
                  "kind": kind, "amount_cents": amount, "before_cents": before,
                  "after_cents": obligation["amount_cents"], "cash_refund_cents": cash_refund,
                  "reason": reason, "created_by": actor, "created_on": today.isoformat()}
    if cash_refund:
        account_id = data.get("account_id")
        if not account_id:
            raise ValueError("Informe a conta que recebeu o reembolso confirmado.")
        occurred_on = _date(data.get("paid_on"), "Data do reembolso", today)
        if occurred_on > today:
            raise ValueError("O reembolso confirmado não pode ter data futura.")
        _ledger(state, account_id, cash_refund, occurred_on, actor, "refund",
                entry_id=obligation["entry_id"], adjustment_id=adjustment["id"])
        adjustment.update({"account_id": account_id, "paid_on": occurred_on.isoformat()})
    state["adjustments"].append(adjustment)
    _audit(state, "obligation.adjust", actor, today, adjustment["id"], {"kind": kind, "reason": reason})
    return {"adjustment": adjustment, "obligation": obligation, "id": adjustment["id"]}


def _invoice_update(state, data, actor, today):
    invoice = _find(state, "invoices", data.get("invoice_id"), "Fatura")
    before = deepcopy(invoice)
    obligation_ids = data.get("obligation_ids") or ([data["obligation_id"]] if data.get("obligation_id") else [])
    if not isinstance(obligation_ids, list):
        raise ValueError("As parcelas da fatura devem formar uma lista.")
    for object_id in obligation_ids:
        obligation = _find(state, "obligations", object_id, "Obrigação")
        if obligation.get("card_id") != invoice["card_id"] or obligation.get("status") == "cancelled":
            raise ValueError("Só é possível atribuir parcelas ativas do mesmo cartão à fatura.")
        if _paid(state, obligation):
            raise ValueError("Uma parcela liquidada não pode ser movida de fatura.")
        old_invoice = obligation.get("invoice_id")
        obligation.update({"invoice_id": invoice["id"], "due_date": invoice["due_date"]})
        _audit(state, "invoice.reassign", actor, today, obligation["id"],
               {"from_invoice_id": old_invoice, "to_invoice_id": invoice["id"]})
    if data.get("due_date"):
        due = _date(data["due_date"], "Vencimento da fatura")
        linked = [item for item in state["obligations"] if item.get("invoice_id") == invoice["id"]]
        if any(_paid(state, item) for item in linked):
            raise ValueError("Não altere o vencimento de fatura com pagamento; preserve o histórico.")
        invoice["due_date"] = due.isoformat()
        for obligation in linked:
            obligation["due_date"] = due.isoformat()
    if data.get("closing_date"):
        invoice["closing_date"] = _date(data["closing_date"], "Fechamento da fatura").isoformat()
    if _date(invoice["closing_date"]) > _date(invoice["due_date"]):
        raise ValueError("O fechamento não pode ser posterior ao vencimento da fatura.")
    _audit(state, "invoice.update", actor, today, invoice["id"], {"before": before, "after": invoice})
    return {"invoice": invoice, "id": invoice["id"]}


def _budget_set(state, data, actor, today):
    category = _find(state, "categories", data.get("category_id"), "Categoria")
    month = _month(data.get("month")).strftime("%Y-%m")
    amount = _money(data.get("amount_cents"), "Orçamento", allow_zero=True)
    budget = next((item for item in state["budgets"]
                   if item["category_id"] == category["id"] and item["month"] == month), None)
    if budget is None:
        budget = {"id": _id(), "category_id": category["id"], "month": month}
        state["budgets"].append(budget)
    budget.update({"amount_cents": amount, "updated_by": actor, "updated_on": today.isoformat()})
    return {"budget": budget, "id": budget["id"]}


def _recurrence_update(state, data, actor, today):
    recurrence = _find(state, "recurrences", data.get("recurrence_id"), "Recorrência")
    scope = data.get("scope")
    if not isinstance(scope, str) or scope not in {"occurrence", "future"}:
        raise ValueError("Escolha editar esta ocorrência ou as futuras.")
    changes = data.get("changes", {})
    allowed = {"amount_cents", "description", "merchant", "category_id", "person_id", "account_id", "notes", "tags", "channel"}
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        raise ValueError("Informe mudanças em valor, descrição, classificação, pessoa, conta ou observações.")
    if "amount_cents" in changes:
        _money(changes["amount_cents"])
    if changes.get("category_id"):
        _active_ref(state, "categories", changes["category_id"], "Categoria")
    if changes.get("account_id"):
        _active_ref(state, "accounts", changes["account_id"], "Conta")
    if "description" in changes:
        changes["description"] = _text(changes["description"], "Descrição", True)
    if "merchant" in changes:
        changes["merchant"] = _text(changes["merchant"], "Estabelecimento")
    if "notes" in changes:
        changes["notes"] = _text(changes["notes"], "Observações", limit=2000)
    if "channel" in changes and (not isinstance(changes["channel"], str) or changes["channel"] not in {"", "online", "presencial"}):
        raise ValueError("Canal deve ser presencial ou online.")
    if "tags" in changes and (not isinstance(changes["tags"], list) or len(changes["tags"]) > 20
                              or any(not isinstance(tag, str) or len(tag) > 60 for tag in changes["tags"])):
        raise ValueError("Etiquetas devem formar uma lista com até 20 textos curtos.")
    if scope == "occurrence":
        _resolve_virtual(state, data.get("entry_id"), today)
        entry = _find(state, "entries", data.get("entry_id"), "Ocorrência")
        if entry.get("recurrence_id") != recurrence["id"]:
            raise ValueError("A ocorrência não pertence a essa recorrência.")
        targets = [entry]
        from_index = entry["occurrence_index"]
    else:
        from_date = _date(data.get("from_date"), "Início das mudanças futuras", today)
        start = _date(recurrence["template"]["due_date"])
        from_index = max(0, (from_date.year - start.year) * 12 + from_date.month - start.month)
        if add_months(start, from_index) < from_date:
            from_index += 1
        targets = [item for item in state["entries"] if item.get("recurrence_id") == recurrence["id"]
                   and item["occurrence_index"] >= from_index]
    for entry in targets:
        if entry["status"] == "cancelled" or any(_paid(state, item) for item in _entry_obligations(state, entry["id"])):
            raise ValueError("Uma ocorrência liquidada ou cancelada não pode ser alterada silenciosamente.")
    if scope == "future":
        recurrence["revisions"].append({"from_index": from_index, "changes": deepcopy(changes),
                                        "created_by": actor, "created_on": today.isoformat()})
    for entry in targets:
        before = {key: entry.get(key) for key in changes}
        entry.update(deepcopy(changes))
        if "amount_cents" in changes:
            _entry_obligations(state, entry["id"])[0]["amount_cents"] = changes["amount_cents"]
        _audit(state, "recurrence.update", actor, today, entry["id"],
               {"scope": scope, "before": before, "changes": changes})
    _audit(state, "recurrence.rule", actor, today, recurrence["id"],
           {"scope": scope, "from_index": from_index, "changes": changes})
    return {"recurrence": recurrence, "updated_entries": len(targets), "id": recurrence["id"]}


def mutate(state, action, data, actor_id, today=None):
    """Validate and apply one operation. Even an error leaves ``state`` intact."""
    today = _date(today or date.today())
    if not isinstance(data, dict):
        raise ValueError("Os dados da operação devem formar um objeto.")
    if action == "entry.preview":
        return preview_entry(state, data, actor_id, today)
    if action == "payment.preview":
        return preview_payment(state, data, actor_id, today)
    working = deepcopy(state)
    for key in COLLECTIONS:
        working.setdefault(key, [])
    if action == "simulation":
        return _simulation(working, data, today)
    _materialize(working, add_months(today, 12), actor_id, today)
    if action in {"obligation.pay", "obligation.adjust", "payment.advance"}:
        _resolve_virtual(working, data.get("obligation_id"), today)
    elif action == "entry.cancel":
        _resolve_virtual(working, data.get("entry_id"), today)
    operations = {"account.create": _account_create, "account.update": _account_update,
                  "card.create": _card_create, "card.update": _card_update,
                  "category.update": _category_update,
                  "category.create": _category_create, "entry.create": _entry_create,
                  "invoice.pay": _invoice_pay, "payment.reverse": _payment_reverse,
                  "payment.advance": _payment_advance,
                  "obligation.adjust": _obligation_adjust, "invoice.update": _invoice_update,
                  "budget.set": _budget_set, "recurrence.update": _recurrence_update}
    if action == "obligation.pay":
        obligation = _find(working, "obligations", data.get("obligation_id"), "Obrigação")
        payment = _pay(working, obligation, data, actor_id, today)
        result = {"payment": payment, "id": payment["id"]}
    elif action == "entry.cancel":
        entry = _find(working, "entries", data.get("entry_id"), "Movimentação")
        _cancel_entry(working, entry, actor_id, today, _text(data.get("reason"), "Motivo", required=True))
        result = {"entry": entry, "id": entry["id"]}
    elif action in operations:
        result = operations[action](working, deepcopy(data), actor_id, today)
    else:
        raise ValueError("Operação financeira desconhecida.")
    _audit(working, action, actor_id, today, result.get("id"), {"summary": "Operação confirmada"})
    state.clear()
    state.update(working)
    return deepcopy(result)


def _balance(state, account, as_of):
    if _date(account["reference_date"]) > as_of:
        return 0
    return account["opening_balance_cents"] + sum(
        row["amount_cents"] for row in state["ledger"]
        if row["account_id"] == account["id"] and _date(row["occurred_on"]) <= as_of)


def _projection(state, as_of, months, start_month, balance):
    start = _month(start_month) if start_month else as_of.replace(day=1)
    if start < as_of.replace(day=1):
        raise ValueError("A projeção começa no mês atual ou em um mês futuro.")
    income = defaultdict(int)
    commitments = defaultdict(int)
    debts = defaultdict(list)
    for obligation in state["obligations"]:
        remaining = _remaining(state, obligation)
        if not remaining:
            continue
        due = max(_date(obligation["due_date"]), as_of)
        key = due.strftime("%Y-%m")
        (income if obligation["kind"] == "income" else commitments)[key] += remaining
    for entry in state["entries"]:
        if entry["kind"] != "expense" or entry["status"] == "cancelled" or entry.get("recurrence_id"):
            continue
        obligations = _entry_obligations(state, entry["id"])
        pending = [item for item in obligations if _remaining(state, item)]
        if pending and entry["installments"] > 1:
            final = max(pending, key=lambda item: item["due_date"])
            end_month = max(_date(final["due_date"]), as_of).strftime("%Y-%m")
            debts[end_month].append({"id": entry["id"], "description": entry["description"],
                                     "released_cents": _remaining(state, final),
                                     "planned": True})
    rows = []
    running = balance
    # Future windows retain cash flows between today and their first displayed month.
    cursor = as_of.replace(day=1)
    while cursor < start:
        key = cursor.strftime("%Y-%m")
        running += income[key] - commitments[key]
        cursor = add_months(cursor, 1)
    previous = commitments[add_months(start, -1).strftime("%Y-%m")]
    for index in range(months):
        key = add_months(start, index).strftime("%Y-%m")
        running += income[key] - commitments[key]
        rows.append({"month": key, "income_cents": income[key],
                     "commitment_cents": commitments[key], "projected_balance_cents": running,
                     "released_cents": max(0, previous - commitments[key]) if index else 0,
                     "ending_debts": debts[key]})
        previous = commitments[key]
    return rows


def _reports(state, as_of, basis="purchase", report_month=None):
    period_start = _month(report_month) if report_month else None
    period_end = min(add_months(period_start, 1) - timedelta(days=1), as_of) if period_start else as_of
    categories = {item["id"]: item for item in state["categories"]}
    cards = {item["id"]: item for item in state["cards"]}
    groups = {key: defaultdict(int) for key in ("category", "subcategory", "merchant", "person", "card", "method")}
    monthly = defaultdict(lambda: {"income_cents": 0, "expense_cents": 0})
    expense, income = 0, 0
    for entry in state["entries"]:
        if entry["status"] == "cancelled" or entry["kind"] == "transfer":
            continue
        financial_date = _date(entry["competence_date"] if basis == "competence" else entry["purchase_date"])
        if financial_date > period_end or (period_start and financial_date < period_start):
            continue
        amount = sum(item["amount_cents"] for item in _entry_obligations(state, entry["id"])
                     if item.get("status") != "cancelled")
        monthly[financial_date.strftime("%Y-%m")][entry["kind"] + "_cents"] += amount
        if entry["kind"] == "income":
            income += amount
            continue
        expense += amount
        category = categories.get(entry.get("category_id"))
        if category and category.get("parent_id"):
            groups["subcategory"][category["id"]] += amount
            groups["category"][category["parent_id"]] += amount
        else:
            groups["category"][entry.get("category_id") or "unclassified"] += amount
        groups["merchant"][entry.get("merchant") or "Não informado"] += amount
        groups["person"][entry.get("person_id") or "unassigned"] += amount
        if entry.get("card_id"):
            groups["card"][entry["card_id"]] += amount
        groups["method"][entry["method"]] += amount
    cash_income, cash_expense = 0, 0
    cash_monthly = defaultdict(lambda: {"income_cents": 0, "expense_cents": 0})
    entry_lookup = {item["id"]: item for item in state["entries"]}
    for movement in state["ledger"]:
        occurred_on = _date(movement["occurred_on"])
        entry = entry_lookup.get(movement.get("entry_id"))
        if (occurred_on > period_end or (period_start and occurred_on < period_start)
                or not entry or entry["kind"] == "transfer"):
            continue
        amount = movement["amount_cents"]
        month = occurred_on.strftime("%Y-%m")
        if entry["kind"] == "income":
            cash_income += amount
            cash_monthly[month]["income_cents"] += amount
        else:
            cash_expense -= amount
            cash_monthly[month]["expense_cents"] -= amount
    result = {"basis": basis, "period": {"start": period_start.isoformat() if period_start else None,
                                         "end": period_end.isoformat()},
              "income_cents": income, "expense_cents": expense,
              "cash_income_cents": cash_income, "cash_expense_cents": cash_expense,
              "monthly": [{"month": key, **value} for key, value in sorted(monthly.items())],
              "cash_monthly": [{"month": key, **value} for key, value in sorted(cash_monthly.items())]}
    for group, values in groups.items():
        rows = []
        for key, value in values.items():
            label = str(key)
            if group in {"category", "subcategory"}:
                label = categories.get(key, {}).get("name", "Sem categoria")
            elif group == "card":
                label = cards.get(key, {}).get("name", "Sem cartão")
            elif group == "person" and key == "unassigned":
                label = "Não informado"
            rows.append({"id": key, "label": label, "amount_cents": value})
        result["by_" + group] = sorted(rows, key=lambda row: (-row["amount_cents"], row["label"]))
    return result


def _assumptions(state):
    assumptions = [
        "Projeção inclui obrigações conhecidas e recorrências mensais configuradas; novos gastos não são presumidos.",
        "Atrasos são carregados para o mês atual. Vencimento e término previsto não confirmam quitação.",
        "Pagamentos previstos reduzem o saldo projetado, mas apenas confirmações alteram o saldo realizado.",
        "Dias inexistentes usam o último dia do mês; parcelas seguintes preservam o dia original.",
        "Limite estimado é o limite informado menos todas as parcelas de crédito ainda pendentes, inclusive futuras.",
        "Compras no dia do fechamento entram na fatura que fecha naquele dia; a atribuição pode ser corrigida.",
        "Não são estimados juros, correção bancária nem receitas ou despesas de valor desconhecido.",
    ]
    if any(not item.get("end_date") for item in state["recurrences"]):
        assumptions.append("Há recorrência sem término; não é possível prometer uma data para ficar sem dívidas.")
    return assumptions


def snapshot(state, as_of=None, months=12, start_month=None, report_month=None):
    """Return a read-only financial view, never confirm an expected payment."""
    as_of = _date(as_of or date.today())
    months = _integer(months, "Meses da projeção", 1, 120)
    start = _month(start_month) if start_month else as_of.replace(day=1)
    if start < as_of.replace(day=1):
        raise ValueError("A projeção começa no mês atual ou em um mês futuro.")
    view = deepcopy(state)
    for key in COLLECTIONS:
        view.setdefault(key, [])
    through = add_months(start, months).replace(day=1) - timedelta(days=1)
    _materialize(view, through, None, as_of)
    for account in view["accounts"]:
        account["balance_cents"] = _balance(view, account, as_of)
    balance = sum(item["balance_cents"] for item in view["accounts"])
    entries = {item["id"]: item for item in view["entries"]}
    for obligation in view["obligations"]:
        obligation["paid_cents"] = _paid(view, obligation)
        obligation["remaining_cents"] = _remaining(view, obligation)
        entry = entries[obligation["entry_id"]]
        obligation["original_amount_cents"] = _original_obligation_amount(entry, obligation)
        obligation["adjustment_cents"] = obligation["amount_cents"] - obligation["original_amount_cents"]
        obligation["forecast"] = not _incurred(obligation, entries, as_of)
        for field in ("description", "category_id", "merchant", "person_id", "method", "account_id"):
            obligation[field] = entry.get(field)
        obligation["created_by"] = entry["created_by"]
        if obligation["status"] != "cancelled":
            obligation["status"] = (
                "paid" if not obligation["remaining_cents"] else
                "overdue" if _date(obligation["due_date"]) < as_of else
                "partial" if obligation["paid_cents"] else "pending")
        obligation["is_overdue"] = bool(obligation["remaining_cents"] and _date(obligation["due_date"]) < as_of)
        obligation["payment_status"] = ("cancelled" if obligation["status"] == "cancelled" else
                                         "paid" if not obligation["remaining_cents"] else
                                         "partial" if obligation["paid_cents"] else "pending")
    for entry in view["entries"]:
        obligations = _entry_obligations(view, entry["id"])
        pending = [item for item in obligations if item["remaining_cents"]]
        entry["forecast"] = bool(entry.get("recurrence_id") and _date(entry["purchase_date"]) > as_of)
        entry["debt_cents"] = sum(item["remaining_cents"] for item in pending) if entry["kind"] == "expense" and not entry["forecast"] else 0
        entry["pending_cents"] = sum(item["remaining_cents"] for item in pending)
        entry["paid_installments"] = sum(item["status"] == "paid" for item in obligations)
        entry["remaining_installments"] = len(pending)
        entry["next_due_date"] = min((item["due_date"] for item in pending), default=None)
        entry["last_due_date"] = max((item["due_date"] for item in obligations), default=None)
        entry["current_installment"] = min((item["installment"] for item in pending), default=entry["installments"])
        entry["paid_cents"] = sum(item["paid_cents"] for item in obligations)
        entry["adjusted_amount_cents"] = sum(item["amount_cents"] for item in obligations)
        entry["adjustment_cents"] = entry["adjusted_amount_cents"] - entry["amount_cents"] if obligations else 0
        entry["is_overdue"] = any(item["is_overdue"] for item in pending)
        entry["payment_status"] = ("cancelled" if entry["status"] == "cancelled" else
                                    "paid" if not pending else "partial" if entry["paid_cents"] else "pending")
    for invoice in view["invoices"]:
        linked = [item for item in view["obligations"] if item.get("invoice_id") == invoice["id"] and item["status"] != "cancelled"]
        invoice["amount_cents"] = sum(item["amount_cents"] for item in linked)
        invoice["paid_cents"] = sum(item["paid_cents"] for item in linked)
        invoice["remaining_cents"] = sum(item["remaining_cents"] for item in linked)
        invoice["obligation_ids"] = [item["id"] for item in linked]
        invoice["status"] = ("paid" if not invoice["remaining_cents"] else
                             "overdue" if _date(invoice["due_date"]) < as_of else
                             "partial" if invoice["paid_cents"] else "pending")
        invoice["original_amount_cents"] = sum(item["original_amount_cents"] for item in linked)
        invoice["adjustment_cents"] = invoice["amount_cents"] - invoice["original_amount_cents"]
        invoice["is_overdue"] = bool(invoice["remaining_cents"] and _date(invoice["due_date"]) < as_of)
        invoice["payment_status"] = ("paid" if not invoice["remaining_cents"] else
                                      "partial" if invoice["paid_cents"] else "pending")
    for card in view["cards"]:
        card["committed_cents"] = sum(item["remaining_cents"] for item in view["obligations"]
                                      if item.get("card_id") == card["id"] and _incurred(item, entries, as_of))
        card["available_cents"] = max(0, card["limit_cents"] - card["committed_cents"])
        card["over_limit_cents"] = max(0, card["committed_cents"] - card["limit_cents"])
        card["limit_estimated"] = True
    view["as_of"] = as_of.isoformat()
    view["balance_cents"] = balance
    view["debt_cents"] = sum(item["remaining_cents"] for item in view["obligations"]
                             if item["kind"] == "expense" and _incurred(item, entries, as_of))
    view["debt_basis"] = "Obrigações registradas; recorrências futuras entram na projeção quando previstas, sem aumentar a dívida atual."
    view["income_pending_cents"] = sum(item["remaining_cents"] for item in view["obligations"]
                                      if item["kind"] == "income" and _incurred(item, entries, as_of))
    current_month = as_of.strftime("%Y-%m")
    view["month_commitment_cents"] = sum(item["remaining_cents"] for item in view["obligations"]
                                         if item["kind"] == "expense" and item["due_date"][:7] <= current_month)
    view["projection"] = _projection(view, as_of, months, start_month, balance)
    view["income_forecast_cents"] = sum(row["income_cents"] for row in view["projection"])
    view["reports"] = _reports(view, as_of, report_month=report_month)
    view["reports_by_basis"] = {"purchase": view["reports"],
                                "competence": _reports(view, as_of, "competence", report_month)}
    view["assumptions"] = _assumptions(view)
    alerts = []
    for obligation in view["obligations"]:
        if not obligation["remaining_cents"]:
            continue
        days = (_date(obligation["due_date"]) - as_of).days
        label = "recebimento" if obligation["kind"] == "income" else "pagamento"
        if days < 0:
            alerts.append({"kind": "overdue", "message": f"{obligation['description']}: {label} vencido.", "object_id": obligation["id"]})
        elif days <= 7:
            alerts.append({"kind": "due_soon", "message": f"{obligation['description']}: {label} em até sete dias.", "object_id": obligation["id"]})
        if obligation["total_installments"] > 1 and obligation["installment"] == obligation["total_installments"] and 0 <= days <= 31:
            alerts.append({"kind": "last_installment", "message": f"Última parcela prevista: {obligation['description']}.", "object_id": obligation["id"]})
    for invoice in view["invoices"]:
        if invoice["remaining_cents"] and 0 <= (_date(invoice["due_date"]) - as_of).days <= 7:
            alerts.append({"kind": "invoice_due", "message": "Fatura de cartão vence em até sete dias.", "object_id": invoice["id"]})
    categories = {item["id"]: item for item in view["categories"]}
    for budget in view["budgets"]:
        spent = 0
        for entry in view["entries"]:
            category = categories.get(entry.get("category_id"), {})
            if (entry["kind"] == "expense" and entry["status"] != "cancelled"
                    and entry["purchase_date"][:7] == budget["month"] and entry["purchase_date"] <= as_of.isoformat()
                    and budget["category_id"] in {entry.get("category_id"), category.get("parent_id")}):
                spent += entry["adjusted_amount_cents"]
        budget["spent_cents"] = spent
        budget["remaining_cents"] = budget["amount_cents"] - spent
        if spent >= budget["amount_cents"] and budget["month"] == current_month:
            alerts.append({"kind": "budget_reached", "message": f"Orçamento atingido: {categories[budget['category_id']]['name']}.", "object_id": budget["id"]})
    for row in view["projection"]:
        if row["projected_balance_cents"] < 0:
            alerts.append({"kind": "negative_projection", "message": f"Saldo projetado negativo em {row['month']}.", "object_id": row["month"]})
    view["alerts"] = alerts
    return view


def _simulation(state, data, today):
    amount = _money(data.get("amount_cents"))
    installments = _integer(data.get("installments", 1), "Número de parcelas", 1, 600)
    if amount < installments:
        raise ValueError("O total não permite parcelas de pelo menos um centavo.")
    due = _date(data.get("due_date"), "Primeiro vencimento", today)
    view = snapshot(state, today, data.get("months", 12), data.get("start_month"))
    extra = defaultdict(int)
    for index, part in enumerate(_split(amount, installments)):
        extra[max(add_months(due, index), today).strftime("%Y-%m")] += part
    cumulative = 0
    start_key = view["projection"][0]["month"]
    cumulative += sum(value for key, value in extra.items() if key < start_key)
    previous = None
    for row in view["projection"]:
        row["simulation_cents"] = extra[row["month"]]
        row["commitment_cents"] += row["simulation_cents"]
        cumulative += row["simulation_cents"]
        row["projected_balance_cents"] -= cumulative
        row["released_cents"] = max(0, previous - row["commitment_cents"]) if previous is not None else 0
        previous = row["commitment_cents"]
    return {"projection": view["projection"], "assumptions": view["assumptions"] + ["Simulação não cria dívida, pagamento ou movimentação real."],
            "amount_cents": amount, "installments": installments}
