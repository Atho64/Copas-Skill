# Parallel Translation (large VN acceleration)

Use this workflow when the user chooses parallel translation: **multiple subagents translate different file ranges concurrently**.

**Placeholders**: `<PFX>` = `PYTHONPATH="$SKILL_DIR/scripts" "$CSTL_PY"`; `<WORK>` = work dir (e.g. `~/my-vn`).

## When to use

- Large VN (hundreds+ lines) with many independent files/batches.
- **Style is settled** from saved project prompts and the confirmed glossary. Use a sample when those choices are unresolved, respecting the user's chosen interaction mode.
- Locked glossary and the saved project prompt are ready. `work/user_prompt.md` and the style guide supplement those project choices unless the user requested an override.

## Iron rule: subagents never write project.copas

`batch write` does read-modify-write of `project.copas`. Concurrent writes → corruption.

```
✗ each subagent batch write to same project.copas  — race, will corrupt
✓ subagents only produce translation JSONs; main agent serially writes back — safe
```

**Architecture:**

```
main: split batches → extract per-group prompt/context packets → write STYLE_GUIDE.md
  ├─ agent1 (files A-B)  read glossary+rules+style+input → produce trans_1.json + newterms_1.txt
  ├─ agent2 (files C-D)  … (concurrent, no shared writes)
  └─ agentN …
main: validate outputs → normalize drift → serial batch write each → merge new terms → verify → export
```

## Steps

### 1. Split (consecutive files in project order, balanced by untranslated count)

```python
# <PFX> python - <<'PY' — enumerate files + untranslated counts
from cstl_translate.cstl_io import load_cstl
d=load_cstl('work/project.copas')
lines=d.get('lines',[])
from collections import Counter
cnt=Counter(l['file'] for l in lines if not l.get('is_translated') and not l.get('_hidden') and (l.get('message') or '').strip())
for f,n in cnt.most_common(): print(f"{f}: {n}")
# Group consecutive files in file_order into ~200-300 untranslated lines per group
# PY
```

Choose concurrency within the environment's available agent slots, with roughly 200–300 lines per group. More groups than concurrency → dispatch in waves (`wait` then next wave).

### 2. Extract per-group task packets (untranslated lines plus reference context)

```python
import json
from pathlib import Path
from cstl_translate.cstl_io import load_cstl
from cstl_translate.batch import read_context_batch
d=load_cstl('work/project.copas')
lines=d['lines']
groups={1:["scene01.json","scene02.json"], 2:["scene03.json"]}  # replace with consecutive file groups
for g, files in groups.items():
    count=sum(1 for l in lines if l["file"] in files and not l.get("is_translated")
              and not l.get("_hidden") and (l.get("message") or "").strip())
    if not count:
        continue
    packet=read_context_batch('work/project.copas', size=count, files=files)
    Path(f'/tmp/cstl_grp_{g}_src.json').write_text(
        json.dumps(packet, ensure_ascii=False, indent=1), encoding='utf-8')
```

Each packet includes the active saved translation `instruction`, all saved `prompts`, glossary, languages, `currentBackground`, `context_type`, and separate `context_before`, `lines`, and `context_after` arrays. Context uses saved `context_lines` and `context_lines_after` and comes from the full project, including neighboring files outside the worker's assignment. Following context defaults to zero if the project has not enabled it; use `before=N, after=N` only for a requested override.

For a large file, create smaller packets with `files=[filename], size=100, offset=N`; offsets count eligible untranslated lines within those files. The CLI equivalent is `batch read ... --file scene01.json --file scene02.json --size 100 --offset N`. Only packet `lines` belongs to the worker. Never translate its context arrays.

Extract all disjoint packets for a concurrent wave before writing translations. Offsets are relative to that snapshot's untranslated lines; after write-back, recompute them, or read the next remaining batch with offset zero.

Re-extract packets for later waves after earlier workers have written back. Concurrent neighbors may still have untranslated context; use the available source evidence and do not invent a previous worker's translation or a story summary. The packet's summary is the one saved in the project.

### 3. Write STYLE_GUIDE.md

Use `references/style_guide_template.md` to produce `<WORK>/work/STYLE_GUIDE.md` (quotes, spacing, name/term handling, dates). All agents must read it.

### 4. Dispatch subagents concurrently (one Tool call per agent, same message)

