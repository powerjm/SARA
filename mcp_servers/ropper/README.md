# ropper MCP server

Phase 2 placeholder. See `../ropgadget/server.py` for the implementation pattern.

## Tools to expose

- `enumerate_gadgets(binary, filter?)`
- `search_gadget(binary, pattern)`
- `get_strings(binary)`

## Implementation note

Ropper complements ROPgadget — different filtering capabilities and sometimes different gadgets discovered. Expose both so the agent (and the failure-mode analysis) can see whether choice of enumerator affects outcomes.
