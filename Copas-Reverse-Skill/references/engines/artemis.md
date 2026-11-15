# Artemis

**Evidence**: `*.pfs` archives, exe strings `Artemis`.

**CopasTool native route**: current CopasTool handles PFS/split volumes containing AST Lua scenarios, including dialogue and flow-page choices, and builds an override PFS volume without an external unpacker. Keep its cache, relative archive paths, and `custom_index` mappings. PFS v2 handling is best-effort/unverified. See [../guides/copastool_game_engine.md](../guides/copastool_game_engine.md). The `.sjs`/external-tool route below is a different Artemis scenario variant.

**Layout**: `.pfs` archives (documented header; entries zlib-compressed; some builds encrypted). Scenario `.sjs`: text records CP932 or UTF-8 depending on build, with a light obfuscation layer (published scheme).

**Extract**: pfs unpack via GARbro/msg-tool; script text via VNTextPatch `ArtemisExtract`.

**Indonesian injection**: VNTextPatch `ArtemisInject` rebuilds scripts; same-length patching possible for text-record-only changes. ASCII fine.

**Tools**: VNTextPatch (ArtemisExtract/Inject), GARbro, msg-tool.
