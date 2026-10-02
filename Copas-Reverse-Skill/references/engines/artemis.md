# Artemis

**Evidence**: `*.pfs` archives, exe strings `Artemis`.

**Layout**: `.pfs` archives (documented header; entries zlib-compressed; some builds encrypted). Scenario `.sjs`: text records CP932 or UTF-8 depending on build, with a light obfuscation layer (published scheme).

**Extract**: pfs unpack via GARbro/msg-tool; script text via VNTextPatch `ArtemisExtract`.

**Indonesian injection**: VNTextPatch `ArtemisInject` rebuilds scripts; same-length patching possible for text-record-only changes. ASCII fine.

**Tools**: VNTextPatch (ArtemisExtract/Inject), GARbro, msg-tool.
