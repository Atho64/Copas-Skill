# LucaSystem (ProtoDB / LUCA System) — Key / VisualArt's

**Evidence**: `files/` folder with `SCRIPT.PAK`, `PARAM.PAK`, `SYSSE.PAK` (+ FONT/BGM/VOICE packs), modern DX11 engine, UTF-16 startup log, UTF-8 entry names inside PAKs. Games: AIR, CLANNAD, Kanon, Little Busters, Summer Pockets, Harmonia, LOOPERS, LUNARiA, Planetarian (Steam-era builds).

**Tool**: LuckSystem — upstream https://github.com/wetor/LuckSystem, actively updated fork: https://github.com/yoremi-trad-fr/LuckSystem-2.3.2-Yoremi-Update (Go CLI+GUI; per-game plugins in `data/<Game>.py` + charset `data/<Game>.txt`; ships plugins for the games above; no LICENSE file in the fork — use locally).

**Extraction** (proven on LUNARiA):
```bash
go build -o lucksystem.exe .          # from the repo root
lucksystem script decompile -s SCRIPT.PAK -c UTF-8 \
    -O data/LUNARiA.txt -p data/LUNARiA.py -o Export -n
```
Produces one readable command-listing `.txt` per script (IMAGELOAD/DRAW/WAIT/…).

**Dialogue format** (decompiled):
`MESSAGE (id, "@Speaker@JP text", "@Speaker@EN text", "@Speaker@CN text")` — trilingual slots;
speaker prefix `@Name@` (same convention as Luca TXT in Copas-Translate-Skill); ruby markup
`$[base$/reading$]` must be preserved verbatim; `LOG_BEGIN ("JP","EN","CN")` = backlog titles.
Slot choice for the Indonesian patch (overwrite JP slot vs EN slot vs extend) is a user
decision tied to the game's language config.

**Indonesian pipeline**: decompile → convert MESSAGE lines to VNTP `id_input/*.json`
(speaker → `name`, JP slot → `message`; entry order = backfill mapping) → translate via
Copas-Translate-Skill → write translations into the chosen slot in the `.txt`s →
`lucksystem script import -s SCRIPT.PAK ... -i Export -o SCRIPT_ID.PAK` → replace in a game
copy and display-test.

**Container structure (independently verified)**: header `(u32, count, u32, u32)` + version
mark at 0x20 + names_end/table_end u32s + entry table of `(u32 offset, u32 uncompressed_size)`
with **contiguous blobs and a 4:1 expansion transform** (`size = 4 × (next_offset − offset) − pad`)
+ null-terminated ASCII/UTF-8 names. (See LUNARiA_extract/metadata/notes.md for the worked example.)
