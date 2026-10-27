# 0029. First steps: goal, first cut, one suggested change, export

Status: accepted (2026-10-26)

## What

Someone new sees a short path instead of the whole editor:

1. **Goal.** The upload page asks for the video and "What are you making?" (the editing mode, ADR 0025), plus a
   brand kit when there is one. Style, hook strategy, footage understanding, pictures and recipes fold under
   "More options"; their defaults are what the folded form sends.
2. **First cut.** The pipeline as before.
3. **One suggested change.** `hypercut/suggest.py` picks one change from the plan alone, with no Claude call:
   end a reel longer than 50 s on the last full sentence before 45 s; else open on a hook that scored within 0.15
   of the chosen one; else tighten pauses when that saves at least a second. `GET /jobs/{id}/suggestion` returns it
   with the plan it makes and what it changes in words. "Try it" puts it in the preview, "Keep it" saves it as a
   version, "Put it back" undoes it, "Skip" moves on.
4. **Export.** Render, then download.

The editor opens in this simple view (player, first steps, the AI box) until the person picks "show all the
controls"; "Simple view" in the toolbar goes back. The choice is remembered per browser (`localStorage`
`hypercut.view`), so returning users get the full editor.

## Alternatives

- **A guided tour over the full editor.** Teaches the controls, but the controls are the problem for a first reel.
- **Claude's review as the suggestion (ADR 0019).** Better ideas, but needs a render first and a Claude call; the
  first suggestion should be instant and free.
- **Several suggestions.** A list is a decision to make; one change, tried in place, is something to react to.

## Consequences

- The defaults behind "More options" carry more weight; changing them changes what new users get.
- A job can have no suggestion; the step then says the cut is ready.
- Remembering the view per browser means a shared machine shows the last person's choice.
