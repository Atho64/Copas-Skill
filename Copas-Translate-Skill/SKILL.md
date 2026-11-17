---
name: copas-translate-skill
description: Translate and review visual novels and books end-to-end through CopasTool backups (.copas, .copas.zip, legacy .cstl), VNTP JSON, EPUB, or Luca TXT. Primary focus on Japanese -> Indonesian (ja-id), plus English -> Indonesian (en-id) and Japanese -> English (ja-en). Features state/provenance tracking, filtered group bundles, live progress dashboard, mechanical audit/scan/verify gates, and slim adversarial / dual-model review.
---

# Copas-Translate-Skill

The coding agent acts as the translation and review engine; deterministic Python stdlib helpers (`Python >= 3.10`, zero required external packages except `beautifulsoup4` + `lxml` for optional raw EPUB import/export) handle I/O, state/provenance, parallel splitting/bundling, glossary enforcement, mechanical auditing, and adversarial review gates.

Aligned with CopasTool `0.1.14-beta.4` (optional `[D]/[N]` dialogue tags, grouped `&` speakers, `ref_lang_1/2`, `.copas` / `.copas.zip`, `custom_index`). Read [references/copastool_workflows.md](references/copastool_workflows.md) when working with the app's UI, spreadsheets, Auto Copas, or Luna Hooker.

**Primary language pair**: **Japanese → Indonesian (`ja-id`)**, with dedicated mechanical profiles and review rules for **English → Indonesian (`en-id`)** and **Japanese → English (`ja-en`)** ([references/language_pairs.md](references/language_pairs.md)).

---

## 1. Setup & Project Layout

Set `PYTHONPATH` to this skill's `scripts` directory (`<PFX>` = Python command with `PYTHONPATH` set):

PowerShell:
```powershell
$CT_SKILL = 'C:\path\to\Copas-Translate-Skill'
$env:PYTHONPATH = Join-Path $CT_SKILL 'scripts'
$env:PYTHONIOENCODING = 'utf-8'
$CSTL_PY = 'python'
```

POSIX shell:
```bash
export CT_SKILL=/path/to/Copas-Translate-Skill
export PYTHONPATH="$CT_SKILL/scripts"
CSTL_PY=python
```

Use an isolated work folder (`<WORK>/work/project.copas`, `<WORK>/out/`). Keep the container suffix matching the input (`.copas` JSON or `.copas.zip` ZIP with `project.json` + `custom_sources/`). Unknown project/line metadata (`custom_index`, `gameEngineCacheDir`, `_ai_checked`, etc.) survives all helper I/O.

---

## 2. Import or Resume

```bash
# VNTP JSON file, folder, or ZIP
<PFX> -m cstl_translate.parse --input /path/scenes --out work/project.copas --name "My VN" --source-lang Japanese --target-lang Indonesian

# Existing CopasTool backup (copied intact, preserving saved prompts & engine indices)
<PFX> -m cstl_translate.parse --input /path/backup.copas --out work/project.copas --import-project
<PFX> -m cstl_translate.parse --input /path/backup.copas.zip --out work/project.copas.zip --import-project

# Basic EPUB or Luca TXT import
<PFX> -m cstl_translate.parse --input /path/book.epub --out work/project.copas --type epub --source-lang English --target-lang Indonesian
<PFX> -m cstl_translate.parse --input /path/luca_txt --out work/project.copas --type luca

# Inspect counts and per-file breakdown
<PFX> -m cstl_translate.cstl_io status work/project.copas
<PFX> -m cstl_translate.cache stats work/project.copas
```

For `cache` inspection/cleanup:
- `cache show work/project.copas --range 1-80 [--file scene01.json] [--status untranslated|translated]`
- `cache set-hidden work/project.copas --range 1-10 --apply` (exclude non-story lines; `--unhide` reverses)
- `cache fill-dupes work/project.copas --max-chars 60 --apply` (copy confirmed translations across exact duplicate short `(name, message)` lines)

---

## 3. Saved Prompts, Modules & Project State (`state`)

