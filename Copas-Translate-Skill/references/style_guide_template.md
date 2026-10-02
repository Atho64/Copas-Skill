# STYLE_GUIDE template for cstl-translate

Copy this to `<WORK>/work/STYLE_GUIDE.md` and fill in per-project specifics. All subagents in parallel mode read this file to stay consistent.

---

# Style Guide — {{projectName}}

## Target language & register

- Target: {{targetLang}} (e.g. Indonesian). Register: natural, neutral-formal for narration, character-faithful for dialogue (casual/polite per speaker).
- No slang pronouns (lo/lu/gue/gua) unless character explicitly requires it — see Characters below.

## Quotation & punctuation

- Dialogue quotes: **choose one** and keep it — either `"` / `"` + `'` / `'` for nested, or Japanese `「」` / `『』`. Do not mix per-agent.
- Narration has no outer quotes.
- Convert Japanese punctuation to target-language equivalents: `。` → `.`, `、`, → `,`, `・` per context, fullwidth `〜` / `ー` normalized.
- Ellipsis: `…` (one char) or `...` consistently.

## Names (characters)

- Glossary `characters[].render` is the only truth. `keep_source:true` or absent → keep source text.
- If `render` is target-language form, use it everywhere (same person → same rendering).
- Include `trans_name` for every line where `name` is non-null. Keep honorifics per User Prompt (`-san/-kun/-chan` etc.).

## Terms (non-character)

- Glossary `terms[].dst` is truth; `keep_source:true` → leave untranslated.
- Do not invent new transliterations for unknown proper nouns — keep source + record for review.

## Tags, placeholders, escapes

- Preserve verbatim: `<i>`, `<b>`, `{0}`, `%s`, `\\n` / `<br>`, `\n`. Do not reposition arbitrarily.

## Line discipline

- **1 line in → 1 line out**. `line_num` unchanged, order unchanged, count unchanged. Never merge/split/drop.

## Tone notes per file/scene (optional)

- `scene01.json`: ...
- `scene02.json`: ...

## Dates, numbers, units

- Dates: target-language convention (e.g. `2024年3月5日` → `5 Maret 2024` for Indonesian).
- Keep numbers as-is unless language requires localization.
