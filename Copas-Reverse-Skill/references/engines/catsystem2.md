# CatSystem2

**Evidence**: `*.int` encrypted archives/data, `cs2.ini`, exe strings `CatSystem`.

**Layout**: archives `.int` (encryption keyed off the file name — scheme published in the community), scenario `.cs` files with speaker ids, CP932 text.

**Extract**: decrypt `.int` with the documented name-derived scheme via community tools (GARbro, msg-tool, crage plugins cover the common variants). Scenario `.cs`: text records in script order.

**Indonesian injection**: patch decrypted `.cs` and repack `.int` with the tool that unpacked, or same-length patch when record lengths live outside the text. ASCII renders fine with default fonts.

**Tools**: GARbro, msg-tool, crage/arc_conv plugins.
