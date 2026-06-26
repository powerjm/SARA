# pwntools MCP server

Implemented in Step 7, following the worked-example pattern in
`../ropgadget/server.py`: pure, SDK-free functions plus a thin MCP shell whose
SDK import is deferred. **Unlike the other tool servers it has no external
dependency** — it reimplements the small, exactly-specified slice of pwntools the
agent needs (little-endian payload assembly, address packing, De Bruijn cyclic
patterns) in plain Python. It does **not** import `pwntools` (a lab-host-only
native dependency), so it is fully unit-tested on CI and **never skipped**.

## Tools exposed

- `build_payload(chain_spec)` — assemble a chain spec into payload bytes.
- `pack_address(addr, arch)` — little-endian pack an address (`i386` / `amd64`).
- `generate_pattern(length)` — De Bruijn cyclic pattern for offset discovery.
- `pattern_offset(value, ...)` — find the offset of a value within the pattern.

## Local testing

```bash
# Direct CLI invocation (without MCP):
python -m mcp_servers.pwntools.server pattern 200
python -m mcp_servers.pwntools.server pack 0x401166 amd64

# Launch the MCP stdio server:
python -m mcp_servers.pwntools.server --serve
```

## Dependencies

None beyond the `mcp` SDK (a core dependency) for the stdio server. The tool
functions are pure Python, so there is no `requires_*` marker and the tests run
everywhere, including CI.
