# Engine identification

Goal: name the engine family (and archive/script formats) from evidence, without modifying anything and without guessing.

## Evidence discipline

Rank evidence by strength and require independence:

1. **Magic bytes** (strongest) — `XP3…`, `RGSSAD\0`, `RPA-3.0 `, `GDPC`, `MajiroArc…` at expected offsets.
2. **File-name fingerprints** — `nscript.dat`, `gameexe.ini`, `seen.txt`, `*.rgss3a`, `ArchData.bin`, `*.pfs`, `*.ypf`, `*.cpz`, `*.mjil`.
3. **Directory layout** — `data/Map01.json` + `www/` (RPG Maker MV/MZ), `tyrano/`, `scene/`, `arc/`.
4. **Executable strings** — engine names embedded in `*.exe` (e.g. `SiglusEngine`, `Kirikiri`, `Ethornell`).
5. **Encoding statistics** — `copas_reverse.carve scan` shows cp932/utf-8/utf-16 hit rates per file.

Rule of thumb: **one strong signal is a hypothesis; two independent signals are a conclusion.** `copas_reverse.detect` produces the report — cite it in `metadata/detection.md`.

## Decision procedure

1. Run `detect`, open `references/engines/<family>.md` for every medium/high candidate only.
2. On the engine page, confirm the page's checklist items actually match this game (engines ship in many variants; publishers re-pack and encrypt).
3. If no candidate, or the page's checklist fails → follow "Unknown formats" below. Do **not** mutate files on the strength of a guess.

## Common gotchas

- **Self-booting archives**: Kirikiri games often carry the XP3 header inside `Game.exe` itself (no separate `.xp3`). `detect` scans exe headers for this reason.
- **Renamed executables** mean nothing; `Game.exe` tells you nothing. Look at data files first.
- **Shared extensions**: `.int` (CatSystem2) vs `.int` config files; `.mjo` (Majiro) vs `.mjo` (Malie); `.dat` is meaningless alone. Decide by magic + context, never by extension only.
- **Multiple engines**: bundled installers, updater exes, and editor tools also contain engine strings. Weigh data-file evidence over exe evidence when they disagree.

## Unknown formats

1. Build the evidence inventory: extension histogram + sizes from `detect`, encoding suggestions from `carve scan`.
2. Hexdump the first 256 bytes of the largest archive-like files; look for ASCII names, length tables, or indexes at the head/tail.
3. Find the dialogue: run `carve file <f> --encoding cp932 --require-cjk` over candidate scripts; files with long kana/kanji runs are scenario scripts.
4. Try read-only opens with community tools (GARbro, msg-tool, VNTextPatch, crage/arc_conv, QuickBMS scripts) **on copies** in a scratch dir. Their support lists also identify engines ("this tool unpacked it → engine X").
5. Record everything in `metadata/detection.md`; tell the user what is unproven. If nothing opens cleanly, stop and report — do not brute-force or "patch and pray".
