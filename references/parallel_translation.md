# Parallel Translation (large VN acceleration)

Run Step 5's serial batch loop as **multiple subagents translating different file ranges concurrently**. Wall-clock ≈ slowest agent.

**Placeholders**: `<PFX>` = `PYTHONPATH="$SKILL_DIR/scripts" "$CSTL_PY"`; `<WORK>` = work dir (e.g. `~/my-vn`).

## When to use

- Large VN (hundreds+ lines) with many independent files/batches.
- **Style already locked**: translate ~1 batch via Mode A and get user approval first. Otherwise subagents diverge.
- Locked glossary + `work/user_prompt.md` are ready (they guarantee term consistency; new entities → keep source + record).

## Iron rule: subagents never write project.cstl

`batch write` does read-modify-write of `project.cstl`. Concurrent writes → corruption.

```
✗ each subagent batch write to same project.cstl  — race, will corrupt
✓ subagents only produce translation JSONs; main agent serially writes back — safe
```

**Architecture:**

```
main: split batches → extract per-group source JSONs → write STYLE_GUIDE.md
  ├─ agent1 (files A-B)  read glossary+rules+style+input → produce trans_1.json + newterms_1.txt
  ├─ agent2 (files C-D)  … (concurrent, no shared writes)
  └─ agentN …
main: validate outputs → normalize drift → serial batch write each → merge new terms → verify → export
```

## Steps

### 1. Split (by file, balanced by untranslated count)

```python
# <PFX> python - <<'PY' — enumerate files + untranslated counts
import json
d=json.load(open('work/project.cstl', encoding='utf-8'))
lines=d.get('lines',[])
from collections import Counter
cnt=Counter(l['file'] for l in lines if not l.get('is_translated'))
for f,n in cnt.most_common(): print(f"{f}: {n}")
# Group files into ~200-300 untranslated lines per group, at file boundaries
# PY
```

Concurrency: aim for ~5–8 concurrent agents, each ~200–300 lines. More groups than concurrency → dispatch in waves (`wait` then next wave).

### 2. Extract per-group source files (untranslated only, with rolling context)

```python
import json
d=json.load(open('work/project.cstl', encoding='utf-8'))
lines=d['lines']
CONTEXT_N=10  # preceding lines to include as read-only context (does NOT get translated)
groups={1:["scene01.json","scene02.json"], 2:["scene03.json"], ...}  # by file
num_to_idx={l["line_num"]:i for i,l in enumerate(lines)}
for g, files in groups.items():
    seg=[{"line_num":l["line_num"],"file":l["file"],"name":l["name"],"message":l["message"]}
         for l in lines if l["file"] in files and not l.get("is_translated")]
    # Preceding context: up to CONTEXT_N lines before first line in this group (read-only)
    if seg:
        first_idx=num_to_idx[seg[0]["line_num"]]
        ctx_start=max(0, first_idx-CONTEXT_N)
        context=[{"line_num":lines[i]["line_num"],"file":lines[i]["file"],"name":lines[i].get("name"),"message":lines[i].get("message"),"trans_message":lines[i].get("trans_message"),"is_translated":bool(lines[i].get("is_translated"))} for i in range(ctx_start, first_idx)]
    else:
        context=[]
    # Payload subagents read: {"context": [...], "batch": [...]} — context is read-only, batch is 1:1
    json.dump({"context":context, "batch":seg}, open(f'/tmp/cstl_grp_{g}_src.json','w', encoding='utf-8'), ensure_ascii=False, indent=1)
```

Or use the built-in helper directly: `<PFX> -m cstl_translate.batch read work/project.cstl --size 100 --context 10` → `{"context": [...], "batch": [...]}`.

### 3. Write STYLE_GUIDE.md

Use `references/style_guide_template.md` to produce `<WORK>/work/STYLE_GUIDE.md` (quotes, spacing, name/term handling, dates). All agents must read it.

### 4. Dispatch subagents concurrently (one Tool call per agent, same message)

Each prompt must be self-contained (see template below). Key points:
- Read `STYLE_GUIDE.md` + `glossary.locked.json` + `translation_rules.md`.
- Read own `/tmp/cstl_grp_N_src.json`, translate line-by-line **1:1** (`line_num` unchanged, count unchanged, order unchanged).
- Produce `/tmp/cstl_trans_N.json` via a **Python builder script** (avoid hand-written JSON escaping; use `json.dump(ensure_ascii=False)`).
- Write kept-as-source new names to `/tmp/cstl_newterms_N.txt` (one per line).
- **Do not** touch `project.cstl` or run `batch write`.

### 5. Validate outputs

```python
for g in groups:
    src=json.load(open(f'/tmp/cstl_grp_{g}_src.json', encoding='utf-8'))
    tr=json.load(open(f'/tmp/cstl_trans_{g}.json', encoding='utf-8'))
    assert [x['line_num'] for x in src]==[x['line_num'] for x in tr]
    assert all(x.get('trans_message','').strip() for x in tr)
```

If a group fails (count/mismatch, empty translations) → **re-dispatch only that agent** with the validation error + 1:1 emphasis.

### 6. Normalize drift (three common drifts)

| Drift | Detect | Fix |
|-------|--------|-----|
| Quote style 「」 vs "" | count `「` per group | normalize to project's chosen style |
| Name/term/title inconsistency | spot-check key characters | rewrite against `user_prompt.md` + glossary |
| New names transliterated per-agent | look at newterms | unify to keep-source, update glossary once |

### 7. Serial write-back + finish

```bash
for g in 1 2 3 4 5 6 7; do
  <PFX> -m cstl_translate.batch write "$WORK/work/project.cstl" /tmp/cstl_trans_$g.json
done
```

Then: merge `cstl_newterms_*` into glossary (default `keep_source`), `verify`, fix, `export`.

Completion criterion: `batch read` returns `[]` (no `is_translated=false` left).

## Subagent prompt template (fill {N}/{FILES}/{COUNT})

> You are a literary VN translator for {COUNT} lines from files {FILES}. Earlier batches were translated and approved — your output must match that style **exactly**.
>
> Step 1 — Read: `<WORK>/work/STYLE_GUIDE.md`, `<WORK>/work/glossary.locked.json`, `<WORK>/work/user_prompt.md` (if exists), `$SKILL_DIR/references/translation_rules.md`.
>
> Step 2 — Read input `/tmp/cstl_grp_{N}_src.json` (`{line_num,file,name,message}` array, {COUNT} lines).
>
> Step 3 — Translate each line to target language. Hard rules: names/terms per locked glossary; unknown proper nouns → keep source; honorifics/style per user prompt; tags/placeholders verbatim; OCR merges (e.g. `Marlowstepped`) → restore boundary; **1:1** — never merge/split/drop.
>
> Step 4 — Write a Python builder `/tmp/cstl_build_{N}.py`: define `T={line_num:"translation"}` + `TN={line_num:"name"}` for every input, load source, build `[{"line_num":i,"trans_message":T[i],"trans_name":TN.get(i)}]` in input order, assert no missing, `json.dump` to `/tmp/cstl_trans_{N}.json` (`ensure_ascii=False`). Run it and print count + 0 missing (=={COUNT}).
>
> Step 5 — Write kept-as-source new proper nouns to `/tmp/cstl_newterms_{N}.txt` (one per line; empty if none).
>
> Constraints: **do not** modify `project.cstl` or glossary files; **do not** run `batch write` or any `cstl_translate` command; only produce those two /tmp files. Translate fully, do not summarize or skip.
>
> Return: count translated, 0-missing confirmation (=={COUNT}), new keep-source list.
