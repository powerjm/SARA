# radare2 MCP server

Implemented in Step 7, following the worked-example pattern in
`../ropgadget/server.py`: pure, SDK-free functions plus a thin MCP shell whose
SDK import is deferred. The tool functions open an `r2pipe` session (imported
lazily), run the relevant `...j` (JSON) command, and parse the result through
standalone helpers (`parse_functions`, `parse_disasm`, `parse_analysis`) that
are unit-tested on canned JSON without radare2 installed. The pipe stays open
across calls, which matters for large binaries.

## Tools exposed

- `analyze_binary(binary_path)` — runs analysis (`ij`/`aaa`) and returns a
  summary.
- `list_functions(binary_path)` — discovered functions (`aflj`).
- `disassemble_at(binary_path, address, n)` — disassemble `n` instructions at an
  address (`pdj`).
- `search_pattern(binary_path, pattern)` — locate a byte/string pattern.

## Local testing

```bash
# Direct CLI invocation (without MCP):
python -m mcp_servers.radare2.server /path/to/binary

# Launch the MCP stdio server:
python -m mcp_servers.radare2.server --serve
```

## Dependencies

- The `radare2` / `r2` CLI on `$PATH` (`sudo apt install radare2`).
- The `r2pipe` Python binding — part of the `binary-tools` extra (lab host only;
  absent in CI).

Integration tests are marked `requires_radare2` and skip when the `r2pipe`
binding is not importable. The JSON parsers are always tested.