### Saved Prompts & Reusable Modules
For `.copas`/`.copas.zip` backups, `batch read` and `batch bundle` automatically use the saved prompt matching each task (`prompt_header` → translate, `glossary_prompt` → glossary, `ai_check_prompt` → review/polish, `agent_prompt` → agent) and resolve `{{sourceLang}}`, `{{targetLang}}`, and `{{lineCount}}`. Fallbacks (plus `ja-id` / `en-id` / `ja-en` rules) apply only when the saved task prompt is blank.

```bash
<PFX> -m cstl_translate.prompt extract work/project.copas --out-dir work/project_prompts
<PFX> -m cstl_translate.prompt init --project work/project.copas --task translate --out work/user_prompt.md
# Or reusable module packs (~/.cstl-translate/modules/<name>, override via CSTL_TRANSLATE_HOME):
<PFX> -m cstl_translate.module create my-vn --source-lang Japanese --target-lang Indonesian
<PFX> -m cstl_translate.module load my-vn --work work
```

### Shared Decisions & Provenance (`work/project.copas.decisions.json` & `.provenance.jsonl`)
Maintain one central truth file read by `batch bundle`, `batch validate`, `audit`, `verify`, and `review`:

```bash
<PFX> -m cstl_translate.state settle work/project.copas --src "旧校舎" --dst "gedung sekolah lama" --note "confirmed"
<PFX> -m cstl_translate.state errata work/project.copas 412 --note "Source typo: keep intended meaning"
<PFX> -m cstl_translate.state token-exception work/project.copas 77 --reason "Intentional extra <i> tag"
<PFX> -m cstl_translate.state lint-rule work/project.copas no_anda --re "\\bAnda\\b" --msg "Casual VN; use aku/kamu"
<PFX> -m cstl_translate.state card work/project.copas --range 1-300
```

Whenever corrections are written via `batch apply --source <label> --reason "..."`, removed snippets are logged to `provenance.jsonl` so subsequent adversarial review passes cannot accidentally revert confirmed meaning fixes (`E_reverts_fix`).

---

## 4. Glossary, `CATATAN_CERITA` & `STYLE_GUIDE`

1. **Seed & extract**:
   - **From VNDB** (official character names, readings, aliases, roles, gender, non-spoiler notes):
     ```bash
     # Search by title or pass VN ID / URL directly (e.g. --vn v17):
     <PFX> -m cstl_translate.glossary vndb --search --query "My VN"
     <PFX> -m cstl_translate.glossary vndb work/project.copas --vn v17 --out work/glossary.locked.json --cast-out work/vndb_cast.md --inject
     ```
     (`--merge` appends into an existing `glossary.locked.json` without overwriting confirmed spellings; `--matched-only` keeps only characters found in the project; `--split-names auto|all|none` splits standalone family names, given names, and paired nicknames; `--max-spoiler 0|1|2` and `--name-order family-given|given-family` control spoilers and Hepburn order.)
   - **From project / script**:
     ```bash
     <PFX> -m cstl_translate.glossary from-project work/project.copas --out work/glossary.locked.json
     <PFX> -m cstl_translate.batch read work/project.copas --task glossary --size 500 --offset 0 > work/glossary_batch_001.json
     # Convert agent's `[type] source = target {desc}` or `src\tdst` terms, review, and inject:
     <PFX> -m cstl_translate.glossary from-text --text work/new_terms.txt --out work/glossary.candidates.json
     <PFX> -m cstl_translate.glossary lint --locked work/glossary.locked.json
     <PFX> -m cstl_translate.glossary inject work/project.copas work/glossary.locked.json
     ```
     Keep standalone family/given names and nicknames separate; do not merge distinct characters sharing a surname. Respect `keep_source: true`.
2. **Pre-translation discoveries**:
   ```bash
   <PFX> -m cstl_translate.scan work/project.copas --locked work/glossary.locked.json --mode pending
   ```
3. **Facts & style**: fill [references/catatan_cerita_template.md](references/catatan_cerita_template.md) (especially the pairwise Pronoun & Address Matrix for `ja-id` / `en-id`) and [references/style_guide_template.md](references/style_guide_template.md). If resuming a partially translated project, generate `work/CATATAN_CERITA.md` automatically via `precedents`.

---

## 5. Intervention Modes & Translation Loop

