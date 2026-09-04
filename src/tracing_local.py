"""A local, file-based trace processor.

The Agents SDK's built-in tracing exports to the OpenAI dashboard by
default, which needs a real API key (`export_api_key`) this development
environment doesn't have. Rather than disable tracing entirely, this
processor calls the SDK's own `Span.export()` / `Trace.export()` --
the same serialization the OpenAI exporter itself uses internally -- and
writes each one as a JSON line locally. This is what produced
`examples/traces/trace.jsonl`: a real, inspectable trace of agent
decisions, handoffs, tool calls, and guardrail checks, in place of a
dashboard screenshot that would need a live account to produce honestly.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents import Span, Trace, TracingProcessor


class LocalFileTracingProcessor(TracingProcessor):
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, record: dict | None) -> None:
        if record is None:
            return
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def on_trace_start(self, trace: Trace) -> None:
        pass  # only the completed trace (on_trace_end) is written

    def on_trace_end(self, trace: Trace) -> None:
        self._write(trace.export())

    def on_span_start(self, span: Span) -> None:
        pass  # only completed spans (with timing + output) are written

    def on_span_end(self, span: Span) -> None:
        self._write(span.export())

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        pass
