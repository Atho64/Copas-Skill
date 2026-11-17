# Parallel Translation & Polish (Large VN Acceleration)

Use this workflow when translating or polishing large VNs concurrently across independent file groups. Every orchestration step uses deterministic CLI commands (`scan --mode pending`, `batch split`, `glossary filter`, `batch bundle`, `precedents`, `batch validate`, `glossary merge-newterms`, `batch write`, `progress`) — no ad-hoc temporary Python heredocs.

**Placeholders**: `<PFX>` = `PYTHONPATH="$CT_SKILL/scripts" "$CSTL_PY"`, `<WORK>` = project work dir containing `project.copas` (or `project.copas.zip`).

---

## When to Use

- Large project (hundreds+ lines) with settled style.
- **Style settled first**: translate one opening sample (~1 chapter/scene) using Intervention Mode A and get user sign-off on register, pronouns, honorifics, and quotation style before launching parallel workers.
- Locked glossary (`work/glossary.locked.json`) and saved project prompts are ready.

## Iron Rule: Subagents Never Touch `project.copas`

`batch write` / `polish write` / `batch apply` perform locked read-modify-write of `project.copas`. Parallel workers only write their assigned `trans_<N>.jsonl` (or `polished_<N>.jsonl`) + `newterms_<N>.txt`. The coordinator validates and writes serially.

```
Coordinator: scan --mode pending -> batch split -> precedents -> batch bundle
  ├─ worker 1  reads ONE file (bundle_1.md) -> writes ONCE (trans_1.jsonl + newterms_1.txt)
  ├─ worker 2  reads ONE file (bundle_2.md) -> writes ONCE (trans_2.jsonl + newterms_2.txt)
  └─ worker N  ...
Coordinator: batch validate -> retry failures -> merge-newterms (check CONFLICT) -> batch write -> verify + scan + audit
```

---

## Step-by-Step Pipeline

### 1. Discover New Pending Terms Before Splitting
```bash
<PFX> -m cstl_translate.scan work/project.copas --locked work/glossary.locked.json --mode pending
```
Settle recurring new speakers, places, or coined terms into `work/glossary.locked.json` (and `glossary inject`) before splitting so parallel workers don't invent conflicting spellings.

### 2. Split Into File-Aligned Groups
```bash
<PFX> -m cstl_translate.batch split work/project.copas --target 250 --out-dir work/par --context 20
```
- Groups consecutive files in `file_order` around `--target` lines (splitting huge files evenly, folding tiny tails).
- Writes `work/par/_stage.json`, `grp_<N>_src.json`, and `grp_<N>_ctx.json` (`context_before` + `context_after` drawn from the full project, including neighboring files!).
- To target specific files or resume only remaining work, add `--file scene01.json ...` or `--range A-B`.

### 3. Build `STYLE_GUIDE.md` & `BOOK_BIBLE.md` (Recommended)
- Generate `work/STYLE_GUIDE.md` from `references/style_guide_template.md`, anchoring rules on the user-approved sample batch.
- If part of the VN is already translated, extract precedents mechanically:
  ```bash
  <PFX> -m cstl_translate.precedents work/project.copas --for work/par/grp_*_src.json --locked work/glossary.locked.json --out work/BOOK_BIBLE.md
  ```
- For brand-new VNs with complex casts/relationships, fill `references/book_bible_template.md` (especially §2 Pairwise Pronoun Matrix and §5 Policy Decisions).

### 4. Generate Read-Once Group Bundles (Token Saver)
```bash
<PFX> -m cstl_translate.batch bundle work/project.copas work/par/grp_*_src.json --locked work/glossary.locked.json --include work/STYLE_GUIDE.md work/BOOK_BIBLE.md
```
Each `work/par/bundle_<N>.md` packs into **one file**:
- Delivery contract (`trans_<N>.jsonl` + `newterms_<N>.txt` paths & exact schema)
- `state card` (settled decisions, source errata, token exceptions, protected meaning fixes)
- Resolved active project prompt (`prompt_header`)
- `STYLE_GUIDE.md` / `BOOK_BIBLE.md` / `user_prompt.md`
- **Filtered group glossary TSV** (only characters & terms appearing in group `N`)
- `context_before` & `context_after` (read-only) + `Assigned Lines (JSONL)`

