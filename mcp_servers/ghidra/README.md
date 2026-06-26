# ghidra MCP server

Implemented in Step 7, following the worked-example pattern in
`../ropgadget/server.py`: a pure, SDK-free layer plus a thin MCP shell whose SDK
import is deferred. Ghidra is driven through **PyGhidra** (Ghidra's first-party
CPython/JPype bridge), pinned to **Ghidra 11.4.3 + JDK 21** — see
[ADR 0004](../../docs/adr/0004-ghidra-bridge.md).

The four program-dependent tools open and auto-analyse a binary **once** through
a `_GhidraSession` and reuse the open program across calls — running headless
analysis per call would be prohibitively slow. `list_strings` is the exception:
it is a dependency-free `strings`-style ASCII extractor over the file bytes (it
does **not** call Ghidra), so it is unit-tested on CI without a skip.

## Tools exposed

- `disassemble_function(binary_path, name_or_addr)` — instruction listing for a
  function resolved by name or address.
- `decompile_function(binary_path, name_or_addr)` — decompiled C text via
  Ghidra's decompiler.
- `list_imports(binary_path)` — imported symbols as `{name, library}`.
- `list_strings(binary_path, min_len?, max_results?)` — printable ASCII runs with
  their file offsets; truncated to `max_results` with `truncated=true`. **Pure;
  needs no Ghidra.**
- `get_xrefs(binary_path, address)` — cross-references to an address as
  `{from_address, to_address, ref_type}`.

## Local testing

```bash
# Pure strings extractor (no Ghidra needed):
python -m mcp_servers.ghidra.server /path/to/binary

# Launch the MCP stdio server (the Ghidra-backed tools need the deps below):
python -m mcp_servers.ghidra.server --serve
```

## Dependencies

Lab-host / cloud-image only (absent in CI). Four of the five tools need all of:

1. **JDK 21** — `sudo apt install openjdk-21-jdk`.
2. **Ghidra 11.4.3** — unzip to `/opt/ghidra` and set `GHIDRA_INSTALL_DIR`
   (the cloud image does this in `infra/packer/provision/install-tools.sh`).
3. **PyGhidra**, installed from the wheel bundled *inside* that distribution so
   the bridge stays matched to the pinned Ghidra (ADR 0004 — do **not** pull it
   from PyPI):
   ```bash
   .venv/bin/pip install \
     "$GHIDRA_INSTALL_DIR"/Ghidra/Features/PyGhidra/pypkg/dist/pyghidra-*.whl
   ```

Integration tests are marked `requires_ghidra` and skip when PyGhidra is not
importable or no Ghidra install is discoverable (`tests/conftest.py`'s
`ghidra_available`). `list_strings` is always tested.
