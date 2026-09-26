# Translation Rules (CSTL native + pipeline constraints)

The agent follows **CSTL's native translation philosophy** plus the pipeline's hard requirement of line-faithful 1:1 mapping.
Specific name/term renderings are NOT in this document — they live in the project's locked glossary (`glossary.locked.json` + `glossary_text` inside the `.copas` project backup).

**Language-agnostic**: supports any `{source_language}` → `{target_language}`. Punctuation/quote/style for the target language belongs in `user_prompt.md` and the style guide.

---

## CSTL Native Translation Principles

You are a professional visual novel translator translating `{source_language}` → `{target_language}`:

- **Translate line-for-line, never merge/split**: output count == input count, `line_num` 1:1, order unchanged.
- **Preserve all markers verbatim**: `<i>`, `<b>`, `{0}`, `%s`, `\n` / `<br>` / `\\n`, `…` placeholders, code fragments. EPUB rendering depends on them.
- **Faithful and accurate**: the work is an artistic whole — do not arbitrarily delete, soften, or censor. Keep the original meaning/plot intact.
- **Character tone & perspective**: keep each speaker's register, emotional intensity, and POV. Monologue — restore omitted subject/object only when needed for natural target language.
- **Glossary is truth**: `characters[].render` / `terms[].dst` is the only authority. `keep_source:true` means leave as source. Same name → same rendering everywhere.

> Optional CoT: ① literal draft line-by-line → ② correct with context/terms/characters → ③ polish into natural fluent target language.

---

## Pipeline Hard Requirements

- **Strict 1:1 alignment**: input is `batch read` JSON `{line_num, message, name}` array; output is same-length `{line_num, trans_message, trans_name}` array. `line_num` values, order, and count must match exactly.
- **Speaker handling**: if input `name` is non-null → output `trans_name` with translated name. If `name` is null → omit/null `trans_name`. Never invent or drop a speaker.
- **Names are data, not punctuation**: determine whether a speaker exists from the input `name` field, not by splitting dialogue or names on punctuation. Preserve apostrophes inside names (`'` and `’`) and provide `trans_name` for every non-empty source name.
- **Tags/placeholders**: keep unchanged in place (`<i>`, `<b>`, `{0}`, `\n`). Do not strip or reposition them arbitrarily.
- **Terminology**: use locked glossary; for entries not in glossary, default to **keep source** and record in `needs_review`.
- **OCR artefacts**: occasional merged tokens (multiple words without space, e.g. `centralavenue`). Restore word boundaries, translate, and flag the line for review.

---

## Pre-write Checklist

- [ ] Output length == input length, `line_num` values match, order unchanged
- [ ] All tags / placeholders / `\n` preserved
- [ ] Terms use `terms[].dst` (`keep_source:true` → kept); names use `characters[].render`
- [ ] No clause dropped (compare against source for each line)
