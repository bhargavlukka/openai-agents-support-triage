"""Disables the SDK's default OpenAI-exporting tracing for the test
suite -- tests should never attempt a network call, and no API key is
configured in this environment."""

from agents import set_tracing_disabled

set_tracing_disabled(True)
