# Unknown / other engines

Use when no dedicated engine page matches. First check `catalog.md` for the family (mid-tier engines, variants, Western engines — with tool pointers), then:

1. **Evidence gathering** — `../guides/engine_identification.md` (detect report, hexdumps, carve scan).
2. **Community tool sweep on copies** — GARbro, msg-tool, arc_conv/crage, QuickBMS scripts, VNTextPatch. Whatever opens the archive identifies the engine ("opened by GARbro's X plugin → engine X").
3. **Reverse it yourself** — when no tool opens it and the format looks derivable, follow `../guides/reverse_engineering_method.md`: hypothesis-driven header/table analysis, obfuscation testing, opcode mapping with the game as oracle, and a parser+writer pair proven by the round-trip test. Respect its stop conditions — encryption without a published scheme is a report, not a puzzle.
4. **Generic carve fallback** — for flat, index-less text blobs: `carve file --encoding cp932 --require-cjk`, hand-convert to VNTP, and rely on same-length patching. This path requires a **passing round-trip test** before any translation (see `../guides/extraction_playbook.md`).
5. **Escalate** — if archives are encrypted without a published scheme, or scripts are opcode-heavy without docs: report findings (formats, samples, what was tried) and stop. Do not guess keys, do not brute force, do not patch originals.

When you identify a family not listed anywhere: add a catalog row (what you actually observed), add detect rules if machine-checkable, and promote it to a page once you have a verified extraction/injection path.
