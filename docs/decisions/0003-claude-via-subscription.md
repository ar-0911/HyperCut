# 0003: Claude through Claude Code on the user's subscription

Status: accepted, 2026-10-17

**Decision.** `hypercut/llm.py` calls Claude Code headless (`claude -p --output-format json`) by default,
using the logged-in Claude subscription. `HYPERCUT_LLM=api` switches to the Anthropic API
(`ANTHROPIC_API_KEY`, default model `claude-opus-5-5`); `HYPERCUT_MODEL` overrides the model.

**Alternatives.** API only; another LLM provider.

**Why.** HyperCut is for personal use for now, and the subscription means no per-call bill. A subscription
is for the subscriber's own use, so the API backend exists for the day other people use the app.

**Consequences.** Calls count against the plan's usage limits and are slower to start than raw API calls
(a few seconds each). Every response is validated against the pydantic models before use. Tests never call
Claude; they use fakes.
