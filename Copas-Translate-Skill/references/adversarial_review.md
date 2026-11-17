# Adversarial Review (Slim Protocol for CopasTool VNs)

Polish passes with the same model catch surface phrasing, while subtle mistranslations, unnatural Indonesian/English calques, and cross-scene drift survive. Adversarial review separates **finding problems** (high recall) from **vetoing weak edits** (high precision), with deterministic gates in between.

## Roles & Incentives

| Role | Reads | Writes | Incentive |
|---|---|---|---|
| **Blind Reader** | `groups/blind_<G>.json` (**target text only**, no source), `review_taxonomy.md`, `EXAMPLES.md`, `POLISH_REDLINES.md` | `flags_<G>.jsonl` | **High recall**: flag anything that feels stiff, ambiguous, unnatural, or off-voice to a native `{target_lang}` reader |
| **Reviewer** | `groups/grp_<G>_src.json`, `hints_<G>.json` (Blind flags + source), `rules_<G>.json`, `STYLE_GUIDE.md`, `language_pairs.md` | `findings_<G>.jsonl` (self-checked with `review check`) | **High recall**: verify each Blind flag against source, scan remaining lines for A/B/C>=2 defects, cite `source_evidence`, write JSONL |
| **Challenger** | `challenge_<G>.jsonl`, `segs_<G>.json`, `hints_<G>.json`, `rules_<G>.json`, `POLISH_REDLINES.md` | `verdicts_<G>.jsonl` | **High precision**: `reject` false alarms, redline violations, or bad rewrites; `amend` real issues with flawed fixes; `accept` solid fixes |
| **Consistency Auditor** | `inventory.json`, `POLISH_REDLINES.md`, `review_taxonomy.md` | `findings_D.jsonl` | Catch cross-line terminology drift, speaker rendering drift, and inconsistent repeated lines (`callbacks`) |
| **Coordinator** | All outputs | `review pre/segs/final`, `batch apply --source adversarial` | Mechanical gate + serial write-back to `project.copas` (subagents never write `.copas`) |

## Why Blind Reader First + `--mode slim`

1. Bilingual reviewers looking directly at Japanese/English source rationalize awkward target prose ("technically it matches the source"). A monolingual **Blind Reader** catches awkward Indonesian/English syntax, wrong register, and unnatural dialogue rhythm immediately.
2. Under **`--mode slim`** (recommended default):
   - **All A & B findings** (mistranslations and target-language grammar/lexicon defects) go to Challenger because passing A/B edits auto-apply into the project.
   - **Flagged C/D findings** (backed by Blind Reader) auto-accept (`verdicts_<G>.auto.jsonl`) straight into the human review table (`review_ALL.md`), saving Challenger tokens.
   - **Unflagged C/D findings** still go to Challenger (unflagged stylistic edits have much higher false-positive rates).
   - **Waivers (`redline_waiver` / `_settled_override`) & `latin_change`** always go to Challenger; `latin_change` A-fixes stay human-reviewed (`review_ALL.md`) instead of auto-applying.

## Review `config.json` & Redlines

Store shared rules in `<work>/review/config.json` (root shared across `--run` passes):

```json
{
  "redline": [
    "Mugi-san",
    {"re": "Kakak|Abang", "waivable": true}
  ],
  "settled": ["gedung sekolah lama"],
  "glossary_settled": true,
  "forbid": "[\\u3001\\u3002\\uff01\\uff1f\\u3000]",
  "soft_block": ["kana_residue", "kanji_residue", "jp_punct", "space_before_punct", "odd_quotes", "english_sfx_residue"],
  "leak_files": ["EXAMPLES.md"]
}
```

- `redline`: protected strings/regexes — multiset in `offending` must equal multiset in `proposed` (change forbidden, unchanged mention allowed). Entries marked `{"re": "...", "waivable": true}` may be modified when the finding supplies `"redline_waiver": "<source reason>"` and always route to Challenger.
- `settled` + `glossary_settled`: confirmed target renderings may be introduced or expanded into a longer settled phrase, never deleted (A-category findings may override glossary-only terms when Challenger verifies them).
- `forbid` / `soft_block`: blocks regressions (e.g., leaking Japanese punctuation `、。！？`, kana/kanji residue, unbalanced quotes). Add `「」` to `forbid` if the project uses standard `"..."` quotes.

