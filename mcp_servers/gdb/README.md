# gdb MCP server

Phase 2 placeholder. See `../ropgadget/server.py` for the implementation pattern.

## Tools to expose

- `run_with_payload(binary, payload_path)` — used by the validator.
- `inspect_state(binary, breakpoint, payload?)`
- `set_breakpoint(addr)`

## Implementation note

GDB is exposed to the agent in **inspect** mode only. Execution of candidate payloads happens through the validator, never through this tool.
