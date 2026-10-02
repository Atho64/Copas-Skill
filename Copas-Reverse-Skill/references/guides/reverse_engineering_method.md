# Reverse-engineering an unknown format yourself

When the catalog and the tool sweep come up empty, the agent does the reverse engineering — with discipline. This is the method. It applies to two targets: **archive containers** (file tables) and **script formats** (records/opcodes/text). Everything happens on copies, in a scratch dir; originals stay read-only; every finding goes into `metadata/notes.md`.

## Ground rules

1. **Hypothesis → test → record.** Never parse blindly. State the hypothesis ("u32 LE at 0x04 is the entry count"), predict a consequence, check it. A single confirmed prediction beats ten hunches.
2. **The game is the oracle.** Text on screen (user runs the game copy), file counts, known resource formats — anything observable validates your model.
3. **Know when it's encryption.** Obfuscation (XOR, rotated tables, name-derived keys) leaves visible structure and is usually derivable — try. **Encryption without a published scheme looks uniformly random everywhere and yields to nothing** — stop and report. Never guess or brute-force keys; a key derivation must be *proven* (e.g., a filename-derived key verified across several files, not one).
4. **Every parser ships with a writer.** The acceptance test is the round-trip: parse → rebuild untranslated → byte-identical. Without that, no translation happens.

## The loop

### 1. Inventory
Group files by extension/size. Candidate roles: **archive** (one big file), **index+data pairs** (small `.idx` next to a big `.dat`), **scripts** (many same-shaped files), **one-off configs**. Count them — counts reappear as header fields.

### 2. Header analysis
Hexdump the first 256–512 bytes of each file class. Look for: ASCII magic, version ints, and any integer that **matches an observable count** (number of scripts, number of files). Japanese PC titles are usually little-endian; note the exception, not the rule.

### 3. Number-table inference
Scan for u16/u32 LE runs that look like: **offsets** (monotonically increasing, last ≈ file size) or **lengths** (sum + header size ≈ file size). This finds file tables even without names. Test each candidate table by predicting where blob #0 starts — then check what's actually there (`78 9C` zlib, `OggS`, PNG, `BMP`…). One confirmed landing point anchors the whole table.

### 4. Container model
Most VN archives are `[magic][version][count][ (name?/offset/size) × N ][data…]`. Names may be fixed-width, length-prefixed, obfuscated, or absent. Confirm the model predicts **every** blob boundary before writing the extractor.

### 5. Obfuscation & compression
- **Compression**: zlib (`78 01/9C/DA`), LZ-family signatures, or stored blobs that decode to known formats.
- **XOR/rolling XOR**: long zero-padded regions become a visible repeating byte (the key); try single-byte XOR against padding, then index-dependent variants (`byte ^ i`, rolling key). Compare two files that share structure — identical plaintext under different keys leaks the scheme.
- **Name-derived keys**: change nothing; verify the derived key on *multiple* files before trusting it.
- **Give-up test**: entropy uniformly high, no table found after systematic hypotheses → report, don't force it.

### 6. Script text records
Carve the script (`carve file --require-cjk`). Around each text run, look for:
- **Length prefixes**: a u8/u16/u32 immediately before the string whose value equals the string's byte length — verify across many strings before believing one.
- **Terminators**: `00`/`0A` after runs.
- **Opcodes**: short constant bytes before/after records with a regular stride. Diff **two scripts from the same game**: common head/tail = engine code, differing middle = data. Records that repeat with the same shape (e.g., name field + text field) are dialogue records.

### 7. Semantics by oracle
Match record order to what the player sees (user runs the copy): alternating name/text = dialogue; a cluster of short records after a marker = choices. Note every mapping in `metadata/notes.md`.

### 8. Implement, round-trip, register
Write a small stdlib-only Python module: parse → dump structured JSON; rebuild → binary. Assert invariants while parsing (offsets in range, counts match, strings decode). Run the round-trip test (extraction_playbook). Then:
- add a catalog row (what you actually verified),
- promote to a dedicated engine page with the algorithm summarized (magic, layout, obfuscation, pseudocode),
- keep the extractor next to the project's metadata (or propose it for `scripts/`) with a synthetic test like `tests/`.

## Stop conditions (all of them, not one)

- Encryption without a published scheme, after the systematic checks above.
- Opcode semantics you cannot pin down even with the game as oracle.
- The user's authorization scope doesn't cover the work (e.g., deploying test injections).

Stopping is a deliverable: report the format facts you *did* establish, the hypotheses tested, and what's missing — that report is how the next attempt (or the community) gets further. One upgrade path exists before declaring defeat: if the user has an RE tool (IDA/Ghidra/x64dbg) reachable via MCP, the "stop" becomes a **proposed escalation with authorization** — see `re_tools_mcp.md` for the boundary rules and the exact question the tool should answer.
