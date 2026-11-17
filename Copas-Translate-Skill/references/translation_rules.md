# Translation Rules

The coding agent acts as the translation engine, applying **CopasTool's localization philosophy**, the **language-pair profile** ([language_pairs.md](language_pairs.md)), confirmed **`decisions.json`** (`state card`), and the **locked glossary**, while obeying strict 1:1 structural alignment.

Saved prompts inside `.copas`/`.copas.zip` govern the matching task (`prompt_header` for translation, `glossary_prompt` for glossary, `ai_check_prompt` for review/polish, `agent_prompt` for agent mode). Language-pair rules fill in when the saved prompt is blank or when generating new templates.

---

## Core Localization Principles

1. **Faithful and complete**: preserve meaning, emotional intensity, speaker perspective, omissions/ambiguity, and plot boundaries (never leak future facts from `context_after`). Do not censor, summarize, or drop clauses.
2. **Spoken dialogue vs narration**: dialogue must sound like real spoken language tailored to speaker × addressee (`BOOK_BIBLE.md`); narration and internal monologue must read naturally in the target language.
3. **Language-pair craft** (see [language_pairs.md](language_pairs.md) for concrete rules & examples):
   - **`ja-id` (Primary — Japanese → Indonesian)**: dynamic pronoun/address selection per relationship, zero-pronoun omission when natural, accurate omitted-subject/directionality (`-てあげる/-てもらう/-てくれる`), functional rendering of aizuchi/particles (`なるほど`, `ね/よ`), natural Indonesian syntax without `telah/adalah/yang` bloat, localized onomatopoeia, distinct standalone surname/given-name/nickname renderings.
   - **`en-id` (English → Indonesian)**: restrain `telah/sedang/akan` tense spam, rewrite passive/nominalization/existential calques into active natural Indonesian, disambiguate `you` and kinship terms from context, translate idioms by intent.
   - **`ja-en` (Japanese → English)**: restore omitted subjects cleanly without repeating names, match speaker register with natural English diction/contractions, follow consistent narrative tense and honorific policy, naturalize aizuchi/onomatopoeia.
4. **Glossary is truth**: `characters[].render` and `terms[].dst` are the single source of truth; `keep_source: true` stays verbatim. Unknown proper nouns stay verbatim (Hepburn for Japanese unless established spelling applies) and are recorded for review.

---

## Pipeline Hard Requirements (Enforced by `integrity`, `audit`, `batch validate/write`)

- **Strict 1:1 alignment**: `line_num`, line count, and order must match the batch `lines` array identically. Never merge, split, or drop lines.
- **Speaker handling**: non-empty source `name` requires non-empty `trans_name`; narration (`name: null`) must keep `trans_name: null`. Never invent or drop speakers. Keep grouped speakers (`Nino & Menoa`, `Nino, Menoa & Ichito`, `??? & ???`) as one single `trans_name`.
- **Context is read-only**: `context_before`, `context_after`, `ref_lang_1/2`, `currentBackground`, and `glossary` provide evidence only and must never add output rows.
- **Tags, placeholders & whitespace**: preserve `<i>`, `<b>`, `{0}`, `%s`, `\n`, `<br>`, `[ruby]`, and meaningful trailing spaces verbatim unless a specific `token-exception` is registered in `state`.
- **App copied formats**: when operating through CopasTool's clipboard formats (`numbered` with/without `[D]/[N]`, `block`, `xml`, `jsonl`, `jsonarray`), follow [copastool_workflows.md](copastool_workflows.md).

---

## Pre-Write Checklist

- [ ] Output count == input count, `line_num` and order identical
- [ ] `trans_name` non-empty iff source `name` non-empty
- [ ] All markup tags, placeholders, `\n`, and trailing spaces preserved
- [ ] Glossary characters/terms and `state` settled decisions applied consistently
- [ ] Zero leaked kana/kanji/Japanese punctuation (for Latin targets) and no dropped clauses