Each prompt must be self-contained (see template below). Key points:
- Read `STYLE_GUIDE.md` + `glossary.locked.json` + `translation_rules.md`.
- Read own `/tmp/cstl_grp_N_src.json`, follow its active `instruction`, and use before/after context according to `context_type` (source text, existing translation, or both). Translate only `lines` **1:1** (`line_num` unchanged, count unchanged, order unchanged).
- Produce `/tmp/cstl_trans_N.json` via a **Python builder script** (avoid hand-written JSON escaping; use `json.dump(ensure_ascii=False)`).
- Write kept-as-source new names to `/tmp/cstl_newterms_N.txt` (one per line).
- **Do not** touch `project.copas` or run `batch write`.

### 5. Validate outputs

```python
for g in groups:
    src=json.load(open(f'/tmp/cstl_grp_{g}_src.json', encoding='utf-8'))['lines']
    tr=json.load(open(f'/tmp/cstl_trans_{g}.json', encoding='utf-8'))
    assert [x['line_num'] for x in src]==[x['line_num'] for x in tr]
    assert all(x.get('trans_message','').strip() for x in tr)
```

If a group fails (count/mismatch, empty translations) → **re-dispatch only that agent** with the validation error + 1:1 emphasis.

### 6. Normalize drift (three common drifts)

| Drift | Detect | Fix |
|-------|--------|-----|
| Quote style 「」 vs "" | count `「` per group | normalize to project's chosen style |
| Name/term/title inconsistency | spot-check key characters | rewrite against saved project prompt + glossary and confirmed style supplements |
| New names transliterated per-agent | look at newterms | unify to keep-source, update glossary once |

### 7. Serial write-back + finish

```bash
for g in 1 2 3 4 5 6 7; do
  <PFX> -m cstl_translate.batch write "$WORK/work/project.copas" /tmp/cstl_trans_$g.json --expect-batch /tmp/cstl_grp_${g}_src.json
done
```

Then: merge `cstl_newterms_*` into glossary (default `keep_source`), `verify`, fix, `export`.

Completion criterion: default `batch read` has an empty `lines` array (`[]` with `--lines-only`). Hidden/empty untranslated lines can remain in status and should be reported separately.

## Subagent prompt template (fill {N}/{FILES}/{COUNT})

> You are a literary VN translator for {COUNT} lines from files {FILES}. Apply the saved project style and confirmed user supplements consistently across all assigned lines.
>
> Step 1 — Read: `<WORK>/work/STYLE_GUIDE.md`, `<WORK>/work/glossary.locked.json`, `<WORK>/work/user_prompt.md` (if exists), `$SKILL_DIR/references/translation_rules.md`.
>
> Step 2 — Read `/tmp/cstl_grp_{N}_src.json`, a task packet with {COUNT} assigned `lines`. Follow its active `instruction` and saved glossary. Use `context_before`, `context_after`, reference languages, and `currentBackground` only as evidence; follow `context_type` when choosing source/translated context. Following context happens later in the story.
>
> Step 3 — Translate only packet `lines` to the saved target language. Hard rules: names/terms per locked glossary; unknown proper nouns → keep source; honorifics/style per saved project prompt and confirmed user supplements; tags/placeholders verbatim; OCR merges (e.g. `Marlowstepped`) → restore boundary; **1:1** — never merge/split/drop. Context rows must not appear in the output.
>
> Step 4 — Write a Python builder `/tmp/cstl_build_{N}.py`: define `T={line_num:"translation"}` + `TN={line_num:"name"}` for every assigned input, load packet `lines`, build `[{"line_num":i,"trans_message":T[i],"trans_name":TN.get(i)}]` in that order, assert no missing, `json.dump` to `/tmp/cstl_trans_{N}.json` (`ensure_ascii=False`). Run it and print count + 0 missing (=={COUNT}).
>
> Step 5 — Write kept-as-source new proper nouns to `/tmp/cstl_newterms_{N}.txt` (one per line; empty if none).
>
> Constraints: **do not** modify `project.copas` or glossary files; **do not** run `batch write` or any `cstl_translate` command; only produce those two /tmp files. Translate fully, do not summarize or skip.
>
> Return: count translated, 0-missing confirmation (=={COUNT}), new keep-source list.