## End-to-End Sequence

`<PFX>` = `PYTHONPATH="$CT_SKILL/scripts" "$CSTL_PY"`, `<REV>` = `work/review` (use `--run <name>` for subsequent passes so files stay isolated under `work/review/<name>/`):

```bash
# 0. Pre-check project decisions & settle book-wide policies (BOOK_BIBLE.md §5)
<PFX> -m cstl_translate.state card work/project.copas --range 1-1000

# 1. Split translated lines into balanced ~140-line review groups
<PFX> -m cstl_translate.batch split work/project.copas --stage review --range 1-1000 --target 140 --prefix g --out-dir work/review/groups --context 3

# 2. Slice glossary + EXAMPLES.md + state card per group
<PFX> -m cstl_translate.review rules work/project.copas g1 g2 --locked work/glossary.locked.json

# 3. Blind Read (target-only, concurrent subagents) -> validate -> attach source
<PFX> -m cstl_translate.review blind work/project.copas g1 g2
# ... Blind Reader subagents produce work/review/flags_gN.jsonl ...
<PFX> -m cstl_translate.review hints work/project.copas work/review/flags_g*.jsonl

# 4. Wave 1: Reviewers (rolling dispatch, ~4-5 concurrent; each self-checks with `review check`)
# ... Reviewer writes work/review/findings_gN.jsonl and runs:
<PFX> -m cstl_translate.review check work/project.copas g1
<PFX> -m cstl_translate.review log work/project.copas --stage reviewer --group g1 --model <model> --file work/review/findings_g1.jsonl --tokens <N> --segments 140

# 5. Pre-gate + slim routing + consistency inventory
<PFX> -m cstl_translate.review pre work/project.copas work/review/findings_g*.jsonl
<PFX> -m cstl_translate.review segs work/project.copas --mode slim work/review/findings_g*.pre.jsonl
<PFX> -m cstl_translate.review inventory work/project.copas --range 1-1000 --locked work/glossary.locked.json

# 6. Wave 2: Challengers (per group with challenge_gN.jsonl) + 1 Consistency Auditor (inventory.json -> findings_D.jsonl)
<PFX> -m cstl_translate.review stats work/project.copas g1 g2

# 7. Final gate -> apply A/B automatically with provenance -> merge C/D for user pick
<PFX> -m cstl_translate.review pre work/project.copas work/review/findings_D.jsonl
<PFX> -m cstl_translate.review final work/project.copas g1 g2 D
<PFX> -m cstl_translate.batch apply work/project.copas work/review/apply_g*.json --source adversarial
<PFX> -m cstl_translate.review merge work/project.copas g1 g2 D

# 8. User selects C/D items from review_ALL.md -> pick -> apply
<PFX> -m cstl_translate.review pick work/project.copas g1 g2 D --min-sev 2 --exclude g1-012
<PFX> -m cstl_translate.batch apply work/project.copas work/review/apply_pick.json --source user

# 9. Re-verify mechanical gates & inspect token ledger
<PFX> -m cstl_translate.verify work/project.copas work/glossary.locked.json
<PFX> -m cstl_translate.audit work/project.copas
<PFX> -m cstl_translate.review ledger work/project.copas
```

## Mechanical Gate Rules (`review pre` / `review check`)
1. Required fields: `id`, `line_num`, `category` ∈ `{A,B,C,D}`, `offending`, `proposed`.
2. `offending` occurs **exactly once** in `trans_message`.
3. `redline` multisets unchanged (unless waivable + `redline_waiver`); `settled` terms preserved (or expanded); no `forbid` chars introduced.
4. Visible length of `proposed` stays within `0.45x–2.2x` of `offending` (when `visible(offending) >= 25`) so rewrites cannot drop clauses.
5. `audit.lint_line` passes all hard checks (`empty`, `speaker_missing`, `speaker_invented`, `structural_tokens`, `markup_order`, `trailing_space`) and adds no `soft_block` regressions.
6. Protected proper nouns / glossary names / source-present Latin tokens in `offending` are untouched (unless `category == "A"` + `"latin_change": true`, which routes to human review).
7. `E_reverts_fix`: must not reintroduce snippets previously removed by protected meaning fixes in `provenance.jsonl`.
