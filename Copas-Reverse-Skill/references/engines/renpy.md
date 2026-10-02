# Ren'Py

**Evidence**: `game/*.rpa` archives (`RPA-3.0 ` ASCII magic), `*.rpyc` compiled scripts, `*.rpy` sources (dev builds); exe strings `Ren'Py`.

**Layout**: scenario in `.rpy` (text) compiled to `.rpyc` (pickled AST). Archives `.rpa` (RPA-3.0/2.0: ASCII header with index offset + key, entries zlib-deflated). Translation via Ren'Py's own i18n system (`tl/<lang>/`).

**Extract**: RPA index is fully documented (deobfuscate index with the header key; entries zlib). Prefer official approach: Ren'Py SDK's `rpy` tooling can generate `tl/indonesian/` translation files from the game scripts — the cleanest path, and it handles re-injection natively. For raw text, unpack `.rpa` and read `.rpy` dialogue (`voice`, say statements) — text is UTF-8.

**Indonesian injection**: use Ren'Py's translation framework (`tl/indonesian`): no binary patching at all, lengths free, wrapping automatic. Fall back to same-length patching only for games locked to `.rpyc` without SDK — usually unnecessary.

**Tools**: Ren'Py SDK (renpy.py, UnRen for rpyc decompile), rpatool/for RPA, GARbro.
