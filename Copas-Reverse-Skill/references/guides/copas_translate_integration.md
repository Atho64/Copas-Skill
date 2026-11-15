# Hand-off to Copas-Translate-Skill

Copas-Reverse-Skill produces `id_input/*.json` and consumes `id_output/*.json`. Everything between — glossary, Indonesian style, batch translation, QA — belongs to **Copas-Translate-Skill**. This page is the exact hand-off.

## Layout assumptions

The VNTP path below exports `id_input`/`id_output` JSON. For CopasTool's native Game Engine path, read [copastool_game_engine.md](copastool_game_engine.md): pass the app backup and complete external cache to translation, preserve scene/text indices, and return the backup for Build Patch. Do not replace that engine project with one parsed from plain VNTP JSON.

```
parent/
├── Copas-Translate-Skill/     # translation skill (this repo, sibling folder)
└── Copas-Reverse-Skill/       # this skill
<somewhere>/<Game>_extract/
├── original/  id_input/  id_output/  metadata/  reports/
```

## Hand-off sequence

```bash
export WORK=/<path>/<Game>_extract
export CR_SKILL=/path/to/Copas-Reverse-Skill
export CT_SKILL="$(dirname "$CR_SKILL")/Copas-Translate-Skill"
export CSTL_PY=python                      # or a venv python with bs4/lxml/chardet for EPUB-only
CT="PYTHONPATH=$CT_SKILL/scripts $CSTL_PY"
CR="PYTHONPATH=$CR_SKILL/scripts $CSTL_PY"

# 1. id_input -> project
$CT -m cstl_translate.parse --input "$WORK/id_input" --out "$WORK/project.copas" --name "My VN"
$CT -m cstl_translate.cstl_io status "$WORK/project.copas"

# 2. glossary: preserve saved entries, then follow the saved glossary task prompt
$CT -m cstl_translate.glossary from-project "$WORK/project.copas" --out "$WORK/glossary.locked.json"
$CT -m cstl_translate.batch read "$WORK/project.copas" --task glossary --size 500 > "$WORK/glossary_batch_001.json"
#   ... agent reads packet instruction, returns typed new terms; review and merge into locked JSON ...
$CT -m cstl_translate.glossary inject "$WORK/project.copas" "$WORK/glossary.locked.json"

# 3. optional prompt file from the saved project prompt (fallback for a new raw import)
$CT -m cstl_translate.prompt init --project "$WORK/project.copas" --out "$WORK/user_prompt.md"

# 4. translation loop — Copas-Translate-Skill Step 5 (agent translates; batch read/write)
$CT -m cstl_translate.batch read "$WORK/project.copas" --size 100 > "$WORK/batch_001.json"
#   ... agent follows packet instruction and context, writes translations_001.json for lines only ...
$CT -m cstl_translate.batch write "$WORK/project.copas" "$WORK/translations_001.json" --expect-batch "$WORK/batch_001.json"

# 5. export back into the inject folder
$CT -m cstl_translate.export --cstl "$WORK/project.copas" --output "$WORK/id_output" --format json

# 6. gate before backfill
$CR -m copas_reverse.vntp pair "$WORK/id_input" "$WORK/id_output"
$CR -m copas_reverse.vntp validate "$WORK/id_output" --against "$WORK/id_input"
```

Notes:

- Copas-Translate-Skill's JSON export writes one file per original, same basenames — exactly what `vntp pair` and `patch build-spec` expect.
- `\\n` stored in the project becomes a real `\n` in the exported JSON; `patch build-spec`/`apply` maps `\n` to the engine byte (e.g. `--newline-hex 0a`).
- Untranslated lines export as source text; patching them is an identity operation (byte-identical), so partial progress can be test-injected safely.
- Interaction mode (sample-then-auto / every batch / fully auto) and the glossary workflow are defined in Copas-Translate-Skill. Use the user's stated preference; target language defaults to Indonesian.
- Follow the packet's active saved `instruction`: translation uses `prompt_header`, glossary uses `glossary_prompt`, review uses `ai_check_prompt`, and agent translation uses `agent_prompt`. Other saved prompts do not govern the active task. Explicit user directions can override project choices; local style files supplement them.
- Translate only packet `lines`; `context_before` and `context_after` are reference-only. Preserve placeholders and meaningful trailing spaces. Parallel worker packets should use `batch read --file EXACT_FILENAME` so full-project preceding/following context is retained outside the assigned files; see the translation skill's parallel reference.
- Spreadsheet edits should merge into the original backed-up project. New projects restored from sheets lack raw export resources and native engine paths/cache.

## Fallback: direct agent translation (sibling missing)

For small extractions (≲ a few hundred lines) translate `id_input` JSONs directly:

1. Read `Copas-Translate-Skill/references/translation_rules.md` if present (line-faithful, tag-preserving, glossary-first). Otherwise apply the same principles.
2. Write `work/user_prompt.md` with the user (honorifics, register, names).
3. Build a small glossary with the user; keep it open during translation.
4. Translate file by file into `id_output/<same-name>.json`; never merge/split/drop lines.
5. Run `vntp validate` + `vntp pair` before backfilling.

For anything larger, tell the user to install Copas-Translate-Skill — glossary + QA tooling matters at scale.