### 5. Monitor Live Progress (Optional)
```bash
<PFX> -m cstl_translate.progress work/project.copas --once
<PFX> -m cstl_translate.progress work/project.copas --watch
<PFX> -m cstl_translate.progress work/project.copas --serve 8765 --open
```

### 6. Dispatch Workers (Rolling Waves of ~4–6 Agents)
Send identical system instructions first (maximizes prompt caching) and have each worker **read `bundle_<N>.md` once and write `trans_<N>.jsonl` (+ `newterms_<N>.txt`) once**:

> You are a literary VN translator for group `{N}` ({COUNT} lines).
> Read `<WORK>/par/bundle_{N}.md` once, along with `$CT_SKILL/references/language_pairs.md#<PAIR>`.
> Follow the `## Delivery (write once)` section in `bundle_{N}.md`: write ALL {COUNT} JSONL lines to `<WORK>/par/trans_{N}.jsonl` and out-of-glossary proper nouns/terms to `<WORK>/par/newterms_{N}.txt`.
> Hard rules: 1:1 `line_num`, exact order, non-empty `trans_name` iff source `name` is non-empty, keep tags/placeholders/`\n`/trailing spaces verbatim, follow `STYLE_GUIDE.md` and the filtered glossary, never touch `project.copas` or run `batch write`.
> Return only: translated line count, newterms count, and up to 5 uncertain lines (`line_num` + note).

### 7. Validate Each Group & Merge New Terms
```bash
<PFX> -m cstl_translate.batch validate work/par/grp_1_src.json work/par/trans_1.jsonl --project work/project.copas
```
- If `validate` reports hard errors (`missing_index`, `extra_index`, `duplicate_index`, `speaker_missing`, `structural_tokens`, etc.), re-dispatch **only that group** with the error list.
- Preview cross-worker new-term conflicts BEFORE writing back:
  ```bash
  <PFX> -m cstl_translate.glossary merge-newterms --locked work/glossary.locked.json work/par/newterms_*.txt
  ```
  If `CONFLICT` appears (two workers rendered the same new term differently), unify the `trans_*.jsonl` files first, then run with `--apply --inject work/project.copas`.

### 8. Serial Write-Back + Mechanical QA Loop
```bash
<PFX> -m cstl_translate.batch write work/project.copas work/par/trans_*.jsonl
<PFX> -m cstl_translate.glossary lint --locked work/glossary.locked.json
<PFX> -m cstl_translate.verify work/project.copas work/glossary.locked.json
<PFX> -m cstl_translate.scan work/project.copas --locked work/glossary.locked.json --mode all
<PFX> -m cstl_translate.audit work/project.copas --out work/audit.json
```
Run this QA loop at the end of **every wave** when translating in waves so newly settled terms feed into subsequent waves immediately.

---

## Parallel Polish Pass

Run the same pipeline with `--stage polish`:
```bash
<PFX> -m cstl_translate.batch split work/project.copas --stage polish --target 250 --out-dir work/par --context 15
<PFX> -m cstl_translate.batch bundle work/project.copas work/par/grp_*_src.json --stage polish --locked work/glossary.locked.json --include work/polish_prompt.md work/STYLE_GUIDE.md
# ... workers write work/par/polished_N.jsonl (`{"line_num": N, "polished_text": "...", "polished_name": ...}`) ...
<PFX> -m cstl_translate.batch validate work/par/grp_1_src.json work/par/polished_1.jsonl --project work/project.copas
<PFX> -m cstl_translate.polish write work/project.copas work/par/polished_*.jsonl
```
