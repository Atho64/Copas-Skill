# Font size & word wrapping for Indonesian

Japanese patches rarely need this; Indonesian patches usually do. Japanese text is dense and the original lines already fit the message window. Indonesian translations run **longer in characters**, Japanese fonts often render Latin glyphs small or awkwardly, and most classic engines do **not** auto-wrap at word boundaries. Treat this as a first-class Phase 3 concern, not an afterthought.

## Step 1 — Determine how the engine handles line breaks

Check in Phase 2/3, per engine (the engine page may say; otherwise infer from screenshots + script):

| Behavior | What you see | What it means for you |
|---|---|---|
| **Manual breaks only** | source lines contain break markers mid-sentence at odd places; text does not wrap at window edge | You must wrap the Indonesian translation yourself, at word boundaries |
| **Auto-wrap, per character** | no breaks in source, but Latin words split mid-word when testing | Insert your own `\n` at word boundaries; per-char wrap will butcher long Indonesian words |
| **Auto-wrap, per word** | long lines reflow correctly in the display test | Do nothing — keep segments within reason |
| **Fixed window, no wrap, no scroll** | overflow just gets cut off | Per-line length budget is hard; consider engine font/window config below |

Where breaks come from: `0x0A` bytes, script tags (KAG `[r]`), opcodes, or nothing. That's the `--newline-hex` / engine-page decision made in the write-back stage.

## Step 2 — Font size (engine-side knobs)

Indonesian in a Japanese font is often half-width and hard to read at the original size. Check the engine's config surface **before** resorting to font replacement:

| Engine | Where the size knob lives |
|---|---|
| RealLive | `gameexe.ini` font-size/interval keys (e.g. `#FONTSIZE`) |
| Kirikiri / KAG | message-window config (`.tjs`/config CSV) or the in-game config menu |
| Wolf RPG Editor | in-game config / config data files |
| Ren'Py | `gui.rpy` (`gui.text_size`) — easiest of all |
| RPG Maker MV/MZ | database message settings / window skin / plugins |
| Tyrano | config/CSS (browser rendering) |
| Unity / Godot | UI theme or TextAsset-bound font settings |
| Classic engines (CatSystem2, Artemis, BGI, WillPlus…) | per build — check config files or the engine page; often a constant in the script/config |

Changing size changes how many characters fit per line and per window — re-run the wrapping pass after any size change. Also check the in-game config menu: many games expose text speed/size to the player.

## Step 3 — Word wrapping on the translation side (default strategy)

When the engine won't wrap for you, wrap in the VNTP messages:

1. **Measure the window**: from a screenshot of the display test, estimate characters-per-line for half-width Latin at current size (typically 30–45 chars for a standard VN window; verify, don't guess).
2. **Wrap at word boundaries**: break lines between words, never inside an Indonesian word — splitting `mengembalikannya` mid-word is worse than a slightly ragged line.
3. **Rebalance, don't pad**: rebalance the whole sentence across its available lines rather than making line 1 max-length and line 2 one word.
4. **Respect slot structure**: display lines map to patch slots (`build-spec` matches per segment). If you need more lines than the source had, the engine must auto-wrap or the injector must be structure-aware — same-length patching cannot grow the file.
5. **Keep tags on the right side of a break**: never split a control token (`<i>`, `{0}`, names) across lines.

## Step 4 — Font replacement (escalation, not default)

If size config doesn't exist or Latin glyphs are genuinely broken (e.g. rendered as half-width kana style), replacing the font asset is the remaining fix. That's engine-specific art/format work (font archives are usually accessible via GARbro) and needs the user's sign-off — list it in the delivery report as a separate task rather than silently doing it.

## Verification (adds to the Phase 3 / final QA checklist)

- [ ] Longest translated line renders fully (no horizontal cut-off)
- [ ] No word split mid-word at a line boundary
- [ ] Line count fits the window height (no vertical overflow) on the longest passage
- [ ] Name plate and choice menu fit at the chosen font size
- [ ] After any font-size change: re-run the whole display test, not just one scene
