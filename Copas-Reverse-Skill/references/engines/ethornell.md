# BGI / Ethornell

**Evidence**: `ArchData.bin`, `DataPack.bin`, `bgi.exe`/`ethornell.exe`; `.arc` with BGI-family magic; DSC scenarios.

**Layout**: archives `ArchData.bin`/`DataPack.bin` (entry table + zlib entries, scheme published). Scenario `.dsc` files: opcodes + text records, CP932 with a light per-byte obfuscation (published).

**Extract**: GARbro and VNTextPatch both know BGI (VNTextPatch `BGIExtract`); DSC disassembly via BGI toolchains.

**Indonesian injection**: VNTextPatch `BGIInject` rebuilds scripts; same-length patching works for pure text-record rewrites. ASCII renders fine.

**Tools**: VNTextPatch (BGIExtract/BGIInject), GARbro.
