"""
Single-run harness.

``run_one`` is the pure, testable callable that turns a (binary, backend,
strategy) triple into a persisted run directory and a :class:`RunRecord`. It
binds the per-run budgets from :class:`RunSettings` (sourced from ``.env``) into
an :class:`~agent.graph.AgentConfig`, streams the agent graph while writing
``trace.jsonl``, then writes ``record.json`` and ``payload.bin`` atomically (see
``harness.persistence``).

``replay_run`` re-executes the validator on a stored payload without mutating the
original record; ``verify_binary`` reproduces a binary's documented exploit to
confirm corpus-truth. Both share the single execution path (the validator
sandbox, ADR 0002).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from agent import prompts
from agent.graph import AgentConfig, build_run_record, run_agent
from agent.tools import ToolLayer
from backends.base import Backend
from harness import corpus, persistence
from harness.record import RunRecord
from validator.runner import DEFAULT_TIMEOUT_SECONDS, execute

# --------------------------------------------------------------------------- #
# Settings                                                                     #
# --------------------------------------------------------------------------- #


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class RunSettings:
    """Per-run budgets and IO targets, sourced from ``.env`` (see ``.env.example``).

    The same settings object describes a laptop run and a cloud-VM run; only the
    environment values differ.
    """

    output_dir: Path = Path("./runs")
    token_cap: int = 200_000
    wall_clock_cap_seconds: float = 1800.0
    max_iterations: int = 8
    validator_image: str | None = None
    validator_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls, **overrides: Any) -> RunSettings:
        """Build settings from environment variables, with explicit overrides."""
        base = cls(
            output_dir=Path(os.environ.get("RUN_OUTPUT_DIR", "./runs")),
            token_cap=_env_int("RUN_TOKEN_CAP", 200_000),
            wall_clock_cap_seconds=_env_float("RUN_WALL_CLOCK_CAP_SECONDS", 1800.0),
            max_iterations=_env_int("RUN_MAX_ITERATIONS", 8),
            validator_image=os.environ.get("VALIDATOR_IMAGE"),
            validator_timeout_seconds=_env_int(
                "VALIDATOR_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS
            ),
        )
        return replace(base, **overrides) if overrides else base


# --------------------------------------------------------------------------- #
# Single run                                                                   #
# --------------------------------------------------------------------------- #


def run_one(
    spec: corpus.BinarySpec,
    backend: Backend,
    strategy: str,
    settings: RunSettings,
    *,
    run_id: UUID | None = None,
    tools: ToolLayer | None = None,
    validator_client: Any = None,
) -> RunRecord:
    """Execute one run and persist it atomically; return the ``RunRecord``.

    ``validator_client`` (a docker client / fake) is injected straight through to
    the validator so the whole run is exercisable without a Docker daemon.
    """
    run_id = run_id or uuid4()
    run_key = str(run_id)
    output_dir = settings.output_dir

    partial = persistence.begin_run(output_dir, run_key)
    final = persistence.final_dir(output_dir, run_key)

    config = AgentConfig(
        strategy=prompts.get(strategy),
        tools=tools or ToolLayer(),
        success_marker=spec.success_marker,
        documented_chain_fingerprint=spec.documented_chain_fingerprint,
        validator_image=settings.validator_image,
        validator_client=validator_client,
        validator_timeout_seconds=settings.validator_timeout_seconds,
        runs_dir=output_dir,
        run_id=partial.name,  # propose writes payload.bin into the partial dir
        token_budget=settings.token_cap,
        wall_clock_cap_seconds=float(settings.wall_clock_cap_seconds),
        max_iterations=settings.max_iterations,
    )

    trace_file = partial / persistence.TRACE_NAME
    with trace_file.open("w", encoding="utf-8") as fh:

        def sink(event: dict[str, Any]) -> None:
            fh.write(json.dumps(event) + "\n")

        result = run_agent(backend, spec.to_context(), config, trace_sink=sink)

    # Build the record with the *final* paths (the partial dir is renamed below).
    record = build_run_record(
        result,
        config,
        binary_id=spec.binary_id,
        backend=backend,
        trace_path=final / persistence.TRACE_NAME,
    )
    if record.payload_path is not None:
        record = record.model_copy(update={"payload_path": final / persistence.PAYLOAD_NAME})
    record = record.model_copy(update={"run_id": run_id})

    persistence.write_record(partial, record)
    persistence.finalize_run(output_dir, run_key)
    return record


# --------------------------------------------------------------------------- #
# Replay                                                                       #
# --------------------------------------------------------------------------- #


def replay_run(
    run_id: str,
    *,
    output_dir: Path,
    validator_client: Any = None,
) -> tuple[RunRecord, Any]:
    """Re-run the validator on a stored payload; never mutate the stored record.

    Returns the (unmodified) original record and the fresh ``ValidatorOutput``.
    The stored ``record.json`` is read-only here by design (Step 5 done-when).
    """
    record = persistence.load_record(persistence.final_dir(output_dir, run_id))
    if record.payload_path is None:
        raise FileNotFoundError(f"run {run_id} has no payload to replay")
    payload_path = Path(record.payload_path)
    if not payload_path.is_file():
        raise FileNotFoundError(f"payload missing on disk: {payload_path}")

    spec = corpus.resolve_binary(record.binary_id)
    output = execute(
        spec.binary_path,
        payload_path,
        success_marker=spec.success_marker,
        documented_chain_fingerprint=spec.documented_chain_fingerprint,
        client=validator_client,
    )
    return record, output


# --------------------------------------------------------------------------- #
# Verify (corpus-truth)                                                        #
# --------------------------------------------------------------------------- #


def verify_binary(
    binary_id: str,
    *,
    validator_client: Any = None,
    payload: bytes | None = None,
    chain_addresses: list[int] | None = None,
) -> Any:
    """Reproduce a binary's documented exploit in the sandbox; return its output.

    When ``payload`` is given it is used directly (tests inject the documented
    bytes); otherwise the documented exploit module at
    ``<exploits_dir>/<binary_id>.py`` is loaded and its ``build_payload()`` /
    ``load_chain()`` supply the bytes and the chain addresses.
    """
    spec = corpus.resolve_binary(binary_id)
    if payload is None:
        payload, chain_addresses = _load_documented_exploit(binary_id)

    with tempfile.TemporaryDirectory(prefix="sara-verify-") as tmp:
        payload_path = Path(tmp) / "payload.bin"
        payload_path.write_bytes(payload)
        return execute(
            spec.binary_path,
            payload_path,
            success_marker=spec.success_marker,
            candidate_chain=chain_addresses,
            documented_chain_fingerprint=spec.documented_chain_fingerprint,
            client=validator_client,
        )


def _load_documented_exploit(binary_id: str) -> tuple[bytes, list[int] | None]:
    """Load ``<exploits_dir>/<binary_id>.py`` and build the documented payload."""
    import importlib.util

    path = corpus.exploits_dir() / f"{binary_id}.py"
    if not path.is_file():
        raise corpus.CorpusError(f"no documented exploit script for {binary_id!r} at {path}")
    spec_ = importlib.util.spec_from_file_location(f"sara_exploit_{binary_id}", path)
    if spec_ is None or spec_.loader is None:  # pragma: no cover - defensive
        raise corpus.CorpusError(f"cannot import exploit module at {path}")
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)

    payload: bytes = module.build_payload()
    addresses: list[int] | None = None
    if hasattr(module, "load_chain"):
        chain = module.load_chain()
        raw = chain.get("documented_gadget_addresses")
        if raw:
            addresses = [int(str(a), 16) for a in raw]
    return payload, addresses


__all__ = [
    "RunSettings",
    "replay_run",
    "run_one",
    "verify_binary",
]
