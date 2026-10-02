# Kirikiri / KAG (XP3)

**Evidence**: `*.xp3` archives (`XP3` + `0D 0A 20 0A 1A 0B 0D 0A` magic), or the header embedded in `Game.exe` (self-boot). KAG scenario tags in scripts; exe strings `Kirikiri`/`KAG`.

**Layout**: archives contain `.tjs` (engine code), `.ks` (KAG scenario), `.csv` config, plus resources. Text may sit in a plain `.xp3`, or in one packed inside the exe, or encrypted (`*.xp3` with custom header checks).

**Extract**: unmodified XP3 → arc_unpacker/GARbro/msg-tool, or a Python XP3 reader (unencrypted variant: TOC at the offset in the header; entries zlib-compressed; filter mask 0xFF xor). Encrypted XP3 variants (common in commercial games) — use a published unpacker; if none opens it, stop and report. Scenario is usually `.ks`: `Text`/dialogue lines between KAG tags; `[name]`/speaker handling per game (often `#speaker` or inline).

**Indonesian injection**: KAG renders text via font tags; ASCII works with the bundled fonts. Keep KAG tags (`[r]` line break, `[cm]`, `[p]`, font tags) verbatim — they are the newline convention, not `\n`. Patch `.ks` as text (structure-aware rebuild preferred: `.ks` is plain text, so regenerate the file rather than offset-patching).

**Tools**: GARbro, arc_unpacker, msg-tool (`xp3`), KAG-based extractors in VNTextPatch family.
