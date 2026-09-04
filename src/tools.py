"""The six tools the specialist agents call, split by domain.

Each tool is a plain, testable Python function wrapped with
`@function_tool`. `issue_refund` additionally carries a `tool_input_guardrail`
(see `guardrails.py`) enforcing a real business rule: no refund over $500
without a manager override. `look_up_invoice` deliberately returns a raw,
unmasked card number from the mock customer record -- an internal system
returning unmasked data is realistic, and it exists specifically so the
output guardrail in `guardrails.py` has something real to catch if an
agent's final answer echoes it back to the customer.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agents import function_tool

from .guardrails import refund_cap_guardrail

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "customers.json"
AUDIT_LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "audit_log.jsonl"

_SERVICE_STATUS = {
    "billing-portal": "operational",
    "mobile-app": "degraded",
    "authentication": "operational",
}


def _load_customers() -> list[dict[str, Any]]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _find_customer(customer_id: str) -> dict[str, Any] | None:
    return next((c for c in _load_customers() if c["customer_id"] == customer_id), None)


def _append_audit(entry: dict[str, Any]) -> None:
    entry = {**entry, "timestamp": time.time()}
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- Billing


@function_tool
def look_up_invoice(customer_id: str) -> str:
    """Look up the current invoice/balance for a customer, including
    stored payment details. Returns JSON."""
    customer = _find_customer(customer_id)
    if not customer:
        return json.dumps({"error": f"No customer found with id '{customer_id}'."})
    return json.dumps(
        {
            "customer_id": customer["customer_id"],
            "balance_usd": customer["balance_usd"],
            "last_payment_date": customer["last_payment_date"],
            "card_number": customer["card_number"],
        }
    )


@function_tool(tool_input_guardrails=[refund_cap_guardrail])
def issue_refund(customer_id: str, amount: float, reason: str, manager_override: bool = False) -> str:
    """Issue a refund to a customer. Refunds over $500 require
    manager_override=True; see the tool input guardrail on this tool."""
    _append_audit({"action": "issue_refund", "customer_id": customer_id, "amount": amount, "reason": reason})
    return json.dumps({"status": "issued", "customer_id": customer_id, "amount": amount})


# -------------------------------------------------------------- Technical


@function_tool
def check_system_status(service_name: str) -> str:
    """Check the operational status of a named internal service."""
    status = _SERVICE_STATUS.get(service_name, "unknown")
    return json.dumps({"service_name": service_name, "status": status})


@function_tool
def create_support_ticket(summary: str, severity: str) -> str:
    """File a support ticket for an issue that needs engineering follow-up."""
    ticket_id = f"TKT-{abs(hash(summary)) % 100000:05d}"
    _append_audit({"action": "create_support_ticket", "summary": summary, "severity": severity, "ticket_id": ticket_id})
    return json.dumps({"ticket_id": ticket_id, "summary": summary, "severity": severity, "status": "open"})


# ---------------------------------------------------------------- Account


@function_tool
def look_up_account(customer_id: str) -> str:
    """Look up a customer's account profile (name, email, phone, plan)."""
    customer = _find_customer(customer_id)
    if not customer:
        return json.dumps({"error": f"No customer found with id '{customer_id}'."})
    return json.dumps(
        {
            "customer_id": customer["customer_id"],
            "name": customer["name"],
            "email": customer["email"],
            "phone": customer["phone"],
            "plan": customer["plan"],
        }
    )


@function_tool
def update_contact_info(customer_id: str, field: str, new_value: str) -> str:
    """Update one field (email or phone) on a customer's contact record."""
    if field not in {"email", "phone"}:
        return json.dumps({"error": f"Unsupported field '{field}'. Use 'email' or 'phone'."})
    _append_audit({"action": "update_contact_info", "customer_id": customer_id, "field": field, "new_value": new_value})
    return json.dumps({"status": "updated", "customer_id": customer_id, "field": field, "new_value": new_value})
