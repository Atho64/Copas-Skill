# Malie

**Evidence**: `*.mjo` objects (`MalieMBF`-family headers), `*.lib` libraries, exe strings `Malie`.

**Layout**: `.mjo` bytecode with string areas; scenario distributed across module files; encryption keys per game (published for several builds).

**Extract**: Malie-specific community tools dump modules/strings where the build is covered; otherwise stop and report.

**Indonesian injection**: rebuild via the same toolchain; string areas carry lengths — prefer structure-aware rebuild over offset patching. ASCII fine.

**Tools**: Malie community toolchains (check per build).
