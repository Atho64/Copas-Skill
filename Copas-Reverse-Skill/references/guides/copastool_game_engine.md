# CopasTool's built-in Game Engine route

Use this route when the native CopasTool app is available and the game matches its supported scenario formats. Verified against `0.1.14-beta.4` / `e15c8d0` (2026-11-11). The Python reverse helpers do not call this backend; operate it through the app or use the existing engine-specific external-tool route.

## Supported paths and limits

| Engine | Native path | Limits |
|---|---|---|
| Kirikiri | Standard XP3 or extracted scenario folders containing PSB `.scn`/`.ks.scn`, including MDF-compressed PSB; decompile/read/rebuild PSB and write XP3 | This backend reads PSB scenarios. Plain KAG `.ks`/TJS scripts need the KAG/external parser route. Output XP3 is unencrypted; games requiring an encrypted index may not mount it. |
| Artemis | PFS and split `.pfs.000` volumes; AST Lua dialogue and flow-page choices; build an override PFS volume | Validate the game's archive/script variant. PFS v2 handling is explicitly best-effort/unverified. Other Artemis scenario formats need the engine page's tools. |

These paths use Rust code in CopasTool and do not require Hxv4 or external unpackers for supported inputs. An engine detection label is not proof that a game's encryption or scripts are supported. Preserve the returned warnings and report skipped/unreadable files.

Source evidence: `src-tauri/src/engine/mod.rs`, `engines/kirikiri.rs`, `engines/artemis.rs`, `psb.rs`, `xp3.rs`; frontend `src/game-engine-modal.ts` and `src/game-engine-types.ts`.

## Extraction and translation hand-off

1. Open Game Engine from the dashboard/workspace in the native app. Select a **game copy**, check detected archives, and select the scenario source deliberately. A retail/translation patch can outrank or change text from the original archive; confirm which source is desired.
2. Choose a cache directory in the work area. The cache retains extracted/decompiled resources, engine marker `engine.txt`, and reconstruction data. Preserve the complete cache, including sidecars that retain archive paths. Refresh/re-extraction can replace cached data, so keep a pristine copy before using it on a continuing translation.
3. Extract and load scenario lines. Select source/translation language slots where applicable. CopasTool makes a `custom` project with ordinary translation fields plus:

```json
{
  "gameEngineCacheDir":"<work cache>",
  "gameEngineGameDir":"<game copy>",
  "lines":[{
    "line_num":1,
    "file":"script01.json",
    "name":"スピカ",
    "message":"先に行くね。",
    "custom_index":{"scene_index":4,"text_index":0}
  }]
}
```

The example indices are schema illustrations; actual values come from extraction. Preserve every `custom_index` exactly. Choice mappings can use special scene indices; do not flatten or renumber them. `line_num` is the translation ID and does not replace scene/text indices.

4. Back up the project as `.copas`/`.copas.zip`, then give that backup to Copas-Translate-Skill. Use `parse --import-project`, glossary/style setup, `batch read --with-context`, and serial `batch write --expect-batch`. A new project parsed from generic VNTP JSON loses engine mapping and is unsuitable for this native round trip.
5. Restore the updated backup in CopasTool and reconnect the preserved cache and game copy. A backup stores cache paths, not the external cache contents; move/copy the cache separately if working on another device. Spreadsheet edits should merge into this original project, since a newly restored sheet lacks engine paths and original resources.

## Build a patch on a copy

Open Game Engine's Build Patch tab with the translated engine project loaded. Choose the proper target language slot, word-wrap setting, and tested maximum line width. Test a small opening/choice sample before translating the whole game.

The UI defaults to installing into the selected game folder, and its backend defaults output to `<game_dir>/patch_output`. Therefore the selected game directory must be a copy under the reverse skill's read-only-original policy. Disable install for a review artifact when available; it still writes to the output directory under the selected copy. Do not describe this route as read-only merely because extraction was read-only.

Kirikiri builds `.xp3`, with a configurable basename. Existing unrelated archives/signatures cause name incrementing; a patch previously installed by this tool can be refreshed in place. Record the returned artifact path and preserve any previous patch needed for rollback. The output warning about an unencrypted XP3 remains relevant even when build succeeds.

Artemis builds the next override volume, such as `root.pfs.001`, containing edited AST scripts. Original volumes stay intact. Preserve AST routing labels, speaker metadata, inline `rt2` line breaks, and original archive entry paths. Copying the resulting volume into the game folder is installation, even though it does not rewrite the original root archive.

Generic helper JSON export does not build either archive. `copas_reverse.patch apply/verify` checks fixed byte slots and must not be used to validate a structure-aware native rebuild.

## Verification for native rebuilds

- Record hashes of the pristine source archives and verify they remain unchanged.
- Confirm file/scene/text/choice counts and stable mappings against the extraction. Check that decoded untranslated content and non-text commands/labels are preserved.
- Check an untranslated round trip at the representation the writer preserves. Use byte equality for byte-preserving operations; for archive/PSB reconstruction, verify decoded structure and explain any recompression or wrapper changes instead of claiming archive byte identity.
- Read/re-extract the generated patch with the compatible reader when possible and compare translated strings, speaker names, language slots, relative paths, and newline markers.
- Have the user launch the game copy and test dialogue, choices, names, wrapping, backlog, and save/load. A successful archive build alone does not prove that the engine mounted the patch.

Keep the reverse skill's existing rule against launching game executables yourself. If runtime analysis is requested, follow its explicit authorization path.

## Existing reverse workflow remains available

For plain KAG, unsupported encryption, different Artemis scripts, or other engines, use the dedicated engine reference and external extraction/injection tools. Keep VNTP `id_input`/`id_output` pairing and fixed-slot byte verification for that path. A failed native import is a reason to investigate the format, not to overwrite the original or silently fall back to carving/repacking.
