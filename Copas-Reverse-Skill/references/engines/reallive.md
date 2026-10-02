# RealLive

**Evidence**: `gameexe.ini` (mandatory config), `seen.txt` (scenario source, sometimes packed), `*.seh`/`.rgd` resources; exe strings `RealLive`.

**Layout**: scenario source `seen.txt` (plain, Shift-JIS, SEEN blocks) is compiled to `SEEN.TXT`/game data by rldev-style tooling. `gameexe.ini` holds UI strings, names, and config keys.

**Extract**: rldev (`rlseen`/`reallive` toolchain) decompiles SEEN data back to readable form; `seen.txt` if present is directly readable Shift-JIS. Dialogue lines are wrapped in message-window commands; speaker names via `#NAME`-style markers or game-specific conventions.

**Indonesian injection**: rebuild via rldev-style compile, or same-length patch on flat variants. ASCII renders fine. `gameexe.ini` is plain Shift-JIS text — patchable directly for UI strings.

**Tools**: rldev (canonical), xVNTextPatch/VNTextPatch has RealLive support, GARbro for resources.
