# Majiro

**Evidence**: `*.mjil`, `*.mjo`, `*.mjs` (`MajiroObj`/`MajiroArc` ASCII magic).

**Layout**: bytecode objects with string tables; archives `MajiroArc`. Strings live in a dedicated string pool with a hash index — extraction is string-table parsing, not free carving.

**Extract**: Majiro community toolchains (published format docs) dump the string pool; hashes must be preserved on re-injection.

**Indonesian injection**: rebuild the string table (lengths may change — the format supports it) with a Majiro-aware tool, keeping entry order and hashes. Same-length patching also works if every string keeps its byte length.

**Tools**: community Majiro toolchains on GitHub.
