# YU-RIS

**Evidence**: `*.ypf` archives (`YPKG`-family header), exe strings `YU-RIS`.

**Layout**: `.ypf` archives (several crypto generations, documented in community tools), scenario text with YU-RIS script commands, CP932.

**Extract**: GARbro/arc_conv handle many YPF variants; scenario text extraction via YU-RIS-specific community tools. Where the archive variant is unsupported, stop and report — YU-RIS crypto varies by build.

**Indonesian injection**: same-length patch on extracted text records, or rebuild with the tool that unpacked. ASCII fine.

**Tools**: GARbro (ypf), arc_conv, community YU-RIS toolchains.
