# MAGES / 5pb (MAGES.engine)

**Evidence**: `*.msb` scenario scripts, `*.mg` archives/indices, exe strings `MAGES` / `5pb`.

**Layout**: `.msb` bytecode holds labels, dialogue records, and choices with a documented-enough community format (Steins;Gate et al.). Resources in engine-specific containers.

**Extract**: community MAGES toolchains (msb disassembly/reassembly) cover several titles; check per game. Encoding CP932 in older builds, UTF-8 in newer.

**Indonesian injection**: reassembly via the same toolchain (lengths are table-driven). Same-length patching possible on text records. ASCII fine.

**Tools**: community MAGES/5pb toolchains, GARbro for resources.
