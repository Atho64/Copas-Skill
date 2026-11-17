# External & Dual-Model Review Hand-off

Use this workflow when sending translated lines to an external reviewer (human proofreader, Codex, or a second model family) and bringing edits safely back through `cstl_translate` gates.

## 1. Hand off a Snapshot + Rule Card

```bash
# Export current translations in range A-B (or only lines changed since a baseline snapshot)
<PFX> -m cstl_translate.cache dump work/project.copas --range 1-500 --out work/ext_snapshot.json
# Optional re-review of only modified lines:
<PFX> -m cstl_translate.cache dump work/project.copas --changed-since work/project.copas.pre_review --out work/ext_delta.json

# Compact rule card (settled renderings, source errata, token exceptions, protected fixes)
<PFX> -m cstl_translate.state card work/project.copas --range 1-500 > work/ext_rules.md
```

Ask the external reviewer to return JSONL findings (one object per line):

```json
{"line_num": 412, "category": "A", "severity": 2, "offending": "dia tidak tahu", "proposed": "dia pura-pura tidak tahu", "reason": "Source is 知らん顔する (feign ignorance), not literal ignorance"}
```

(`text_index`/`i`, `current`, `fix`, `sev`, `issue` field aliases are also accepted on import.)

## 2. Import Through the Mechanical Gate

```bash
<PFX> -m cstl_translate.review import work/project.copas work/their_findings.jsonl --group ext --source codex --run ext-1
<PFX> -m cstl_translate.review pre work/project.copas --run ext-1 work/review/ext-1/findings_ext.jsonl
<PFX> -m cstl_translate.review merge work/project.copas --run ext-1 ext
<PFX> -m cstl_translate.review pick work/project.copas --run ext-1 ext --min-sev 2
<PFX> -m cstl_translate.batch apply work/project.copas work/review/ext-1/apply_pick.json --source codex --reason "External meaning review"
```

- Even if the external reviewer read an older snapshot, `review pre` verifies `offending` occurs **exactly once** in the current text and rejects stale items (`ambiguous(0)`).
- `--source codex` (or `dual`/`external`/`user`/`editor`) logs removed snippets to `provenance.jsonl`; later adversarial passes cannot revert those fixes (`E_reverts_fix`).

## 3. Dual-Model Meaning Review (`dual-merge`)

When two different model families review the same lines independently (`modelA_g1.jsonl`, `modelB_g1.jsonl` with `{line_num, cat, sev, issue, fix}`):

```bash
<PFX> -m cstl_translate.review dual-merge work/project.copas work/dual/modelA_*.jsonl work/dual/modelB_*.jsonl --out work/dual/fix_input.json
```

`dual-merge` sorts lines by `agree` descending (`agree=2` lines flagged by both reviewers first), then `maxsev`. An editor applies minimal patches `{line_num, patches: [[old, new], ...], reason}` and commits via `batch apply ... --source dual`.
