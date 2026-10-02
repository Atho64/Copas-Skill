# Eushully

**Evidence**: exe strings `Eushully`, `Data/` with `*.arc` archives, `sys*.dat` system files.

**Layout**: ARC-family archives (entry tables with obfuscated names), scenario in proprietary script records, CP932.

**Extract**: GARbro supports Eushully ARC variants; scenario extraction needs Eushully-specific tooling — several community extractors exist per engine generation.

**Indonesian injection**: structure-aware rebuild via the matching tool. Same-length patching where records are flat. ASCII fine.

**Tools**: GARbro (Eushully), community Eushully extractors.
