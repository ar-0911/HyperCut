# 0301: Six presets; prompt-to-style as "closest preset plus a patch"

Status: accepted, 2026-10-17

**Decision.** `hypercut/style` ships six complete `Style` presets (`bold_creator`, `clean_corporate`,
`playful`, `cinematic`, `minimal`, `podcast`) and `style_from_prompt(prompt)`. Claude (via
`hypercut.llm.ask_json`) is shown the presets and the `Style` JSON schema and answers
`{"preset": ..., "changes": {...}}`: the closest preset and only the fields to change. The patch is
deep-merged onto the preset and validated with pydantic (`extra="forbid"`). `Style.name` is always the
preset name. An invalid answer (bad JSON, unknown preset, bad or invented fields) is retried once with
the same prompt; if it fails again the result is the chosen preset unchanged, or `bold_creator` if no
valid preset was ever chosen. An empty or blank prompt returns `bold_creator` without calling Claude.

**Alternatives.** Ask Claude for a whole `Style` (more tokens, drifts from tested defaults, easy to
omit fields). Keyword matching without Claude (cannot handle "moody but with red captions"). Raise on
bad output (a styling hiccup should not fail a whole render).

**Why.** Presets are hand-tuned and known to look good, so a patch keeps results sane and the answer
small. Validation means a bad model answer never reaches the renderer. Falling back keeps the pipeline
running; the failure is logged as a warning.

**Consequences.** Any `LLMError` (including a missing `claude` CLI) also falls back silently to a
preset, so a user with no Claude access still gets a working default look. The retry does not feed the
validation error back to Claude; revisit if failures turn out to be common. New `Style` fields
automatically reach Claude through the schema, but each preset should be reviewed when one is added.
