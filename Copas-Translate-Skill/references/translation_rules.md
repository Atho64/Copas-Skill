# Translation rules

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

Use the source and surrounding scene to resolve omitted subjects, pronouns, tense, speaker perspective, and relationships. Reference-language text can help disambiguate, but the original source remains the text being translated. Make dialogue match the speaker's register; keep narration smooth without turning internal monologue into attributed dialogue.

---

## Pipeline Hard Requirements

- **Strict 1:1 alignment**: input is `batch read` JSON `{line_num, message, name}` array; output is same-length `{line_num, trans_message, trans_name}` array. `line_num` values, order, and count must match exactly.
- **Speaker handling**: if input `name` is non-null → output `trans_name` with translated name. If `name` is null → omit/null `trans_name`. Never invent or drop a speaker.
- **Names are data, not punctuation**: determine whether a speaker exists from the input `name` field, not by splitting dialogue or names on punctuation. Preserve apostrophes inside names (`'` and `’`) and provide `trans_name` for every non-empty source name.
- **Grouped names**: multiple speakers or descriptive names can contain commas and ampersands (`&`/`＆`), including forms such as `Nino & Menoa` or `??? & ???`. Preserve the whole name field and its mapping instead of splitting it into translation rows.
- **Copied app formats**: when numbered dialogue tags are enabled, repeat the input's `[D]`/`[N]` tag. With `use_dialogue_tags:false`, return `N. Name: dialogue` or `N. narration` without tags. Omit `[File: ...]` labels in either mode. The helper JSON schema does not use these tags. Read [copastool_workflows.md](copastool_workflows.md) for the app's format contracts.
- **Context is reference-only**: for `batch read --with-context`, translate only `lines`. Preceding/following context, references, glossary, and rolling summaries do not add output rows. Following context happens later; do not give a character knowledge they have not acquired yet.
- **Tags/placeholders**: keep unchanged in place (`<i>`, `<b>`, `{0}`, `\n`). Do not strip or reposition them arbitrarily.
- **Spacing**: preserve meaningful trailing spaces and engine newline conventions. Use JSON strings to retain spaces that copied text may trim.
- **Terminology**: use locked glossary; for entries not in glossary, default to **keep source** and record in `needs_review`.
- **Standalone names**: use separate glossary renderings for independently used family/given names and nicknames; do not replace every short name with a full name. Honorific and quotation choices follow the project prompt.
- **OCR artefacts**: occasional merged tokens (multiple words without space, e.g. `centralavenue`). Restore word boundaries, translate, and flag the line for review.

---

## Pre-write Checklist

- [ ] Output length == input length, `line_num` values match, order unchanged
- [ ] `batch write --expect-batch` accepts the saved batch; no context rows or changed speaker types
- [ ] All tags / placeholders / `\n` preserved
- [ ] Terms use `terms[].dst` (`keep_source:true` → kept); names use `characters[].render`
- [ ] No clause dropped (compare against source for each line)
