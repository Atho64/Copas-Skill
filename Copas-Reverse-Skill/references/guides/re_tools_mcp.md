# RE tooling via MCP (IDA Pro, Ghidra, x64dbg) — optional escalation

The default pipeline is file-based and needs no disassembler. This guide is for the one case where data analysis genuinely dies: **custom encryption or key derivation that `reverse_engineering_method.md` cannot crack.** If the user has an MCP server configured for a RE tool, the agent may escalate to it — with explicit authorization, on a game copy only.

## What each tool is for in VN reverse engineering

| Tool | Mode | Typical use here |
|---|---|---|
| **x64dbg / x32dbg** | dynamic | Break on file reads (`CreateFileW`/`ReadFile`), find the routine that touches the script, dump the *decrypted* buffer from memory, trace where a key comes from (often a constant, a filename hash, or a simple transform) |
| **IDA Pro / Ghidra** | static | Decompile the file-table builder and the decoder loop; read constants (XOR keys, magic values); understand call flow around the text renderer for opcode semantics |
| **Binary Ninja** | static | Same role as IDA/Ghidra via its API/MCP bridges |
| **Scylla / dumper plugins** | dynamic | Reconstruct unpacked executables for self-modifying engines (rare; last resort) |

The goal is **never** to do the translation flow inside the RE tool. The goal is to learn the algorithm, then reimplement it as stdlib Python (parser + writer), prove it with the round-trip test, and register the finding — same acceptance test as always.

## How the agent connects

RE tools are reached through **MCP servers configured in the agent client** (not installed by this skill). The ecosystem moves fast — check the current MCP registry/community for:

- Ghidra: the well-known GhidraMCP bridge (decompile function, list functions/strings, rename, read memory)
- IDA Pro: community IDA MCP servers built on IDAPython (decompile, xrefs, read segments)
- x64dbg: debugger MCP bridges (breakpoints, registers, memory read/write, step)

Workflow once connected: run `detect` → identify the binary that opens the script → in the RE tool, find `CreateFileW`/`fopen` xrefs → locate the parse/decrypt routine → decompile → reconstruct the algorithm in Python → round-trip test → register (catalog row / engine page).

## Authorization & safety boundary (non-negotiable)

1. Baseline rule stands: **the agent does not launch the game.** Dynamic analysis is an *explicit, per-project exception*: the user authorizes it, it happens **on a copy**, ideally in a throwaway VM/sandbox, and the user is told exactly what will run.
2. Attaching a debugger or driving it through MCP counts as running the game — same authorization.
3. No anti-DRM work: this skill targets *format interoperability for personal translation patches*. Refuse tasks that are about defeating licensing/DRM for piracy, and refuse to distribute circumvention.
4. Stop conditions from `reverse_engineering_method.md` still apply — RE tooling is an escalation of the *method*, not a removal of the *guardrails*.

## If no RE tooling is configured

The stop conditions hold: report the format facts, hypotheses tested, and what's missing — and suggest to the user that connecting a Ghidra/IDA/x64dbg MCP server is the path forward if they want to push further. Give them the exact target: which file, which routine (if located), and the specific question the tool should answer (e.g., "what transform maps this 16-byte header to the key stream").
