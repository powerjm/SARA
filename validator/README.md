# validator/

The validator is the only component that executes candidate ROP payloads. It
runs them inside a hardened Docker container (`Dockerfile.sandbox`) with:

- No network
- Read-only rootfs
- No host filesystem (other than a read-only bind for the binary + payload)
- Non-root user (uid 1500)
- Memory and PIDs limits
- All capabilities dropped, `no-new-privileges`
- Kernel + wall-clock timeouts

## Files

- `runner.py` — invokes the sandbox; returns a `ValidatorOutput`.
- `classifier.py` — converts (agent state, validator output) into the
  canonical (Outcome, FailureMode|None) tuple.

## Build the sandbox image

```bash
make sandbox-build
```

## Why the agent never has direct execution access

The agent has read-only inspection tools (Ghidra, radare2, ROPgadget, GDB
inspect-only). Execution is centralised in the validator so that:

1. Every payload runs under the same hardened policy.
2. The "did this exploit work" decision is made by one component, not by
   the agent's own claims.
3. Failure-mode coding has a uniform set of validator outputs to draw from.
