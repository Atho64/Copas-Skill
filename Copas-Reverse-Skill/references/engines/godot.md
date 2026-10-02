# Godot

**Evidence**: `*.pck` (`GDPC` magic), `*.exe` + `*_pck.exe` pairs; exe strings `GodotEngine`.

**Layout**: PCK packages all resources; scripts may be text `.gd` or compiled `.gdc`; dialogue often in `.po`/CSV translation files or TextAssets.

**Extract**: PCK format is fully documented (magic, version, file table). Unpack with gdsdecomp (Godot RE tools), which also decompiles `.gdc`.

**Indonesian injection**: repack PCK into the output dir, or deliver loose files when the game loads them. UTF-8 everywhere; prefer the game's own `.po`/CSV translation files when present — Godot's i18n does the rest.

**Tools**: gdsdecomp, gdtoolkit.
