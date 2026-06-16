# ghidra MCP server

Phase 2 placeholder. See `../ropgadget/server.py` for the implementation pattern this server should follow:

1. Plain Python module wrapping the underlying tool (testable without MCP).
2. Thin MCP server shell exposing the functions with explicit JSON schemas.
3. Hard timeout on every operation.
4. Truncation of large outputs to a configurable token budget.

## Tools to expose

- `disassemble_function(binary, name_or_addr)`
- `decompile_function(binary, name_or_addr)`
- `list_imports(binary)`
- `list_strings(binary, min_len)`
- `get_xrefs(binary, addr)`

## Implementation note

Use Ghidra Bridge (Python RPC into a running Ghidra Headless instance) rather than shelling out repeatedly. Bridge cost is one-time at server startup.
