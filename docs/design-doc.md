# Design Document

## What this is

A multi-agent customer support triage system built on the OpenAI Agents
SDK: a router classifies intent and hands off to a billing, technical
support, or account management specialist, each with its own tools,
guardrails, and access to persistent conversation state. Built for the
"Build a Multi-Agent Customer Support Triage System" lab.

## Design decisions and why

**Customer-scoped tools read `customer_id` from the run context, never
from a model-suppliable argument.** This was not the original design --
an automated security review of the initial commit found that
`look_up_invoice`, `issue_refund`, `look_up_account`, and
`update_contact_info` all took `customer_id: str` as a plain tool
argument, meaning the calling agent (and anything able to influence its
tool-call arguments, such as a prompt-injection payload) could ask to
act on a *different* customer's record. The fix uses the SDK's own
`ctx: RunContextWrapper[SupportContext]` parameter convention: a
ctx-typed first parameter is injected from the trusted run context and
excluded from the tool's model-facing JSON schema entirely (confirmed by
printing `params_json_schema` for a ctx-only tool: zero properties). This
is the idiomatic authorization boundary the SDK provides for exactly
this situation, not a guardrail bolted on after the fact -- see
`docs/architecture.md`'s security-review section for the other three
issues found and fixed the same way.


**Handoffs are keyword-classified in the demo model, but the real
architecture routes on LLM judgment.** In production
(`OPENAI_API_KEY` set), the router's real model decides which
`handoff()` to call based on its own understanding of the message --
the same mechanism as any other Agents SDK handoff. `DemoModel`'s
keyword matching (`demo_model.router_decide`) exists only to make that
decision deterministically testable without a live model; it is not a
production classification strategy and isn't presented as one.

**Guardrails are attached per-agent, not globally on `RunConfig`.** The
SDK supports both. Per-agent was chosen because it lets each specialist
own only the guardrails relevant to its own risk surface --
`no_sensitive_data_leak_guardrail` is on Billing and Account (where a
tool result can contain PII/payment data) but not Technical Support
(whose tools return service-status/ticket data, never customer PII).
Attaching it everywhere "to be safe" would have been simpler to write
and worse to reason about later, since a guardrail firing on an agent
that never produces the risky content it's meant to catch takes real
investigation time to rule out as noise.

**The tool guardrail rejects before the tool body runs, not after.**
`refund_cap_guardrail` is a `tool_input_guardrail` (checked before
`issue_refund` executes) rather than a `tool_output_guardrail` (checked
after). This matters operationally: `tools.py::issue_refund`'s
`_append_audit()` call -- the write that would represent money actually
moving -- never runs for a rejected call. An output-side guardrail would
have had to also guarantee the refund was rolled back after the fact,
which is a strictly harder and riskier thing to get right than never
executing it in the first place.

**Session scoping is per-conversation-thread, not per-customer.** Each
scenario in `run_demo.py` gets its own `SQLiteSession` id
(`cust-4471-billing`, `cust-4471-technical`, etc.) rather than one shared
session per customer. This mirrors a real support tool: a customer's
billing conversation and their unrelated technical-support conversation
from last week shouldn't be replayed into the same context window just
because they're the same customer.

## Trace evidence (in place of a dashboard screenshot)

No OpenAI dashboard access exists in this environment (no API key), so
`examples/traces/trace.jsonl` is the actual evidence: every span,
captured via the SDK's own `Span.export()`. Below is one real trace from
that file, reproduced directly (not summarized) -- the tool-guardrail
rejection scenario, showing the guardrail intercept mid-tool-call:

```
custom    {name: task, data: {sdk_span_type: task, name: Agent workflow}}
agent     {name: Router, handoffs: [Billing Agent, Technical Support Agent, Account Management Agent]}
custom    {name: turn, data: {turn: 1, agent_name: Router}}
guardrail {name: injection_guardrail, triggered: False}
handoff   {from_agent: Router, to_agent: Billing Agent}
agent     {name: Billing Agent, tools: [look_up_invoice, issue_refund]}
custom    {name: turn, data: {turn: 2, agent_name: Billing Agent}}
function  {name: issue_refund,
           input:  {"amount": 900.0, "reason": "customer request"},
           output: "Refund of $900.00 exceeds the $500 threshold. This must be
                     processed by a manager through a separate, authenticated
                     approval workflow -- it cannot be issued from this tool."}
custom    {name: turn, data: {turn: 3, agent_name: Billing Agent}}
guardrail {name: no_sensitive_data_leak_guardrail, triggered: False}
```

Two things worth noting in that span, directly from the trace rather
than asserted in prose: the `function` span's `output` field is the
guardrail's rejection message, not the tool's real return value
(`{"status": "issued", ...}`, visible in the $50 refund scenario's trace
in the same file) -- direct, inspectable proof the guardrail intercepted
before the tool body ran. And `input` carries only `amount` and
`reason` -- no `customer_id` -- which is the authorization fix
(`docs/architecture.md`'s "Vulnerabilities found by an automated
security review") visible in the trace itself: the tool was never given
an argument an attacker could have set to a different customer's ID in
the first place.

The input-guardrail trip (`examples/outputs/06_...json`'s scenario) shows
even more starkly in the trace -- the run stops after a single
`guardrail` span with `triggered: True`; no handoff, no agent-2 span,
because `Runner.run()` raised `InputGuardrailTripwireTriggered` before
anything downstream could execute:

```
custom    {name: task, data: {sdk_span_type: task, name: Agent workflow}}
agent     {name: Router}
custom    {name: turn, data: {turn: 1, agent_name: Router}}
guardrail {name: injection_guardrail, triggered: True}
```

## What's real vs. what requires a live OpenAI account

Consistent with the sibling labs in this project set: **no OpenAI API
key is configured in this development environment.** What's real:

- Every line of orchestration logic -- guardrails, handoffs, tools,
  session state, tracing -- is exercised end to end via `DemoModel` and
  produces the committed outputs in `examples/`.
- The full test suite (14 tests, `pytest`) runs and passes against the
  real installed SDK.
- `agents_def.py` is written so that setting `OPENAI_API_KEY` and
  removing nothing else routes every agent through the real Responses
  API automatically -- this isn't a documented-but-unwired aspiration,
  it's the actual `if os.environ.get("OPENAI_API_KEY")` branch already
  in the code.
- What's *not* demonstrated: an actual live model response, or an actual
  trace visible in the OpenAI dashboard. `DemoModel` substitutes a
  deterministic model specifically so the real control-flow code could
  be run and proven correct without API access -- labeled as such
  everywhere it appears, never presented as a live result.
