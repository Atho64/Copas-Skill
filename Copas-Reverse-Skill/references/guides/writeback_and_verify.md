# Write-back and verification

How translated `id_output/*.json` gets back into the game — and how we prove nothing else broke.

## Strategy ladder (prefer the top that works)

1. **Structure-aware rebuild** (best): the engine page documents the script structure — rebuild text records and re-serialize with the engine's own packer (engine tool or our scripts). Handles length changes naturally. Required when scripts carry per-record lengths, pointers, or checksums.
2. **Same-length offset patch** (default here): rewrite text in place at carved offsets; file size never changes; all pointers/lengths stay valid. Works for flat text blobs and many index-less formats. This is what `copas_reverse.patch` does.
3. **External patcher**: VNTextPatch-style tools that extract/inject for a specific engine. Fine when the engine page recommends one — same verification applies.

## Same-length patch workflow

Per script file `X`:

```bash
# carve once per file (Phase 2), then after translation:
$PFX -m copas_reverse.patch build-spec \
    --carve metadata/carve_X.json \
    --input  id_input/X.json --output id_output/X.json \
    --file-label <game-relative-path> \
    --encoding cp932 --newline-hex 0a --pad space \
    --out metadata/patch_X.json

$PFX -m copas_reverse.patch apply --spec metadata/patch_X.json \
    --src original/X.bin --out <OutputDir>/<game-relative-path>

$PFX -m copas_reverse.patch verify --spec metadata/patch_X.json \
    --src original/X.bin --dst <OutputDir>/<game-relative-path>
```

Properties you can rely on:

- `build-spec` matches by exact text; it reports every line it could not match (`unmatched`) — those lines will **not** be patched. Zero unmatched is the goal; anything else needs the structure-aware path for those lines.
- `apply` refuses to write when any translation exceeds its slot (OVERFLOW). Options: shorten the line, or switch strategy. `--truncate` exists for deliberate cases — only with the user informed.
- `apply` checks `orig_hex` before writing: stale offsets (file changed) abort the patch.
- `verify` fails if **any** byte outside the declared ranges changed, or if patched bytes differ from the spec. A passing `verify` + passing display test is our definition of "done" for a file.
- Backfilling unchanged text reproduces the original bytes exactly (tested in `tests/`).

## Overflow handling (Indonesian notes)

Indonesian is 1 byte/char vs Japanese 2 bytes/char, so slots are usually generous. When OVERFLOW hits:

1. Shorten the translation first (Copas-Translate-Skill style guide covers register; a 5–10% trim is normal editorial work).
2. If the *engine* wraps text automatically, ask the user before switching to a structure-aware rebuild that changes lengths — that class of patch is riskier.
3. Never pad into terminators: keep terminators outside carved runs (the carve dump and engine pages show where they are).

## Archive repacking

If scripts live inside an archive, rebuild it with the engine's packer (engine page lists tools/commands) **into the output dir**, preserving entry order and names. Some engines tolerate rebuilt archives; some need original compression settings — the page notes it. When unsure, deliver loose patched files + a repack script the user can run in their game copy.

## Final QA

- `vntp pair id_input id_output` — exit 0.
- `vntp validate id_output` — no kana residue, no token drift (`--against id_input`).
- `patch verify` passed for every file; count of patched files == count of exported files.
- Rebuilt archives load (user test), or loose files delivered with instructions.
- Display test on the game copy: intro, mid-game, choices, backlog, save/load, crash-free scene transitions.
- Delivery report table (SKILL.md) written to `reports/delivery.md`, including everything NOT handled (images with text, UI, system menus).
