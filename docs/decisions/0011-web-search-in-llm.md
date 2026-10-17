# 0011: `ask_json` can let Claude search the web

Status: accepted, 2026-10-17

**Decision.** `hypercut.llm.ask_json(..., web_search=True)` allows web search for that call: the CLI
backend passes `--allowedTools WebSearch` to `claude -p`, and the API backend adds the server-side
`web_search` tool (at most 5 uses). Off by default.

**Alternatives.** Fetch pages from our own code (the cloud environment blocks most hosts). Never search.

**Why.** Illustration briefs need to know what named things look like. Search runs on Anthropic's side,
so it works without opening the environment's network, and it costs nothing extra on the subscription.

**Consequences.** Calls with search are slower (several turns). Only the visuals director uses it.
