# 0611: Stage graphics behind the speaker: cards, scenes and charts

Status: accepted, 2026-10-18

**Decision.** Three graphic types show what the speaker talks about, drawn behind the cut-out speaker
(`render/src/Stage.tsx`, `hypercut/analyze/stage.py`). Each is picked per moment, only where a moment calls
for one:

- `card_stack` (`props.cards`: 1-3 `{title, brief}` plus the drawing): illustrated cards that start behind
  the speaker's head and slide out in 3D down one side of the frame, one after another, while the speaker
  is pulled back and moved to the other third. When the speaker names things: roles, steps, products,
  places.
- `scene` (`title`, `brief` plus the drawing): a drawn world, tall 1080x1920, replacing the room, with a
  slow push-in and the edges falling off into the panel colour. For an intro or a change of topic.
- `chart` (`headline`, `kind`: line or bars, `values`, `labels`, `unit`): a headline with its number in white
  and its words in the accent, over a dark panel where the line draws on (or the bars grow) and the last value
  pops in a tag. Over a dark studio backdrop. Only for numbers that are actually said.

For every stage graphic the speaker is pulled back: scaled to 74% about the bottom of the frame under the
face, eased over 0.45 s, so the graphic shows above and around them; for cards they also move sideways so the
face sits a third of the way in from the other side (the reframe keeps the face centred, so in a close-up
there is no free side otherwise; the first test reel had the cards hidden behind the speaker's hair). Camera
punch-ins fade out while pulled back. The speaker's pixels are still the original pixels, only smaller and
moved. A scene, or a dark studio backdrop for cards and charts, covers the real footage, so the full-size
speaker never shows as a ghost behind the smaller one.

Analyze asks for them in the main call (`"stage"`, at most two a minute, "most reels need 1-3, [] when
nothing calls for it"), drops overlaps and those outside speaker stretches, caps cards at 5.5 s and scenes and
charts at 5 s, and drops behind titles and effects around the speaker that would share the moment. Cards and
scenes are drawn by the layout illustrator (one call per three drawings) with the style's palette; the
illustrator can now draw a tall canvas. The AI box has a `stage` op; the editor has Cards, Scene and Chart
tiles; anything added or changed there is drawn before the render.

Two new style colours: `graphics.secondary_color` (tags and chart details, default the accent) and
`graphics.panel_color` (panels and card labels, default a near-black navy). Card labels and chart type use the
caption font.

This replaces orbit and fly-out (ADR 0610) as what analyze proposes: Adi found the stickers read like
emoji. Those types still render in older plans, and particles stay in the editor.

**Alternatives.** Only one of the three treatments: every moment would look the same. Generated photo or video
backgrounds: costly, and generated pictures next to real footage look fake. Charts drawn by Claude as SVG: the
data would not animate and could not be edited as numbers.

**Consequences.** Without a cut-out (not made yet, or it failed) stage graphics are not drawn at all, since
they would cover the speaker. Each card or scene costs a share of an illustrator call. Cards and charts
always sit on the same studio backdrop, which gives the reel a consistent look but hides the real room for
those few seconds.
