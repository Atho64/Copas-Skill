# Indonesian text in Japanese engines — encoding & display

Why Indonesian is the easy case: standard Indonesian orthography uses the 26 basic Latin letters (a–z) and ordinary punctuation — all single-byte ASCII. Japanese engines that render Japanese can almost always render ASCII **without font repacking** (Chinese patches need new fonts; Indonesian usually does not). The remaining risks are encoding, punctuation width, and line length.

## Character policy per encoding

### CP932 / Shift-JIS games (the common case)

ASCII `0x20–0x7E` is natively encodable and renderable. Policy:

- **Allowed**: A–Z a–z 0–9 and ASCII punctuation `, . ! ? : ; ' " ( ) - … space`.
- **Forbidden** (not encodable in CP932 — `apply` will refuse): `é è ê ñ ü` and similar accented Latin. Indonesian does not need them; write `e`, `n`, `u` (`kafé → kafe`). This is also KBBI-consistent for common use.
- **Prefer replacing** source full-width punctuation with ASCII: `。→ .`, `、→ ,`, `！→ !`, `？→ ?`, `「」→ " "`, `～→ -` or `s/d`. Full-width forms *are* encodable (the game rendered Japanese), but half-width is correct Indonesian typography and costs half the bytes.
- Useful CP932 characters that survive if you want them: `…` (0x8163), `“ ”` (0x8167/0x8168), `‘ ’` (0x8165/0x8166), `―` (0x815C), full-width space (0x8140). They cost 2 bytes each — on a tight slot, plain ASCII is safer.
- Half-width katakana (`ｱｲｳ`, 0xA1–0xDF) in source often marks SFX/shouts; translate the word, keep any surrounding markup.

### UTF-8 games (RPG Maker MV/MZ, Ren'Py, Unity, Godot, modern engines)

No character-set limits — accented letters are fine. Indonesian still needs none; keep it plain unless a proper noun demands it.

### UTF-16 games

Same freedom as UTF-8.

## Length & layout (the real constraint)

1. **Budget in bytes, not characters.** Japanese is 2 bytes/char; Indonesian ASCII is 1 byte/char. A 40-byte Japanese slot ≈ 40 ASCII characters — usually enough, but measure: `apply` tells you the exact available length per slot.
2. **Watch hard line breaks.** Engines that don't auto-wrap show overflow off-screen or crash. Keep `\n` where the source had it; aim for each segment ≲ the source segment's byte length.
3. **Long words.** Indonesian compounds (`mengembalikannya`, `mempertanggungjawabkan`) can exceed a display row even when total length fits. Prefer natural phrasing that breaks across lines; test the longest lines in the display test.
4. **Padding**: `patch apply` fills leftover bytes with spaces (default). Trailing spaces are harmless in virtually all engines; `--pad zero` for engines that treat 0x20 as content.
5. **Name plate**: speaker names get their own slots/fields; keep translations short there (UI width, not text width, is the limit).
6. **All-caps / small caps UI**: choices are sometimes rendered uppercase — keep choice translations short and accent-free.

For the full wrapping/font-size procedure — how to detect whether the engine word-wraps, where each engine's font-size knob lives, and the translation-side wrapping rules for longer Indonesian text — see `fonts_and_wrapping.md`.

## Newline conventions

The engine decides what "newline" means at byte level: `0x0A`, `\n` escape in text, `<br>`, a control opcode, or nothing (auto-wrap). Determine it once per engine (engine page / hexdump), then pass it to every injection: `--newline-hex 0a`, or leave texts as-is when the engine wraps itself.

## Display test checklist (Phase 3)

On the game **copy**, check: normal dialogue, long lines, name plate, choices, backlog/history, save → load, scene transition. Mojibake ⇒ wrong encoding. Missing text ⇒ wrong offsets/terminator. Crash ⇒ bytes changed outside text slots (should be impossible after `patch verify` — re-run it).
