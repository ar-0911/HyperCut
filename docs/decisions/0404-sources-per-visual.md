# 0404: The director picks a source per visual

Status: accepted, 2026-10-20

**Context.** With stock footage and generated pictures available (0016), something has to decide which moments
get real footage, which a generated picture and which a drawing.

**Decision.**
- The visual director call (0402) is offered two more kinds, only for what this machine can fetch:
  `footage` (`query`, `media`: video or image) for real things, places and actions; `picture` (`prompt`) for concrete
  scenes no stock shot shows. Drawings stay the choice for diagrams, processes, lists and abstract ideas. Every
  footage or picture visual also has a `brief`, which is what gets drawn if nothing can be fetched.
- With pictures on, the director writes one `look` line for the reel that every picture prompt shares, so they
  match.
- They become `media` graphics with a `generate` request and alternating still moves (`move`).
- Motion moments (0612) also get a `generate: {kind: "video"}` request when clips are available
  (`motion.ask_for_clips`); their 3D scene is still designed and stays the fallback.
- The editor assistant gets `add_picture` (footage, picture or clip) and `anchor` operations.

**Consequences.** With no keys the prompts are unchanged. The share of footage is guided in the prompt ("about a
third of the visuals"), not enforced.
