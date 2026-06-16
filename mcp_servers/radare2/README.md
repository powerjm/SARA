# radare2 MCP server

Phase 2 placeholder. See `../ropgadget/server.py` for the implementation pattern.

## Tools to expose

- `analyze_binary(binary)` — runs `aaa` and returns a summary.
- `list_functions(binary)`
- `disassemble_at(binary, addr, n)`
- `search_pattern(binary, pattern)`

## Implementation note

Use `r2pipe` rather than subprocessing `r2 -c '...'`. Pipe stays open across calls, which matters for large binaries.
