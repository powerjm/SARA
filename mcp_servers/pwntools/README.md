# pwntools MCP server

Phase 2 placeholder. See `../ropgadget/server.py` for the implementation pattern.

## Tools to expose

- `build_payload(chain_spec)` — assemble a chain into bytes.
- `pack_address(addr, arch)`
- `generate_pattern(length)` — De Bruijn pattern for offset discovery.

## Implementation note

pwntools is in-process Python; this MCP server is a thin schema wrapper. The actual exploit construction lives in the wrapped module so the agent can test it programmatically.
