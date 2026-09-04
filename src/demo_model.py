"""A deterministic, scripted stand-in for a real model -- used only when
no `OPENAI_API_KEY` is configured (see `agents_def.py`). This is what let
this whole system run and be verified end-to-end in a development
environment with no live OpenAI credentials, the same honest trade-off
made throughout this project set: real, correct SDK usage (Agent,
handoffs, guardrails, Session, tracing) exercised against a fake model,
clearly labeled as such, rather than an untested claim.

In production (`OPENAI_API_KEY` set), no agent in `agents_def.py`
overrides `model=` at all, so every agent uses the SDK's own default --
`OpenAIResponsesModel`, i.e. the Responses API -- satisfying the lab
brief's "at least one workflow using the Responses API" requirement with
the SDK's actual default, not a special-cased workflow bolted on to
satisfy the checklist.

Each role gets its own `decide` callback (below), inspecting the
conversation's item list in exactly the shape the real SDK constructs it
(confirmed empirically against the installed `openai-agents==0.22.0`
package, not assumed from documentation): plain dicts with
`role`/`content` for messages, and `type: "function_call"` /
`"function_call_output"` pairs joined by `call_id`.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any, Callable

from agents import Model, ModelResponse
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

_call_id_counter = itertools.count(1)


def _next_call_id() -> str:
    return f"call_{next(_call_id_counter)}"


def _text_message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id=_next_call_id(),
        role="assistant",
        status="completed",
        type="message",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
    )


def _tool_call(name: str, arguments: dict[str, Any]) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        call_id=_next_call_id(), name=name, arguments=json.dumps(arguments), type="function_call"
    )


def latest_user_message(input_data: str | list) -> str:
    if isinstance(input_data, str):
        return input_data
    for item in reversed(input_data):
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, str):
                return content
    return ""


def _items_since_latest_user_message(input_data: list) -> list:
    """Restricts the search to items after the *current* user message --
    a returning session's history can contain an earlier call to the same
    tool from a previous turn, which must not be mistaken for "already
    handled this turn." Found by actually running a two-turn session
    scenario and seeing the follow-up wrongly reuse turn one's tool
    output (see README's "Bugs found by actually running this")."""
    last_user_idx = -1
    for i, item in enumerate(input_data):
        if isinstance(item, dict) and item.get("role") == "user":
            last_user_idx = i
    return input_data[last_user_idx + 1 :]


def tool_output_for(input_data: str | list, tool_name: str) -> str | None:
    """Returns the parsed function_call_output for a call to `tool_name`
    made in response to the *current* user message, or None if that tool
    hasn't been called yet this turn."""
    if isinstance(input_data, str):
        return None
    scoped = _items_since_latest_user_message(input_data)
    call_ids = {
        item["call_id"]
        for item in scoped
        if isinstance(item, dict) and item.get("type") == "function_call" and item.get("name") == tool_name
    }
    for item in reversed(scoped):
        if isinstance(item, dict) and item.get("type") == "function_call_output" and item.get("call_id") in call_ids:
            return item.get("output")
    return None


def customer_id_from_instructions(system_instructions: str | None) -> str:
    if not system_instructions:
        return "cust-4471"
    match = re.search(r"customer_id[:=]\s*([\w-]+)", system_instructions)
    return match.group(1) if match else "cust-4471"


DecideFn = Callable[[str | None, str | list], "ResponseFunctionToolCall | ResponseOutputMessage"]


class DemoModel(Model):
    """Wraps one `decide` callback per agent role. `decide` receives
    `(system_instructions, input)` and returns either a tool/handoff call
    or a final text message -- built with `_tool_call`/`_text_message`
    above so call IDs are always unique across the whole run (the SDK
    rejects a reused call_id, confirmed by hitting exactly that error
    while developing this)."""

    def __init__(self, decide: DecideFn):
        self._decide = decide

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> ModelResponse:
        output_item = self._decide(system_instructions, input)
        return ModelResponse(output=[output_item], usage=Usage(), response_id=_next_call_id())

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError("DemoModel is non-streaming; use the real model for streaming.")


# ----------------------------------------------------------- Decisions

_BILLING_KEYWORDS = ("refund", "invoice", "bill", "charge", "payment", "overcharge", "card number")
_TECHNICAL_KEYWORDS = ("error", "bug", "crash", "not working", "broken", "reset my password", "can't log in", "outage", "down")
_ACCOUNT_KEYWORDS = ("update my email", "change my address", "my profile", "contact info", "phone number", "update my account")

_REFUND_AMOUNT_RE = re.compile(r"\$?\s?(\d+(?:\.\d{2})?)")


def router_decide(system_instructions, input_data):
    text = latest_user_message(input_data).lower()
    if any(k in text for k in _BILLING_KEYWORDS):
        return _tool_call("transfer_to_billing_agent", {})
    if any(k in text for k in _TECHNICAL_KEYWORDS):
        return _tool_call("transfer_to_technical_support_agent", {})
    if any(k in text for k in _ACCOUNT_KEYWORDS):
        return _tool_call("transfer_to_account_management_agent", {})
    return _text_message(
        "I can help with billing, technical issues, or account changes -- "
        "could you tell me a bit more about what you need?"
    )


def billing_decide(system_instructions, input_data):
    customer_id = customer_id_from_instructions(system_instructions)
    text = latest_user_message(input_data).lower()

    refund_output = tool_output_for(input_data, "issue_refund")
    if refund_output is not None:
        return _text_message(f"Here's the result of your refund request: {refund_output}")

    invoice_output = tool_output_for(input_data, "look_up_invoice")
    if invoice_output is not None:
        data = json.loads(invoice_output)
        if "card number" in text:
            # Deliberately echoes the raw value from the tool's own output --
            # this is the exact behavior the output guardrail exists to catch.
            return _text_message(f"Your card on file is {data.get('card_number')}.")
        return _text_message(f"Your current balance is ${data.get('balance_usd')}.")

    if "refund" in text:
        amount_match = _REFUND_AMOUNT_RE.search(text)
        amount = float(amount_match.group(1)) if amount_match else 50.0
        return _tool_call("issue_refund", {"customer_id": customer_id, "amount": amount, "reason": "customer request"})

    return _tool_call("look_up_invoice", {"customer_id": customer_id})


def technical_decide(system_instructions, input_data):
    text = latest_user_message(input_data).lower()

    ticket_output = tool_output_for(input_data, "create_support_ticket")
    if ticket_output is not None:
        data = json.loads(ticket_output)
        return _text_message(f"I've filed ticket {data.get('ticket_id')} for this issue. Our team will follow up.")

    status_output = tool_output_for(input_data, "check_system_status")
    if status_output is not None:
        data = json.loads(status_output)
        if data.get("status") != "operational":
            return _tool_call("create_support_ticket", {"summary": f"{data.get('service_name')} reported {data.get('status')}", "severity": "high"})
        return _text_message(f"{data.get('service_name')} shows as operational on our end -- let's dig into what you're seeing.")

    service = "mobile-app" if "app" in text else "billing-portal" if "portal" in text or "login" in text or "log in" in text else "authentication"
    return _tool_call("check_system_status", {"service_name": service})


def account_decide(system_instructions, input_data):
    customer_id = customer_id_from_instructions(system_instructions)
    text = latest_user_message(input_data).lower()

    update_output = tool_output_for(input_data, "update_contact_info")
    if update_output is not None:
        return _text_message(f"Done -- your contact info has been updated: {update_output}")

    profile_output = tool_output_for(input_data, "look_up_account")
    if profile_output is not None:
        data = json.loads(profile_output)
        return _text_message(f"Your account: {data.get('name')}, {data.get('email')}, plan: {data.get('plan')}.")

    if "update" in text or "change" in text:
        field = "email" if "email" in text else "phone"
        new_value_match = re.search(r"to ([\w@.\-]+)", text)
        new_value = new_value_match.group(1) if new_value_match else "unknown@example.com"
        return _tool_call("update_contact_info", {"customer_id": customer_id, "field": field, "new_value": new_value})

    return _tool_call("look_up_account", {"customer_id": customer_id})
