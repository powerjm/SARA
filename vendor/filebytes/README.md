# Vendored `filebytes` 0.10.2 (Python 3.14 build fix)

`ropper` (in the `binary-tools` extra) depends on `filebytes`, but **no released
`filebytes` builds on Python 3.14**: its `setup.py` metadata extractor uses
`ast.Str` and `node.s`, both removed in Python 3.12. Since sara targets Python
3.14 / Ubuntu 26.04, `pip install ropper` (and therefore
`pip install -e ".[binary-tools]"`) fails while building `filebytes` from sdist.

This directory vendors a **one-line-patched** wheel so installs are reproducible
on the target. See [ADR 0008](../../docs/adr/0008-filebytes-py314-and-binary-tools.md).

## Contents

- `filebytes-0.10.2-py3-none-any.whl` — the patched wheel (sha256
  `93f096e146417adb92e9a7a5578fd4c042cee1d656c26036a7a0cc3f2cf895d3`).
- `ast-str-py312.patch` — the exact change applied (`ast.Str` → `ast.Constant`,
  `.s` → `.value`). It touches only build-time metadata extraction; the runtime
  package is byte-for-byte upstream 0.10.2.

## How to use

Install this wheel **before** the extra so ropper's `filebytes>=0.10.0`
requirement is already satisfied and pip never tries to build the broken sdist:

```bash
.venv/bin/pip install vendor/filebytes/filebytes-0.10.2-py3-none-any.whl
.venv/bin/pip install -e ".[binary-tools]"
```

`infra/packer/provision/install-tools.sh` does this automatically.

## How to rebuild from upstream (provenance)

```bash
# Upstream sdist (PyPI), sha256 764202f74d79e7587f04b6ad46f7c50485d8f32c4aeddd02200f1651a0892741
curl -fsSLO https://files.pythonhosted.org/packages/01/44/4ea92a74ca7d7940a29d6c437f62a91fd05d43bfa04fc8306b5dc541d01d/filebytes-0.10.2.tar.gz
tar xzf filebytes-0.10.2.tar.gz
patch -p1 -d filebytes-0.10.2 < ast-str-py312.patch
pip wheel ./filebytes-0.10.2 --no-deps -w .
```

Revisit if upstream `filebytes` publishes a Python-3.12+ compatible release; at
that point this vendored wheel and the pre-install step can be dropped.