Confirm the user's mode before mass translation:
- **Mode A (Sample-then-Auto, default)**: translate an opening sample (up to ~1000 lines / opening chapter for full VNs so the main cast appears, or ~100–200 lines for shorter works; summarize the pronoun matrix and representative dialogue per character for sign-off instead of dumping all raw lines), confirm voice/pronouns/honorifics/quotes with the user, then proceed automatically (pausing only on ambiguous new entities).
- **Mode B (Every-Batch Review)**: show each batch for sign-off before write-back.
- **Mode C (Fully Auto)**: translate end-to-end, logging uncertain out-of-glossary names to `needs_review` for final summary.

### Serial Loop (Small/Medium Projects or Sample Batch)
```bash
<PFX> -m cstl_translate.batch read work/project.copas --size 100 > work/batch_001.json
# Agent translates `lines` 1:1 following references/translation_rules.md + references/language_pairs.md
<PFX> -m cstl_translate.batch write work/project.copas work/translations_001.json --expect-batch work/batch_001.json
```
- Windows PowerShell 5.1 note: write CLI JSON with `| Out-File -LiteralPath work/batch_001.json -Encoding utf8` (avoid `>` UTF-16).
- `--expect-batch` enforces exact count, order, `line_num`, speaker presence, snapshot freshness, and token/markup fidelity atomically before backup/write. Every write uses an advisory file lock, retains up to `CSTL_BACKUP_KEEP` (default 10) backups, and saves atomically.

### Parallel Bundle Loop (Large VNs)
See [references/parallel_translation.md](references/parallel_translation.md). Summary:
```bash
<PFX> -m cstl_translate.batch split work/project.copas --target 250 --out-dir work/par --context 20
<PFX> -m cstl_translate.batch bundle work/project.copas work/par/grp_*_src.json --locked work/glossary.locked.json --include work/STYLE_GUIDE.md work/CATATAN_CERITA.md
# Workers read ONE bundle_N.md and write ONE trans_N.jsonl + newterms_N.txt (never touching project.copas)
<PFX> -m cstl_translate.batch validate work/par/grp_1_src.json work/par/trans_1.jsonl --project work/project.copas
<PFX> -m cstl_translate.glossary merge-newterms --locked work/glossary.locked.json work/par/newterms_*.txt --apply --inject work/project.copas
<PFX> -m cstl_translate.batch write work/project.copas work/par/trans_*.jsonl
```
Watch live worker progress anytime with `progress work/project.copas --once | --watch | --line | --serve 8765 --open`.

---

## 6. Mechanical Quality Loop (`verify` + `scan` + `audit` + `glossary lint`)

Run all four tools together after each wave or upon completion (`verify` only enforces what is already in `glossary.locked.json`; `scan` discovers missing terms, strays, and merges; `audit` catches structural & language-pair residue):

```bash
<PFX> -m cstl_translate.verify work/project.copas work/glossary.locked.json --out work/verify.json
<PFX> -m cstl_translate.scan work/project.copas --locked work/glossary.locked.json --mode all --out work/scan.json
<PFX> -m cstl_translate.audit work/project.copas --out work/audit.json
<PFX> -m cstl_translate.glossary lint --locked work/glossary.locked.json
```

Apply any corrections cleanly without downgrading statuses using `batch apply` (supports full `trans_message`/`polished_text` OR minimal `patches: [[old, new]]` and `--source` provenance):
```bash
<PFX> -m cstl_translate.batch apply work/project.copas work/fixes.jsonl --source editor --reason "Fix stray terms"
```
Suppress reviewed false positives (e.g. intentional pronoun drops) with `verify ... --write-baseline work/verify.baseline.json`, then `--baseline work/verify.baseline.json`.

---

## 7. Polish & Adversarial / Dual-Model Review (Optional High-Quality Pass)

### Surface Polish Pass
- Serial: `batch read-translated` → `polish write work/project.copas work/polished_001.json --expect-batch work/review_001.json`
- Parallel: `batch split --stage polish` → `batch bundle --stage polish` → `batch validate` → `polish write work/project.copas work/par/polished_*.jsonl`

