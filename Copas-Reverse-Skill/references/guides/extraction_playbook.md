# Extraction playbook

From packed game files to `id_input/*.json` (VNTP) — with the round-trip contract that makes backfill safe.

## VNTP JSON format

```json
[
  {"name": "ため子", "message": "今日はとても良い天気ですね。\n散歩に行きましょう。"},
  {"name": null, "message": "空が青い。"}
]
```

- UTF-8, JSON array; `name` is a string or `null`; `message` is never empty.
- Hard line breaks inside a message are `\n` (real newline in the JSON). How they map to engine bytes is decided at injection time (`--newline-hex`).
- Choices/options are exported as regular messages (exporter may prefix them, e.g. `name: null`, and the engine page says how to recognize them).
- This is exactly the format Copas-Translate-Skill parses (`--type json`) and exports (`--format json`).

## Steps

### 1. Unpack

Use the engine page's tool or algorithm. Unpack into a scratch dir, e.g. `<Game>_extract/unpacked/`. Keep the original archive untouched. If the archive is encrypted and the page does not document the scheme — stop and report.

### 2. Locate scenario scripts

Signals: largest files after unpack, high cp932/UTF-8 hit rate (`carve scan`), long CJK runs (`carve file ... --require-cjk`), file names like `scene`, `script`, `nss`, `sjs`, `ss`, `mes`. System/menu strings live elsewhere; the engine page says which files are dialogue.

### 3. Export semantically

Prefer structure-aware extraction (per engine page): parse commands/records, emit `{name, message}` in script order. Name comes from the speaker field of the command — never from splitting the message text. Preserve in-message tags/placeholders verbatim (`<i>`, `%s`, `\k`, `{0}` — engine-specific).

Generic fallback (unknown flat formats): `carve` → convert runs to VNTP by hand, keeping the carve dump as the offset map for `patch build-spec`.

### 4. Round-trip test (contract)

Before translating anything:

```bash
$PFX -m copas_reverse.patch build-spec --carve metadata/carve_X.json \
    --input id_input/X.json --out metadata/patch_X.json        # no --output = identity
$PFX -m copas_reverse.patch apply --spec metadata/patch_X.json \
    --src original/X.bin --out /tmp/roundtrip.bin
cmp original/X.bin /tmp/roundtrip.bin && echo ROUNDTRIP-OK
```

`cmp` must pass (for the carve-fallback path, `build-spec` with identical text re-encodes to the same bytes). If not:

- extraction lost characters (encoding mismatch, trimmed spaces, normalized punctuation), or
- the engine stores text with headers/lengths interleaved — you need the structure-aware path.

Fix before proceeding. A failed round-trip guarantees a broken patch later.

### 5. Count and report

`copas_reverse.vntp validate id_input` (expect no kana residue warnings — it is source Japanese, so kana warnings here are expected only for `id_output`).

Report to the user:

| Item | Value |
|---|---|
| Engine / archive / script format | … |
| Text encoding | cp932 / utf-8 / … |
| Scripts found / exported | N / M |
| Dialogue lines exported | K (choices: C, narrator: R) |
| Round-trip test | OK / FAILED (why) |
| Skipped files | list + reason |

Then recommend the sample injection test (SKILL.md Phase 3) before full translation.
