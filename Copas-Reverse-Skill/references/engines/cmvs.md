# CMVS

**Evidence**: `*.cpz` archives (header contains `CPZ`/"Cherry" markers), exe strings `CMVS`.

**Layout**: `.cpz` compressed archives (scheme published in community tools), scenario text records CP932.

**Extract**: GARbro / msg-tool unpack `.cpz`; extract scenario text with CMVS-aware extractors (VNTextPatch-family where supported).

**Indonesian injection**: same-length patch of text records or rebuild via the unpacking tool. ASCII fine.

**Tools**: GARbro (cpz), msg-tool.
