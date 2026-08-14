---
name: cstl-translate
description: Translate visual novels end-to-end on the coding agent itself (Claude Code / Codex), CSTL-style — parse JSON/EPUB/Luca TXT into .cstl, build a locked glossary, translate batch-by-batch with the agent as engine, write back and export. Triggers on "translate this VN", "terjemahkan VN ini", "translate with cstl", "cstl translate" and similar VN translation requests.
---

# cstl-translate — Agent-as-Engine VN Translator for CSTL Format

Let the **coding agent itself** be the translation engine, with a deterministic Python pipeline that mirrors [CSTL (Copas Tool)](https://atho64.github.io/cstl) — translate a visual novel **end-to-end on the agent**:

```
parse → build locked glossary → translate batch-by-batch (agent) → write back → export → verify
```

- **Agent IS the engine**: no external translation API; quality comes from the agent following `references/translation_rules.md` + your `user_prompt.md` + a locked glossary.
- **CSTL-native**: reads and writes `.cstl` backup JSON (the single-file project format CSTL uses for Backup/Restore). Also handles raw `JSON (VNTP)`, `EPUB`, and `LucaSystem TXT` inputs.
- **Resumable**: `batch read` only returns `is_translated=false` lines — re-run resumes from the first untranslated line. Each `batch write` creates a timestamped backup.
- **Any language pair**: auto-detect source, user-specified target (examples use `Japanese → Indonesian`).

Pipeline scripts live in `scripts/cstl_translate/` — no separate `pip install` of CSTL needed. Light Python deps only.

---

## Prerequisites (one-time)

### 1. Skill location

Place this `cstl-translate/` folder in the agent's skills directory:

```
~/.claude/skills/cstl-translate/     # Claude Code
~/.codex/skills/cstl-translate/      # Codex
```

Below, `$SKILL_DIR` means that directory. For Codex tool-name mapping see `references/codex-tools.md` if present.

### 2. Python venv + deps

Any Python ≥ 3.10:

```bash
python3 -m venv ~/.venvs/cstl-translate
~/.venvs/cstl-translate/bin/pip install beautifulsoup4 lxml chardet
# epub support needs bs4 + lxml; plain JSON works with stdlib only
```

### 3. Env vars (each new shell, or put in profile)

```bash
export SKILL_DIR=~/.claude/skills/cstl-translate
export CSTL_PY=~/.venvs/cstl-translate/bin/python
```

**Command prefix used below as `<PFX>`:**

```bash
PYTHONPATH="$SKILL_DIR/scripts" "$CSTL_PY"
```

Self-check:

```bash
PYTHONPATH="$SKILL_DIR/scripts" "$CSTL_PY" -c "from cstl_translate import cstl_io; print('cstl OK')"
```

---

## Step 1 — Prepare a work directory

One work dir per book/project (referred to as `$WORK`):

```bash
export WORK=~/my-vn
mkdir -p "$WORK/work" "$WORK/out"
```

---

## Step 2 — Parse input into .cstl

Turn raw files into a `.cstl` project bundle (`work/project.cstl`):

```bash
# JSON (VNTP) — single file, folder, zip, or multiple files
<PFX> -m cstl_translate.parse --input /path/to/scene.json --out "$WORK/work/project.cstl" --name "My VN"

# Folder of JSONs
<PFX> -m cstl_translate.parse --input /path/to/json_folder/ --out "$WORK/work/project.cstl" --name "My VN"

# EPUB
<PFX> -m cstl_translate.parse --input /path/to/book.epub --out "$WORK/work/project.cstl" --name "My VN" --type epub --epub-tags p

# LucaSystem TXT (one or many .txt)
<PFX> -m cstl_translate.parse --input /path/to/luca_txt_folder/ --out "$WORK/work/project.cstl" --name "My VN" --type luca
```

Options:
- `--type auto|json|epub|luca` (default `auto` by extension)
- `--name` project name
- `--source-lang` / `--target-lang` (default `Japanese` / `Indonesian`)
- `--epub-tags` CSS selector for EPUB text extraction (default `p`)

Prints: `parsed N lines -> .../project.cstl [type=json]`.

### Step 2 alt — Import an existing .cstl

Already have a `.cstl` backup (from CSTL's Dashboard → Backup) or a previous cstl-translate `project.cstl`:

```bash
# Import / resume
<PFX> -m cstl_translate.parse --input /path/to/existing.cstl --out "$WORK/work/project.cstl" --import-cstl
# or simply copy:
cp /path/to/existing.cstl "$WORK/work/project.cstl"
```

Then check status:

```bash
<PFX> -m cstl_translate.cstl_io status "$WORK/work/project.cstl"
```

---

## Step 3 — Build and lock the glossary

Generate a locked glossary from the source text, then **human-review and lock** it:

```bash
# Extract candidate glossary from source lines (frequency + CJK heuristics)
<PFX> -m cstl_translate.glossary extract "$WORK/work/project.cstl" --out "$WORK/work/glossary.locked.json"

# Optional: seed from an existing CSTL glossary_text export
<PFX> -m cstl_translate.glossary from-text --text /path/to/glossary.txt --out "$WORK/work/glossary.locked.json"

# Optional: import VNDB/AniList names (requires network; writes to locked file)
# <PFX> -m cstl_translate.glossary vndb --id 1234 --out "$WORK/work/glossary.locked.json"
```

**You must review `glossary.locked.json` before translating.** Check:
- `characters` — should `keep_source`/`render` be source or translated? Gender/type correct?
- `terms` — `dst` is the fixed target; `keep_source:true` means leave untranslated.
- Dedup: same family name appearing as two different characters — ensure `aliases` don't merge distinct people.

Locked glossary format:

```json
{
  "characters": [
    {"canonical": "速川 麦", "render": "Hayakawa Mugi", "aliases": ["麦"], "type": "character", "desc": "male name"}
  ],
  "terms": [
    {"src": "炬燵", "dst": "kotatsu", "category": "item"},
    {"src": "渋谷", "dst": "Shibuya", "keep_source": true}
  ]
}
```

Inject the locked glossary into the .cstl's `glossary_text` field (so CSTL UI sees it):

```bash
<PFX> -m cstl_translate.glossary inject "$WORK/work/project.cstl" "$WORK/work/glossary.locked.json"
```

### Module (optional) — reusable per-book settings

A module is a reusable settings pack in `~/.cstl-translate/modules/<name>/` containing: translate prompt, glossary, style/character notes, source/target languages.

```bash
<PFX> -m cstl_translate.module create my-vn --source-lang Japanese --target-lang Indonesian
<PFX> -m cstl_translate.module list
<PFX> -m cstl_translate.module show my-vn
<PFX> -m cstl_translate.module load my-vn --work "$WORK"
```

`load` copies `translate_prompt.md` → `work/user_prompt.md`, `polish_prompt.md` → `work/polish_prompt.md`, and `glossary.locked.json` into the project work dir. Without modules the flow is identical.

---

## Step 3+ — Custom user prompt (like CSTL's per-project prompts)

Translation rules are two layers; **domain/style rules are not hardcoded** — you write them (same as CSTL's prompt_header):

- **Base layer (skill-owned)**: `references/translation_rules.md` — faithful, line-faithful, tag-preserving.
- **Project layer (you write)**: name handling, honorifics, dialogue style, worldbuilding, examples — in `work/user_prompt.md`.

Create or extract it:

```bash
# Start from CSTL's default prompt header for a format
<PFX> -m cstl_translate.prompt init --format numbered --out "$WORK/work/user_prompt.md"
# Formats: numbered | block | xml | jsonl | jsonarray

# Or write it by hand:
cat > "$WORK/work/user_prompt.md" <<'MD'
Keep Japanese honorifics (-san, -kun, -chan). Translate names naturally.
Use 「」 for dialogue. Convert onomatopoeia to natural Indonesian.
MD
```

During translation the agent follows: **translation_rules.md + user_prompt.md (if present) + glossary.locked.json**.

---

## Step 4 — Choose interaction mode

Confirm with the user before starting:

| Mode | Behaviour | When |
|------|-----------|------|
| **A Sample-then-auto (default)** | Translate ~1 batch (~100 lines) and show for approval; then auto batch-by-batch. Pause on unknown new entities. | First time with a new VN |
| **B Every batch** | Show each batch after translation, wait for user OK, then write back. | User wants tight control |
| **C Fully auto** | Run all batches to completion, log unknown entities to `needs_review` for end review. | Style already locked |

---

## Step 5 — Translation loop

### 5a. Read next untranslated batch

```bash
<PFX> -m cstl_translate.batch read "$WORK/work/project.cstl" --size 100
```

Output: JSON array of `{line_num, file, name, message, trans_message}` for `is_translated=false` lines only. Re-running resumes automatically.

```json
[
  {"line_num": 1, "file": "scene01.json", "name": null, "message": "今日はとても良い天気ですね。", "trans_message": null},
  {"line_num": 2, "file": "scene01.json", "name": "太郎", "message": "こんにちは、世界！", "trans_message": null}
]
```

### 5b. Agent translates

**The agent itself translates.** Read the JSON and translate each entry following:

1. `references/translation_rules.md` (line-faithful, preserve tags/placeholders).
2. `work/user_prompt.md` (name style, honorifics, quoting).
3. `work/glossary.locked.json` — `render`/`dst` is ground truth; `keep_source:true` stays untranslated.

New entities not in the locked glossary: Mode A/B → ask the user; Mode C → keep source + append to `needs_review`.

Write results to a JSON file:

```json
[
  {"line_num": 1, "trans_message": "Hari ini cuacanya bagus sekali ya.", "trans_name": null},
  {"line_num": 2, "trans_message": "Halo, dunia!", "trans_name": "Taro"}
]
```

Save as e.g. `$WORK/work/translations_001.json` (name is free).

Rules:
- `line_num` must match input exactly, same order, same count — **never merge/split/drop lines**.
- `trans_name` required when `name` is non-null; omit/null when `name` is null.
- Preserve tags/placeholders (`<i>`, `{0}`, `\n` / `<br>`, `\\n`).

### 5c. Write back

```bash
<PFX> -m cstl_translate.batch write "$WORK/work/project.cstl" "$WORK/work/translations_001.json"
```

- Auto-creates timestamped backup: `project.cstl.bak.YYYYMMDD_HHMMSS`.
- Prints: `applied N translation(s)`.
- Repeat 5a → 5c until `batch read` returns `[]`.

### 5+ Parallel translation (optional, for large VNs)

When the VN has many independent files and **style is locked via Mode A**, multiple subagents can translate different file ranges concurrently. See `references/parallel_translation.md` for the full flow (split, extract, dispatch template, normalization, serial write-back). **Iron rule: subagents never write `project.cstl` — they only produce translation JSONs; the main agent writes back serially.**

---

## Step 6 — Export

```bash
# JSON (VNTP) — one file per original file, or single file
<PFX> -m cstl_translate.export --cstl "$WORK/work/project.cstl" --output "$WORK/out/" --format json

# EPUB — rebuild epub with translated text
<PFX> -m cstl_translate.export --cstl "$WORK/work/project.cstl" --output "$WORK/out/" --format epub

# Luca TXT — rebuild txt files
<PFX> -m cstl_translate.export --cstl "$WORK/work/project.cstl" --output "$WORK/out/" --format luca
```

Uses original structure/tags; respects `is_translated` (untranslated lines export source). For EPUB the original epub bytes are embedded in the .cstl only if the .cstl was created from EPUB via this skill or CSTL — otherwise EPUB export needs the original file via `--epub-source`.

---

## Step 6.5 — Polish / AI Check (optional)

If `work/polish_prompt.md` exists (from module or hand-written), run a QA polish pass over already-translated lines:

```bash
# Read next translated-but-not-polished batch
<PFX> -m cstl_translate.batch read-translated "$WORK/work/project.cstl" --size 100
# Agent polishes per polish_prompt.md + glossary → work/polished_001.json  {line_num, polished_text, polished_name}
<PFX> -m cstl_translate.polish write "$WORK/work/project.cstl" "$WORK/work/polished_001.json"
```

---

## Step 7 — Verify

```bash
<PFX> -m cstl_translate.verify "$WORK/work/project.cstl" "$WORK/work/glossary.locked.json"
```

Checks:
- `empty_translation`: source has content but `trans_message` empty while `is_translated` is true (or vice versa).
- `name_not_preserved`: locked glossary character/term expected in translation but missing.
- `kana_residue`: hiragana/katakana left in Indonesian translation (if enabled).
- `line_count_mismatch`: translated line count ≠ source batch count.

Outputs JSON issue list + summary count. Fix by `batch write` (or `polish write` for polished lines) then re-verify.

### Step 7+ — Scan (supplements verify)

```bash
<PFX> -m cstl_translate.scan "$WORK/work/project.cstl" --locked "$WORK/work/glossary.locked.json" --mode all
# modes: all | discover | terms | strays | merges
```

- `discover`: source names not in glossary that were transliterated/inconsistently kept
- `terms`: glossary terms with `dst` that were left as source
- `strays`: hallucinated names in translation with no source
- `merges`: suspicious merged tokens / missing spaces (OCR artefacts)

Add confirmed findings to `glossary.locked.json` and re-inject.

---

## Appendix A — Command cheat-sheet

```bash
export SKILL_DIR=~/.claude/skills/cstl-translate
export CSTL_PY=~/.venvs/cstl-translate/bin/python
PFX="PYTHONPATH=$SKILL_DIR/scripts $CSTL_PY"

# Parse
$PFX -m cstl_translate.parse --input book.epub --out "$WORK/work/project.cstl" --name "My VN"
# Glossary
$PFX -m cstl_translate.glossary extract "$WORK/work/project.cstl" --out "$WORK/work/glossary.locked.json"
$PFX -m cstl_translate.glossary inject "$WORK/work/project.cstl" "$WORK/work/glossary.locked.json"
# Prompt
$PFX -m cstl_translate.prompt init --format numbered --out work/user_prompt.md
# Batch
$PFX -m cstl_translate.batch read "$WORK/work/project.cstl" --size 100
$PFX -m cstl_translate.batch write "$WORK/work/project.cstl" "$WORK/work/translations_001.json"
# Export
$PFX -m cstl_translate.export --cstl "$WORK/work/project.cstl" --output "$WORK/out/" --format json
# Verify / Scan
$PFX -m cstl_translate.verify "$WORK/work/project.cstl" "$WORK/work/glossary.locked.json"
$PFX -m cstl_translate.scan   "$WORK/work/project.cstl" --locked "$WORK/work/glossary.locked.json" --mode all
# Status
$PFX -m cstl_translate.cstl_io status "$WORK/work/project.cstl"
```

---

## Appendix B — Troubleshooting

**`batch read` returns `[]`:** all lines are `is_translated=true` — ready to export.

**Exported JSON is still source language:** those lines were never `batch write`-en; check `status` counts.

**Want to redo a line:** `batch write` a new `{line_num, trans_message}` — it overwrites by `line_num`.

**Skip a line (e.g. chapter number):** write `trans_message` equal to source or empty with `is_translated` handling per your policy; CSTL exports `trans_message || message` when untranslated.

**EPUB export empty:** ensure original epub bytes are in `.cstl` (`epub_source` field) or pass `--epub-source`.

**Glossary not applied in CSTL UI:** did you `glossary inject`? CSTL UI reads `glossary_text` inside the .cstl.

---

## Appendix C — Slash commands (if installed as plugin)

If installed as a Claude Code plugin, operations are available as `/cstl-translate:<cmd>` (see `commands/` if present). Otherwise use the `<PFX> -m cstl_translate.*` CLI above directly.
