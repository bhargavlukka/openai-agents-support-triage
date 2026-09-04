"""Wires up the four agents, their handoffs, and all three guardrails.

Model selection: if `OPENAI_API_KEY` is set, no agent below passes a
`model=` override at all -- every agent falls back to the Agents SDK's
own default, `OpenAIResponsesModel`, which calls the real Responses API.
That satisfies the lab brief's Responses API requirement with the SDK's
actual default behavior, not a special-cased demo. If no key is
configured (this development environment's case -- see README), every
agent uses `DemoModel` (see `demo_model.py`) so the whole system can
still be built, run, and verified end to end.
"""

from __future__ import annotations

import os

from agents import Agent, RunContextWrapper, handoff

from .context import SupportContext
from .demo_model import DemoModel, account_decide, billing_decide, router_decide, technical_decide
from .guardrails import injection_guardrail, no_sensitive_data_leak_guardrail
from .tools import check_system_status, create_support_ticket, issue_refund, look_up_account, look_up_invoice, update_contact_info

_USE_REAL_MODEL = bool(os.environ.get("OPENAI_API_KEY"))


def _model_for(decide_fn):
    return None if _USE_REAL_MODEL else DemoModel(decide_fn)


def _billing_instructions(context: RunContextWrapper[SupportContext], agent: Agent) -> str:
    return (
        "You are the billing specialist for a SaaS support desk. "
        f"customer_id: {context.context.customer_id}. "
        "Use look_up_invoice to check balances and issue_refund to process refunds. "
        "Never state a customer's full card number in your reply -- reference it only "
        "as 'the card on file' or its last 4 digits."
    )


def _technical_instructions(context: RunContextWrapper[SupportContext], agent: Agent) -> str:
    return (
        "You are the technical support specialist for a SaaS support desk. "
        f"customer_id: {context.context.customer_id}. "
        "Use check_system_status to investigate reported outages before filing a ticket, "
        "and create_support_ticket when a real issue is confirmed."
    )


def _account_instructions(context: RunContextWrapper[SupportContext], agent: Agent) -> str:
    return (
        "You are the account management specialist for a SaaS support desk. "
        f"customer_id: {context.context.customer_id}. "
        "Use look_up_account to answer profile questions and update_contact_info "
        "to make changes the customer requests."
    )


def _router_instructions(context: RunContextWrapper[SupportContext], agent: Agent) -> str:
    return (
        "You are the triage router for a SaaS support desk. Classify the customer's "
        "message and hand off to the billing, technical support, or account management "
        "specialist. If the request doesn't clearly fit one of those, ask a clarifying "
        "question yourself instead of guessing."
    )


def build_agents() -> dict[str, Agent[SupportContext]]:
    billing_agent = Agent[SupportContext](
        name="Billing Agent",
        handoff_description="Handles invoices, balances, charges, and refunds.",
        instructions=_billing_instructions,
        tools=[look_up_invoice, issue_refund],
        input_guardrails=[injection_guardrail],
        output_guardrails=[no_sensitive_data_leak_guardrail],
        model=_model_for(billing_decide),
    )

    technical_agent = Agent[SupportContext](
        name="Technical Support Agent",
        handoff_description="Handles outages, errors, and bug reports.",
        instructions=_technical_instructions,
        tools=[check_system_status, create_support_ticket],
        input_guardrails=[injection_guardrail],
        model=_model_for(technical_decide),
    )

    account_agent = Agent[SupportContext](
        name="Account Management Agent",
        handoff_description="Handles profile lookups and contact-info changes.",
        instructions=_account_instructions,
        tools=[look_up_account, update_contact_info],
        input_guardrails=[injection_guardrail],
        output_guardrails=[no_sensitive_data_leak_guardrail],
        model=_model_for(account_decide),
    )

    router_agent = Agent[SupportContext](
        name="Router",
        instructions=_router_instructions,
        handoffs=[handoff(billing_agent), handoff(technical_agent), handoff(account_agent)],
        input_guardrails=[injection_guardrail],
        model=_model_for(router_decide),
    )

    return {
        "router": router_agent,
        "billing": billing_agent,
        "technical": technical_agent,
        "account": account_agent,
    }
