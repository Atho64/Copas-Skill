# RPG Maker (XP / VX / VX Ace / MV / MZ)

**Evidence**: XP/VX/Ace: `Game.rgssad`/`.rgss2a`/`.rgss3a` (`RGSSAD\0` magic). MV/MZ: `www/` or `data/` + `js/` folders, `data/Map###.json`, `data/System.json`.

**Layout**: RGSS generations pack everything into one RGSSAD archive (documented format: header key 0xDEADCAFE, per-entry rolling keys; file-name obfuscation). MV/MZ ship **plain UTF-8 JSON** — no archive (or a simple one).

**Extract**: MV/MZ: read `data/*.json` directly; dialogue in `Map###.json` events (event command code 401 = message lines, 102 = choices), actor/skill names in `Actors.json` etc. XP/VX/Ace: unpack RGSSAD with GARbro/msg-tool (well-documented cipher), then `Marshal.load` Ruby marshalled `Map###.rxdata`/`.rvdata` — or use a Ruby/marshal-aware extractor.

**Indonesian injection**: MV/MZ is the friendliest target of all: edit JSON (UTF-8 free text), re-zip or repack; no length limits. RGSS generations: rebuild the rxdata structures (Ruby Marshal) rather than byte-patching; ASCII text renders fine in the default fonts.

**Tools**: GARbro, msg-tool (rgssad), RPG Maker editor itself (opening the project often just works), VNTextPatch (rgss).