### Slim Adversarial Review & External/Dual-Model Review
To eliminate subtle mistranslations (`誰が誰に`, modality, flipped negation, dropped clauses) and translationese (`telah/adalah/yang` bloat, stiff dialogue) that single-pass polish misses:
- Full protocol: [references/adversarial_review.md](references/adversarial_review.md)
- Defect taxonomy (A–E + 14 symptoms): [references/review_taxonomy.md](references/review_taxonomy.md)
- Role prompt templates (Blind Reader, Reviewer, Challenger, Consistency Auditor): [references/review_prompts.md](references/review_prompts.md)
- External / dual-model review (`cache dump`, `review import`, `review dual-merge`): [references/external_review.md](references/external_review.md)

---

## 8. Export & Hand-Off

```bash
# Default deliverable ZIP containing ONLY the `.copas` backup (`out/<name>.zip` -> `<name>.copas`)
<PFX> -m cstl_translate.export --cstl work/project.copas --output out --format copas-zip

# Raw script / document formats (for Copas-Reverse-Skill backfill, EPUB, or Luca)
<PFX> -m cstl_translate.export --cstl work/project.copas --output out --format json
<PFX> -m cstl_translate.export --cstl work/project.copas --output out --format epub
<PFX> -m cstl_translate.export --cstl work/project.copas --output out --format luca
```

- **`.copas`-only ZIP delivery (`--format copas-zip` / `copas`)**: writes `<out>/<name>.zip` containing strictly one file (`<name>.copas`, preserving `custom_sources/` buffers, prompts, glossary, and `custom_index`). Use this whenever delivering a translated CopasTool project backup as an archive.
- **VNTP JSON**: writes one JSON file per original filename (plus ZIP for multi-file projects). Chain into `Copas-Reverse-Skill` (`vntp pair` / `vntp validate` -> `patch build-spec` / engine repack).
- **Native Game Engine / Custom Parser**: deliver the updated `.copas` (or `--format copas-zip`) / `.copas.zip` backup (with preserved `custom_index` & external cache) back to CopasTool for Build Patch / parser export.

---

## 9. CLI Quick Reference

| Module | Subcommands / Purpose |
|---|---|
| `cstl_io` | `status <project>` |
| `parse` | `--input ... --out ... [--import-project] [--type auto\|json\|epub\|luca] [--source-lang] [--target-lang]` |
| `cache` | `stats` · `show --range` · `dump --out [--changed-since]` · `set-hidden --apply` · `fill-dupes --apply` |
| `state` | `show` · `settle` · `errata` · `token-exception` / `tag-exception` · `lint-rule` · `card` |
| `prompt` | `init [--project \| --format]` · `extract` |
| `module` | `create` · `list` · `show` · `load --work` |
| `glossary` | `vndb` · `from-project` · `from-text` · `extract` · `inject` · `filter` · `lint` · `merge-newterms` |
| `vndb` | `[project] [--vn ID \| --query TITLE] [--search] [--out] [--cast-out] [--merge] [--inject] [--matched-only]` |
| `precedents` | `<project> --for grp_*_src.json [--locked] --out CATATAN_CERITA.md` |
| `batch` | `read` · `read-translated` · `split` · `bundle` · `validate` · `write` · `apply` |
| `polish` | `write <project> <files...> [--expect-batch] [--force] [--allow-tag-mismatch]` |
| `verify` | `<project> [locked] [--baseline] [--write-baseline] [--json] [--out]` |
| `scan` | `<project> --locked L --mode all\|discover\|terms\|strays\|merges\|pending [--out]` |
| `audit` | `<project> [--out] [--json] [--allow-tag-mismatch]` |
| `review` | `blind` · `hints` · `rules` · `check` · `pre` · `segs` · `inventory` · `stats` · `final` · `merge` · `pick` · `benchmark` · `score` · `log` · `ledger` · `import` · `dual-merge` |
| `progress` | `<project> [--once\|--watch\|--line\|--json\|--serve PORT]` |
| `export` | `--cstl <project> --output <dir> --format copas-zip\|copas\|auto\|json\|epub\|luca [--name BASE]` |

Tests (from `Copas-Translate-Skill/`):
```bash
python -B -m unittest discover -s tests -v
```
