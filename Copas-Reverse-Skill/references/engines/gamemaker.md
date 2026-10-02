# GameMaker

**Evidence**: `data.win` (IFF-style `FORM` magic) or `game.unx`/`game.ios`, `*.yy` JSON in source builds.

**Layout**: data.win chunks hold code/strings/assets; dialogue may be in code strings, JSON, or `*.yy`/CSV. Undertale-style tooling covers the format well.

**Extract**: UndertaleModTool / DeltaVectorizer-family dumpers read data.win directly; text extraction from string tables and code.

**Indonesian injection**: UndertaleModTool re-imports strings (lengths are handled by the format). UTF-8 capable; fonts must cover Latin (usually do).

**Tools**: UndertaleModTool, QuickBMS scripts.
