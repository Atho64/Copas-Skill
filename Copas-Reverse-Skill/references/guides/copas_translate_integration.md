# Hand-off to Copas-Translate-Skill

Copas-Reverse-Skill produces `id_input/*.json` and consumes `id_output/*.json`. Everything between — glossary, `CATATAN_CERITA` / `STYLE_GUIDE`, state/provenance, batch/parallel translation, mechanical QA, adversarial review — belongs to **Copas-Translate-Skill**. This page is the exact hand-off.

## Layout assumptions

The VNTP path below exports `id_input`/`id_output` JSON. For CopasTool's native Game Engine path, read [copastool_game_engine.md](copastool_game_engine.md): pass the app backup and complete external cache to translation, preserve scene/text indices, and return the backup for Build Patch. Do not replace that engine project with one parsed from plain VNTP JSON.

```
parent/
├── Copas-Translate-Skill/     # translation skill (sibling folder)
└── Copas-Reverse-Skill/       # this skill
<somewhere>/<Game>_extract/
├── original/  id_input/  id_output/  metadata/  reports/
```

## Hand-off sequence

Primary target is **Japanese → Indonesian (`--source-lang Japanese --target-lang Indonesian`)**, with full profile support for **English → Indonesian** and **Japanese → English** as well.

```bash
export WORK=/<path>/<Game>_extract
export CR_SKILL=/path/to/Copas-Reverse-Skill
export CT_SKILL="$(dirname "$CR_SKILL")/Copas-Translate-Skill"
export CSTL_PY=python
CT="PYTHONPATH=$CT_SKILL/scripts $CSTL_PY"
CR="PYTHONPATH=$CR_SKILL/scripts $CSTL_PY"

# 1. id_input -> project (specify --source-lang / --target-lang when not Japanese -> Indonesian)
$CT -m cstl_translate.parse --input "$WORK/id_input" --out "$WORK/project.copas" --name "My VN"
$CT -m cstl_translate.cache stats "$WORK/project.copas"

# 2. glossary (VNDB seed + pre-translation pending term discovery)
# Optional: seed official VNDB character cast/names first:
$CT -m cstl_translate.glossary vndb "$WORK/project.copas" --vn v17 --out "$WORK/glossary.locked.json" --cast-out "$WORK/vndb_cast.md"
$CT -m cstl_translate.glossary from-project "$WORK/project.copas" --out "$WORK/glossary.locked.json"
$CT -m cstl_translate.batch read "$WORK/project.copas" --task glossary --size 500 > "$WORK/glossary_batch_001.json"
#   ... agent returns typed terms; merge, lint, and inject ...
$CT -m cstl_translate.glossary lint --locked "$WORK/glossary.locked.json"
$CT -m cstl_translate.glossary inject "$WORK/project.copas" "$WORK/glossary.locked.json"
$CT -m cstl_translate.scan "$WORK/project.copas" --locked "$WORK/glossary.locked.json" --mode pending

# 3. translation loop — serial (small/sample) or parallel read-once bundles (large VN)
# Serial:
$CT -m cstl_translate.batch read "$WORK/project.copas" --size 100 > "$WORK/batch_001.json"
$CT -m cstl_translate.batch write "$WORK/project.copas" "$WORK/translations_001.json" --expect-batch "$WORK/batch_001.json"
# Parallel (after Mode A sample style confirmation):
$CT -m cstl_translate.batch split "$WORK/project.copas" --target 250 --out-dir "$WORK/par" --context 20
$CT -m cstl_translate.precedents "$WORK/project.copas" --for "$WORK/par"/grp_*_src.json --locked "$WORK/glossary.locked.json" --out "$WORK/CATATAN_CERITA.md"
$CT -m cstl_translate.batch bundle "$WORK/project.copas" "$WORK/par"/grp_*_src.json --locked "$WORK/glossary.locked.json" --include "$WORK/STYLE_GUIDE.md" "$WORK/CATATAN_CERITA.md"
# ... workers write trans_N.jsonl + newterms_N.txt; coordinator validates & writes serially ...
$CT -m cstl_translate.batch validate "$WORK/par/grp_1_src.json" "$WORK/par/trans_1.jsonl" --project "$WORK/project.copas"
$CT -m cstl_translate.glossary merge-newterms --locked "$WORK/glossary.locked.json" "$WORK/par"/newterms_*.txt --apply --inject "$WORK/project.copas"
$CT -m cstl_translate.batch write "$WORK/project.copas" "$WORK/par"/trans_*.jsonl

# 4. quality loop (verify + scan + audit) + optional adversarial review (`review` + `batch apply`)
$CT -m cstl_translate.verify "$WORK/project.copas" "$WORK/glossary.locked.json"
$CT -m cstl_translate.scan "$WORK/project.copas" --locked "$WORK/glossary.locked.json" --mode all
$CT -m cstl_translate.audit "$WORK/project.copas" --out "$WORK/audit.json"

# 5. export back into the inject folder (or deliverable .copas-only ZIP)
$CT -m cstl_translate.export --cstl "$WORK/project.copas" --output "$WORK/out_zip" --format copas-zip
$CT -m cstl_translate.export --cstl "$WORK/project.copas" --output "$WORK/id_output" --format json

# 6. gate before backfill
$CR -m copas_reverse.vntp pair "$WORK/id_input" "$WORK/id_output"
$CR -m copas_reverse.vntp validate "$WORK/id_output" --against "$WORK/id_input"
```

Notes:

- Copas-Translate-Skill's JSON export writes one file per original, same basenames — exactly what `vntp pair` and `patch build-spec` expect.
- `\\n` stored in the project becomes a real `\n` in the exported JSON; `patch build-spec`/`apply` maps `\n` to the engine byte (e.g. `--newline-hex 0a`).
- Untranslated lines export as source text; patching them is an identity operation (byte-identical), so partial progress can be test-injected safely.
- Interaction mode (sample-then-auto / every batch / fully auto), `state` decisions/provenance, and adversarial review are defined in Copas-Translate-Skill.
- Translate only packet `lines`; `context_before` and `context_after` are reference-only.
- Spreadsheet edits should merge into the original backed-up project. New projects restored from sheets lack raw export resources and native engine paths/cache.

## Fallback: direct agent translation (sibling missing)

For small extractions (≲ a few hundred lines) translate `id_input` JSONs directly:

1. Read `Copas-Translate-Skill/references/translation_rules.md` and `references/language_pairs.md` if present.
2. Write `work/user_prompt.md` with the user (honorifics, pronouns, register, names).
3. Build a small glossary with the user; keep it open during translation.
4. Translate file by file into `id_output/<same-name>.json`; never merge/split/drop lines.
5. Run `vntp validate` + `vntp pair` before backfilling.

For anything larger, install Copas-Translate-Skill so glossary, bundle, audit, and QA tooling run cleanly at scale.
