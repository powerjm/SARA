"""
Command-line entry point for the run harness.

Usage:

  sara run    --binary X --backend Y [--strategy Z]
  sara batch  --config experiments.yaml [--dry-run]
  sara verify --binary X            # reproduce documented exploit (corpus-truth)
  sara replay --run-id <uuid>       # re-execute validator on stored payload

Each command is a thin shell over the harness functions in ``harness.runner`` /
``harness.matrix``; the agent loop, backends, tools, and validator do the work.
The validator sandbox stays the single execution path (ADR 0002).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from backends import pricing, registry
from harness import corpus, persistence
from harness.matrix import BatchConfig, completed_counts, estimate_cost, plan, run_batch
from harness.runner import RunSettings, replay_run, run_one, verify_binary

console = Console()

# A run for record should not use rates older than this (advisory; warns, does
# not block). Matches scripts/refresh_pricing.py --check.
_PRICING_MAX_AGE_DAYS = 30

# Load .env once so RUN_OUTPUT_DIR / caps / API keys are available to every
# command (a missing .env is fine — real environment values still win).
load_dotenv()


@click.group()
@click.version_option()
def cli() -> None:
    """sara experimental harness."""


@cli.command()
@click.option("--binary", required=True, help="Binary ID from corpus/manifest.yaml")
@click.option("--backend", required=True, help="Backend name, e.g. 'claude-sonnet'")
@click.option(
    "--strategy",
    default="zero_shot",
    type=click.Choice(["zero_shot", "chain_of_thought", "react"]),
    help="Prompting strategy",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to write the run directory (overrides RUN_OUTPUT_DIR)",
)
def run(binary: str, backend: str, strategy: str, output_dir: Path | None) -> None:
    """Execute a single experimental run."""
    console.print(
        f"[bold cyan]Run[/] binary=[yellow]{binary}[/] backend=[yellow]{backend}[/]"
        f" strategy=[yellow]{strategy}[/]"
    )
    settings = (
        RunSettings.from_env(output_dir=output_dir)
        if output_dir is not None
        else RunSettings.from_env()
    )
    try:
        spec = corpus.resolve_binary(binary)
        backend_obj = registry.get(backend)
    except (corpus.CorpusError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    record = run_one(spec, backend_obj, strategy, settings)
    run_dir = persistence.final_dir(settings.output_dir, str(record.run_id))
    console.print(
        f"[green]done[/] outcome=[bold]{record.outcome.value}[/]"
        + (f" failure_mode={record.failure_mode.value}" if record.failure_mode else "")
    )
    console.print(f"  run dir: {run_dir}")
    console.print(
        f"  iterations={record.iterations} tokens={record.tokens.total} cost=${record.cost.usd:.4f}"
    )


@cli.command()
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="YAML describing the experiment matrix",
)
@click.option("--dry-run", is_flag=True, help="Print the plan and cost estimate; run nothing")
def batch(config: Path, dry_run: bool) -> None:
    """Execute the full experiment matrix from a config file."""
    console.print(f"[bold cyan]Batch[/] config=[yellow]{config}[/]")
    cfg = BatchConfig.from_yaml(config)
    cells = plan(cfg)
    done = completed_counts(cfg.output_dir)

    table = Table(title="Experiment matrix")
    table.add_column("binary")
    table.add_column("backend")
    table.add_column("strategy")
    table.add_column("done/total", justify="right")
    for cell in cells:
        have = min(done.get(cell.key(), 0), cfg.replicates)
        table.add_row(cell.binary_id, cell.backend, cell.strategy, f"{have}/{cfg.replicates}")
    console.print(table)

    estimate = estimate_cost(cfg)
    total_runs = len(cells) * cfg.replicates
    console.print(
        f"[bold]{len(cells)}[/] cells × {cfg.replicates} replicates = "
        f"[bold]{total_runs}[/] runs; est. cost ~[bold]${estimate['__total__']:.2f}[/] "
        "(rough upper bound)"
    )
    for backend_name in cfg.backends:
        cap = cfg.cap_for(backend_name)
        cap_text = f" (cap ${cap:.2f})" if cap > 0 else ""
        console.print(f"  {backend_name}: ~${estimate.get(backend_name, 0.0):.2f}{cap_text}")

    # Pricing provenance + freshness gate: the estimate (and every recorded
    # cost) is only as good as backends/pricing.yaml. Surface its version/age so
    # a run for record doesn't silently use stale rates.
    age = pricing.age_days(date.today())
    console.print(
        f"[dim]pricing v{pricing.PRICING_VERSION} (oldest rate as of "
        f"{pricing.oldest_as_of()}, {age}d old)[/]"
    )
    if age > _PRICING_MAX_AGE_DAYS:
        console.print(
            f"[yellow]warning:[/] pricing is >{_PRICING_MAX_AGE_DAYS}d old — verify and refresh "
            "via [bold]scripts/refresh_pricing.py[/] before a run for record"
        )

    if dry_run:
        console.print("[dim]dry run — nothing executed.[/]")
        return

    result = run_batch(cfg, on_event=lambda msg: console.print(f"  {msg}"))
    console.print(
        f"[green]batch done[/] executed={len(result.executed)} "
        f"skipped(existing)={result.skipped_existing} "
        f"halted={sorted(result.halted_backends) or 'none'}"
    )


@cli.command()
@click.option("--binary", required=True, help="Binary ID from corpus/manifest.yaml")
def verify(binary: str) -> None:
    """Reproduce the documented exploit chain to confirm corpus-truth."""
    console.print(f"[bold cyan]Verify[/] binary=[yellow]{binary}[/]")
    try:
        output = verify_binary(binary)
    except (corpus.CorpusError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc

    if output.succeeded and output.stdout_marker_found:
        console.print(f"[green]PASS[/] success marker fired (rc={output.return_code})")
        return
    console.print(f"[red]FAIL[/] marker_found={output.stdout_marker_found} rc={output.return_code}")
    if output.stderr_excerpt:
        console.print(f"[dim]{output.stderr_excerpt}[/]")
    raise SystemExit(1)


@cli.command()
@click.option("--run-id", required=True, help="UUID of a previously recorded run")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Run output directory (overrides RUN_OUTPUT_DIR)",
)
def replay(run_id: str, output_dir: Path | None) -> None:
    """Re-execute the validator on a stored payload (does not mutate the record)."""
    console.print(f"[bold cyan]Replay[/] run_id=[yellow]{run_id}[/]")
    out_dir = output_dir or RunSettings.from_env().output_dir
    try:
        _record, output = replay_run(run_id, output_dir=out_dir)
    except (corpus.CorpusError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]replayed[/] succeeded={output.succeeded} "
        f"marker_found={output.stdout_marker_found} rc={output.return_code} "
        f"matched_documented_chain={output.matched_documented_chain}"
    )


if __name__ == "__main__":  # pragma: no cover
    cli()
