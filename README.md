# Multi-Agent Customer Support Triage System (OpenAI Agents SDK)

A production-style customer support triage system: a router agent
classifies each request and hands off to a billing, technical support,
or account management specialist, each with its own tools and
guardrails, backed by persistent session state and full tracing. Built
for the "Build a Multi-Agent Customer Support Triage System" lab.

## What's real vs. what requires a live OpenAI account

**No OpenAI API key is configured in this development environment.**
What's real:

- Every line of orchestration logic -- guardrails, handoffs, tools,
  session state, tracing -- lives in `src/` and is exercised end to end,
  producing the committed outputs in `examples/`.
- `python -m src.run_demo` actually runs that code, seven times,
  producing real committed outputs (`examples/outputs/*.json`), a real
  trace (`examples/traces/trace.jsonl`), and a real audit log
  (`data/audit_log.jsonl`) -- including two real bugs found and fixed by
  running it (see `docs/architecture.md`'s "Bugs found by actually
  running this").
- The 17-test suite (`pytest`) runs and passes against the real
  installed `openai-agents==0.22.0` package.
- Setting `OPENAI_API_KEY` (see `.env.example`) switches every agent to
  the SDK's real default model -- `OpenAIResponsesModel`, the real
  Responses API -- with no other code change; see `src/agents_def.py`.
- What's *not* demonstrated: an actual live model response, or a trace
  visible in the OpenAI dashboard (that needs the API key above).
  `DemoModel` substitutes a deterministic, keyword-driven model
  specifically so the real control-flow code could be built, run, and
  proven correct without API access -- labeled as such everywhere it
  appears.

## Quickstart (runs now, no API key needed)

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # or .venv/bin/pip on macOS/Linux
python -m src.run_demo
```

Regenerates `examples/outputs/*.json`, `examples/traces/trace.jsonl`, and
appends to `data/audit_log.jsonl` from a clean state.

```bash
python -m pytest -v
```

## Sample interactions

See `examples/outputs/`:

1. `01_billing_balance_lookup.json` -- billing intent, `look_up_invoice` called
2. `02_billing_followup_refund_small.json` -- a stateful follow-up in the
   *same session* as #1 ("can I get a $50 refund on that?"), proving
   conversation history persists via `SQLiteSession`
3. `03_technical_mobile_app_crash.json` -- routed to Technical Support,
   `check_system_status` finds the service degraded, `create_support_ticket` files a ticket
4. `04_account_update_email.json` -- routed to Account Management, `update_contact_info` called
5. `05_tool_guardrail_refund_over_threshold.json` -- **the required
   guardrail demonstration**: a $900 refund request is rejected by
   `refund_cap_guardrail` (a `tool_input_guardrail`) before `issue_refund`'s
   body ever runs
6. `06_input_guardrail_injection_blocked.json` -- a prompt-injection
   attempt is blocked by `injection_guardrail` before any agent acts on it
7. `07_output_guardrail_card_number_blocked.json` -- a response that
   would have echoed a raw card number is blocked by
   `no_sensitive_data_leak_guardrail` before reaching the customer

All three guardrail types trip in this sample run, not just the one the
brief requires -- see `docs/architecture.md`'s guardrail table.

**Security note:** an automated review of the initial commit found four
real issues (a cross-customer authorization gap in the tools, a
guardrail bypass via a self-asserted flag, and two guardrail parsing
gaps) -- all fixed, with regression tests added for each; see
`docs/architecture.md`'s "Vulnerabilities found by an automated security
review" section for the full detail.

## Tracing

`examples/traces/trace.jsonl` -- every agent run, handoff, tool call, and
guardrail check, captured via the SDK's own `Span.export()`/`Trace.export()`
(no OpenAI dashboard access exists here to screenshot; see
`docs/design-doc.md`'s "Trace evidence" section for a real trace walked
through span by span, including the tool guardrail intercepting a
rejected refund mid-call).

## Repository layout

- `src/agents_def.py` -- the four agents, their handoffs, and guardrail wiring
- `src/tools.py` -- the six domain tools (billing, technical, account)
- `src/guardrails.py` -- input, output, and tool guardrails
- `src/demo_model.py` -- the local deterministic model used without an API key
- `src/tracing_local.py` -- local trace capture (stands in for the OpenAI dashboard)
- `src/run_demo.py` -- runs all seven sample interactions
- `docs/architecture.md` -- agent topology diagram, guardrail table, bugs found by running this
- `docs/design-doc.md` -- design decisions and rationale, plus the trace-evidence walkthrough
- `tests/` -- 17 tests: guardrail unit tests + full-run integration tests
- `examples/` -- committed sample outputs, trace, and (once generated) sessions

## Repository layout note on `data/audit_log.jsonl`

Committed as real evidence of the write actions the tool calls actually
took during the captured run (a refund issued, a ticket created, a
contact-info update) -- not gitignored, since it's part of the "sample
interactions" evidence this lab asks for, not a throwaway dev artifact.
