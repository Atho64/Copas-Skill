# Wolf RPG Editor (Silvore)

**Evidence**: `Game.exe` + `Data.wolf` (archive, header starts with `DX`), scattered `*.wolf` data files, `Config2.dat`, exe strings. One of the most common doujin engines.

**Layout**: everything in `Data.wolf` (entry names and contents are obfuscated/encrypted; scheme varies by version and per-game key). Scripts are `Data/Scenario/*.wolf`-style scenario files (bytecode with text records, CP932; newer versions UTF-8?), plus `BasicData` etc.

**Extract**: GARbro and WolfDecompress/wolf-tools handle most common versions (decrypt with the embedded/derived key). Scenario text records are interleaved with opcodes — use a structure-aware Wolf extractor, not carving.

**Indonesian injection**: rebuild via the same tool (Wolf tools re-encrypt). Text lengths are record-based — structure-aware rebuild preferred; same-length patching works when records are fixed-size. ASCII renders with default fonts (verify older CP932 builds for half-width rendering).

**Tools**: GARbro, WolfDecompress/WolfTrans community toolchains.
