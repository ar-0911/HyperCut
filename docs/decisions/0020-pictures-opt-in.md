# 0020. Stock and generated pictures are opt-in per video

Status: accepted (2026-10-20)

## What

Stock footage and generated pictures / clips (0016) are used only when the user asks for them for that video:
a "Use stock footage and AI pictures" checkbox on the upload page (`pictures` on `POST /jobs`, `--pictures` on
`python -m hypercut.run`, `analyze(..., pictures=True)`). It is off by default, and disabled with a note when no
keys are set (`GET /generation` reports what the engine can fetch). In the editor, asking the assistant for a
picture, or "Try another" on one, is itself the request, so those still work on any video when keys are set.

## Alternatives

- **On whenever keys are set** (the first version of 0016). Setting a key for one video changed every later video
  and could spend money without being asked.
- **A global setting in `.env`.** Still not per video, and harder to find than a checkbox.

## Why

Adi: it should be optional and still work without keys. Drawn visuals are free and need nothing; pictures cost a
little and send search words or prompts to outside services, so the user should choose them each time.

## Consequences

- Without keys, or with the box unticked, the pipeline is exactly the drawn-visuals pipeline: no `generate`
  requests are planned, nothing is fetched and no outside service is called.
- Variants and re-renders of a job keep whatever pictures its plan already has.
