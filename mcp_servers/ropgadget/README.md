# ROPgadget MCP server

The worked example (Step 2) the rest of the tool layer copies. The pattern:

1. **Plain Python module wrapping the underlying tool** (`server.py`'s `enumerate_gadgets`). Importable and testable without the MCP SDK.
2. **Thin MCP server shell** (`server.py`'s `_build_server()` / `serve()`) exposing the function with an explicit JSON input schema. The SDK import is deferred so the core stays SDK-free.
3. **Hard timeout on every operation** (`timeout_seconds`, server policy — not exposed to the agent).
4. **Truncation of large outputs** to a configurable budget (`max_results`), with `truncated=true` so the caller can re-query with a tighter filter.
5. **Output parser kept separate** (`parser.py`) so it can be unit-tested against fixture stdout from multiple ROPgadget versions.

## Tools exposed

- `enumerate_gadgets(binary_path, filter_regex?, max_length?, max_results?, include_duplicates?)`
  - `filter_regex` — a Python regex matched (`re.search`) against each gadget's instruction text, applied after enumeration. (Not ROPgadget's mnemonic-oriented `--only`/`--filter`, whose semantics differ.)
  - `max_length` — maximum instructions per gadget (ROPgadget `--depth`).
  - `max_results` — truncate the result set to this many gadgets.
  - `include_duplicates` — pass ROPgadget `--all` so every address of an otherwise-duplicate gadget is reported (the default deduplicates to one entry per unique instruction sequence). Needed to surface, e.g., the alignment `ret` the documented exploit chains.

`call_tool` returns the `EnumerateResult` as MCP structured content (and a mirrored JSON text block): `{binary_path, total_found, returned, truncated, gadgets[]}`.

## Local testing

```bash
# Direct CLI invocation (without MCP):
python -m mcp_servers.ropgadget.server /path/to/binary "pop rdi"

# Launch the MCP stdio server:
python -m mcp_servers.ropgadget.server --serve
```

## Dependencies

- `ROPgadget` on `$PATH` — part of the `binary-tools` extra (lab host only; absent in CI). Install standalone with `pip install ROPgadget`.
- `mcp` Python SDK for the stdio server (core dependency).

Integration tests are marked `requires_ropgadget` and skip when the CLI is not on `$PATH`.
