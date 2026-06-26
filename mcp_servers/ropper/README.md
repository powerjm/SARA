# ropper MCP server

Implemented in Step 7, following the worked-example pattern in
`../ropgadget/server.py`: pure, SDK-free functions plus a thin MCP shell whose
SDK import is deferred. The tool functions shell out to the `ropper` CLI
(constructed argv, no shell), then parse and truncate. `parse_gadgets` turns
`ropper --file X --nocolor` stdout into typed `Gadget` records and is unit-tested
on a canned output string. ropper complements ROPgadget — different filters,
sometimes different gadgets — so exposing both lets the failure-mode analysis see
whether the choice of enumerator affects outcomes.

## Tools exposed

- `enumerate_gadgets(binary_path, filter?, ...)` — gadgets, optionally filtered.
- `search_gadget(binary_path, query)` — search for a specific gadget.
- `get_strings(binary_path)` — strings reported by ropper.

## Local testing

```bash
# Direct CLI invocation (without MCP):
python -m mcp_servers.ropper.server /path/to/binary "pop rdi"

# Launch the MCP stdio server:
python -m mcp_servers.ropper.server --serve
```

## Dependencies

- The `ropper` CLI on `$PATH` — part of the `binary-tools` extra (lab host only;
  absent in CI). Install standalone with `pip install ropper`.

Integration tests are marked `requires_ropper` and skip when the CLI is not on
`$PATH`. The output parser is always tested.
