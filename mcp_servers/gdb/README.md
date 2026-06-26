# gdb MCP server

Implemented in Step 7, following the worked-example pattern in
`../ropgadget/server.py`: pure, SDK-free functions plus a thin MCP shell whose
SDK import is deferred.

GDB is exposed to the agent in **inspect mode only**. Execution of candidate
payloads happens through the validator sandbox, never through this tool
([ADR 0002](../../docs/adr/0002-validator-boundary.md): the validator owns all
payload execution). The server therefore **rejects** any command that would run
or resume the inferior — `run`, `start`, `continue`, `attach`, `jump`, `call`,
etc. — and only allows static inspection. `run_gdb_batch` enforces this policy by
inspecting each command's leading token before shelling out to
`gdb --batch -nx -ex ...`.

## Tools exposed

- `inspect_state(binary_path, focus?)` — static inspection (file info, symbols,
  disassembly) of the binary.
- `set_breakpoint(addr)` — records a breakpoint **plan**; it never runs anything.
- `disassemble(binary_path, ...)` — disassembly of a function/region.

## Local testing

```bash
# Direct CLI invocation (without MCP):
python -m mcp_servers.gdb.server /path/to/binary

# Launch the MCP stdio server:
python -m mcp_servers.gdb.server --serve
```

## Dependencies

- The `gdb` CLI on `$PATH` (`sudo apt install gdb`) — lab host only; absent in CI.

Integration tests are marked `requires_gdb` and skip when `gdb` is not on
`$PATH`. The inspect-only policy checks are always tested.
