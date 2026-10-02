# Working with external extraction skills and tools

Extraction can come from anywhere — this skill, another agent skill, or a standalone tool. What this skill owns is the **Indonesian translation stage and the verification discipline**. As long as extracted text arrives in the hand-off format, the pipeline works.

## Hand-off contract (the only requirement)

Text must arrive as VNTP JSON: a UTF-8 array of `{"name": <string|null>, "message": <string>}` — one file per script, file names matching the original scripts.

```json
[{"name": "ため子", "message": "今日はとても良い天気ですね。"}, {"name": null, "message": "空が青い。"}]
```

Drop the files into `<Game>_extract/id_input/` (or point this skill at wherever they are), then continue at Phase 3 (sample injection test) or Phase 4 (full translation).

## Example: extracting with another agent skill

Users may already have an extraction skill installed, e.g. **GalTransl-GalGameReverse-Skill** (https://github.com/GalTransl/GalGameReverse-Skill), which identifies engines and exports dialogue JSON. A combined workflow:

1. **Their skill**: identify the engine, extract scenario text into its work folder (`gt_input/*.json` — same `{"name", "message"}` shape).
2. **This skill**: take those JSONs as `id_input/`, run the sample injection test, then translate to Indonesian via Copas-Translate-Skill (glossary, agent translation, QA).
3. **Backfill**: either through their skill's injection path (put our translated JSONs where its flow expects them) or through this skill's patch pipeline (`carve` → `build-spec` → `apply` → `verify`).

License note: that skill is GPL-3.0 or later. Referring to it by name and interoperating through files is fine and does not affect this repository's licensing — this repo contains **no code or text copied from it**. If you install it, it stays under its own license in its own folder.

**Language fit for Indonesian**: that skill's docs are written for Chinese patches (JIS codepoint replacement, charset/font checks). Indonesian skips all of that — `a–z` and basic punctuation are natively encodable in CP932/Shift-JIS and render without font repacking, so Indonesian is the *easy* case. Extraction/repack mechanics are language-agnostic and transfer as-is; the Indonesian-specific rules (character policy, byte budgets, wrapping) in `encoding_and_display.md` and `writeback_and_verify.md` govern from the moment text lands in `id_input/`, and the Phase 3 sample injection test proves display before any mass translation. (The GalTransl *translator app* is Chinese-first and not needed in this pipeline — translation is agent-driven via Copas-Translate-Skill.)

## If extraction came from outside this skill

Skip our Phase 1–2, but do **not** skip the gates:

1. `$PFX -m copas_reverse.vntp validate <extracted-dir>` — schema, empties, kana inventory.
2. Confirm the extraction is **line-faithful** (no merges/splits/drops) — count lines in a few files against the game text.
3. If injection will use our patch pipeline, we still need offsets: run `carve` and the round-trip test (extraction_playbook). If the external tool also injects, use its path — but run its round-trip/verify too if it has one.
4. From there: Phase 3 sample test → Phase 4 translation as normal.

## Division of labor (recommended)

| Stage | Owner |
|---|---|
| Engine identification, unpacking, extraction | Any capable skill/tool (this skill, or an external one) |
| Glossary, Indonesian translation, QA | Copas-Translate-Skill |
| Offset patching, byte-level verify (when no structure-aware injector exists) | Copas-Reverse-Skill |
| Display testing on a game copy | The user |
