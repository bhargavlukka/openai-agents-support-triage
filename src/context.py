"""Run context shared across the whole triage conversation.

Passed as `context=` to `Runner.run(...)`. Every agent's `instructions`
callable receives this via `RunContextWrapper[SupportContext]` and embeds
`customer_id` into the system prompt text -- the mechanism the demo model
in `demo_model.py` uses to know which customer a turn is about, since the
Model interface itself is never handed the run context directly (only
guardrail functions are).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SupportContext:
    customer_id: str
    session_id: str
