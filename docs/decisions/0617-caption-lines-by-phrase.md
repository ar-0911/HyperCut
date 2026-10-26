# 0617: Caption lines break by phrase

Status: accepted, 2026-10-26

**Decision.** `groupWords(words, perLine, maxChars)` in `render/src/captions.ts` still fills lines up to
`style.caption.words_per_line` words and still breaks at sentence ends and pauses over 0.7 s. It adds four rules:

1. **Clause ends.** A line may stop at a comma, semicolon, colon or dash once it has two words.
2. **No dangling function words.** A full line never ends on an article, preposition, conjunction or possessive
   ("the", "of", "and", "my"); that word starts the next line, unless the line would be left with nothing else.
   Only one word moves, so lines don't chain into a run of short ones.
3. **No orphans.** With three or more words per line, a sentence's last word joins the full line rather than
   sit alone on the next one, if the line still fits.
4. **Fits the frame.** A line is at most `lineChars(size, uppercase)` characters (960 px of the 1080 frame at about
   0.6 em per uppercase character, 0.52 lowercase: 22 at the default 72 px uppercase), so a line never wraps into
   two rows.

Both the export and the editor preview use the same function, so they stay identical.

**Alternatives.** Asking Claude to segment captions: a call per edit for something rules do well, and the editor
regroups on every change. A parser (spaCy) for real phrase boundaries: a heavy dependency in the renderer and in the
browser. Measuring text with the font: exact, but needs canvas metrics in both Remotion and the browser; the
estimate is good enough because flex-wrap catches the rest.

**Why.** Adi's note asks for better captions; line breaks mid-phrase ("good in | the world") are what makes
automatic captions look automatic. On the test footage: "going to be | too much good | in the world.",
"My name is | Marianne Jackabowski", "been in the past." (before: "going to | be too much | good in | the world.",
"My name | is Marianne Jackabowski", "been in | the past.").

**Consequences.** Some lines are a word shorter or longer than `words_per_line`. The word list is English; other
languages fall back to the old count-based breaks plus clause, orphan and width rules.
