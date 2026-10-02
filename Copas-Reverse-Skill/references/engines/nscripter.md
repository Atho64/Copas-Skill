# NScripter / ONScripter

**Evidence**: `nscript.dat` (encrypted bytecode script), `arc.nsa`/`*.nsa`, `arc.sar`, `*.s` resource archives; exe strings `NScripter`.

**Layout**: the whole scenario is `nscript.dat`; game data in NSA/SAR archives. `nscript.dat` is encrypted with a trivial rolling XOR documented in ONScripter sources and many public decryptors — do not invent one.

**Extract**: decrypt `nscript.dat` with a published ONScripter-family decryptor (or run ONScripter's own extraction path). Decrypted script is Shift-JIS text: numeric labels, `*` labels, `print 1` and dialogue lines, speaker via `vsp`/named text conventions per game.

**Indonesian injection**: ONScripter renders CP932 half-width ASCII fine; full-width chars also fine. Re-encrypt with the same cipher or ship the decrypted script with an ONScripter build that reads plain scripts (common practice). Keep line structure — the interpreter is line-based; a dialogue line must stay one line.

**Tools**: ONScripter sources, ponscr/NScripter toolchains, GARbro (nsa/sar).
