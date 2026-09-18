"""Local-only reproducible research CLI."""

import json
from importlib.metadata import version
from pathlib import Path

import typer

from frontier.campaign import run_campaign, verify_replay
from frontier.data import import_dataset, list_datasets
from frontier.domain import RunConfig, StrategyConfig
from frontier.fixtures import generate_fixture
from frontier.replay import run_research
from frontier.store import Registry

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def output(value):
    typer.echo(json.dumps(value, indent=2, allow_nan=False))


@app.callback()
def main(ctx: typer.Context, workspace: Path = typer.Option(Path.cwd(), "--workspace")):
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    ctx.obj = workspace


def paths(ctx):
    workspace = ctx.obj
    return (
        workspace / "data/datasets",
        Registry(workspace / "data/frontier.sqlite"),
        workspace / "artifacts",
    )


@app.command()
def doctor():
    output(
        {
            "python_requirement": "3.13",
            "nautilus_trader": version("nautilus-trader"),
            "frontier": version("frontier-trading"),
            "execution": "Research and opt-in Alpaca paper operation; live execution disabled",
            "corporate_actions": (
                "cash dividends require payment dates; stock splits rejected; "
                "unknown coverage requires opt-in"
            ),
        }
    )


@app.command()
def demo(ctx: typer.Context):
    data, registry, artifacts = paths(ctx)
    manifest = import_dataset(generate_fixture(ctx.obj / "data/demo-source"), data)
    output(run_research(RunConfig(dataset_id=manifest.dataset_id), data, registry, artifacts))


@app.command()
def datasets(ctx: typer.Context):
    output([manifest.model_dump(mode="json") for manifest in list_datasets(paths(ctx)[0])])


@app.command("import")
def import_command(ctx: typer.Context, path: Path):
    output(import_dataset(path, paths(ctx)[0]).model_dump(mode="json"))


@app.command()
def run(
    ctx: typer.Context,
    dataset: str,
    strategy: str = "passive",
    lookback: int = 20,
    allow_incomplete_actions: bool = False,
):
    data, registry, artifacts = paths(ctx)
    config = RunConfig(
        dataset_id=dataset,
        strategy=StrategyConfig(family=strategy, name=strategy, lookback=lookback),
        allow_incomplete_actions=allow_incomplete_actions,
    )
    output(run_research(config, data, registry, artifacts))


@app.command()
def campaign(ctx: typer.Context, dataset: str, allow_incomplete_actions: bool = False):
    data, registry, artifacts = paths(ctx)
    output(
        run_campaign(
            dataset, data, registry, artifacts, allow_incomplete_actions=allow_incomplete_actions
        )
    )


@app.command()
def runs(ctx: typer.Context):
    output(paths(ctx)[1].list_runs())


@app.command()
def show(ctx: typer.Context, run_id: str):
    record = paths(ctx)[1].get_run(run_id)
    result = None
    if record["status"] == "COMPLETED":
        result = json.loads(
            (Path(record["artifact_path"]) / "result.json").read_text(encoding="utf-8")
        )
    output({"record": record, "result": result})


@app.command("verify-replay")
def verify(ctx: typer.Context, run_id: str):
    data, registry, _ = paths(ctx)
    result = verify_replay(run_id, data, registry)
    output(result)
    if not result["identical"]:
        raise typer.Exit(1)


@app.command()
def serve(ctx: typer.Context, port: int = 8765):
    from frontier.web import serve as web_serve

    web_serve(ctx.obj, port=port)


@app.command("model-campaign")
def model_campaign(
    ctx: typer.Context,
    dataset: str,
    max_proposals: int = typer.Option(2, min=1, max=2),
    allow_incomplete_actions: bool = False,
):
    """Request at most two typed model proposals and persist actual replay evidence."""
    from frontier.research import run_model_campaign

    data, registry, artifacts = paths(ctx)
    result = run_model_campaign(
        dataset,
        data,
        registry,
        artifacts,
        max_proposals=max_proposals,
        allow_incomplete_actions=allow_incomplete_actions,
    )
    output(result)
    if result.get("status") == "FAILED":
        raise typer.Exit(1)


@app.command()
def freeze(ctx: typer.Context, run_id: str):
    """Freeze a completed run for observation without promoting or placing orders."""
    from frontier.observation import freeze_run

    _, registry, artifacts = paths(ctx)
    output(freeze_run(registry.get_run(run_id), artifacts))


@app.command()
def observe(ctx: typer.Context, frozen_id: str, dataset: str):
    """Record a frozen strategy's as-of decision against a new compatible dataset."""
    from frontier.observation import observe as record_observation

    data, _, artifacts = paths(ctx)
    output(record_observation(frozen_id, dataset, data, artifacts))


def _artifact_list(ctx, kind):
    from frontier.workflow import list_artifacts

    output(list_artifacts(ctx.obj / "artifacts", kind))


@app.command()
def campaigns(ctx: typer.Context):
    """List all persisted fixed exploratory tournaments."""
    _artifact_list(ctx, "campaigns")


@app.command("model-campaigns")
def model_campaigns(ctx: typer.Context):
    """List all persisted model campaigns, including failed attempts."""
    _artifact_list(ctx, "model-campaigns")


@app.command()
def frozen(ctx: typer.Context):
    """List saved frozen configurations."""
    _artifact_list(ctx, "frozen")


@app.command()
def observations(ctx: typer.Context):
    """List saved observation records without evaluating them again."""
    _artifact_list(ctx, "observations")


@app.command("source-status")
def source_status():
    """Read sanitized source status; never log in or inspect credential files."""
    import subprocess

    from frontier.sources import BOC_URL, longbridge_status

    try:
        longbridge = longbridge_status()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        longbridge = {
            "provider": "longbridge_standalone_cli",
            "status": "unavailable",
            "authenticated": False,
            "error": str(exc),
        }
    output(
        {
            "boc": {
                "provider": "Bank of Canada FXUSDCAD",
                "url": BOC_URL,
                "authentication": "public; no credentials",
                "connectivity": "not probed",
            },
            "longbridge": longbridge,
        }
    )


@app.command("fetch-boc")
def fetch_boc(
    ctx: typer.Context,
    start: str,
    end: str,
    refresh: bool = False,
    timeout: float = typer.Option(15, min=0.1),
):
    """Capture public dated USD/CAD rates, reusing verified cached bytes by default."""
    from frontier.sources import fetch_boc_fx

    output(
        fetch_boc_fx(start, end, ctx.obj / "data/raw/captures", refresh=refresh, timeout=timeout)
    )


@app.command("fetch-longbridge")
def fetch_longbridge(
    ctx: typer.Context,
    symbol: str,
    start: str,
    end: str,
    refresh: bool = False,
    timeout: float = typer.Option(30, min=0.1),
):
    """Capture regular-session US raw hourly quotes using existing CLI authentication."""
    from frontier.sources import fetch_longbridge_history

    output(
        fetch_longbridge_history(
            symbol, start, end, ctx.obj / "data/raw/captures", refresh=refresh, timeout=timeout
        )
    )


@app.command("import-session-hourly")
def import_session_hourly(ctx: typer.Context, captured_at: str | None = None):
    """Import retained session SPY hourly snapshots with explicit timing/provenance."""
    from frontier.sources import import_longbridge_snapshot

    output(import_longbridge_snapshot(ctx.obj, captured_at=captured_at))


@app.command()
def scan(
    ctx: typer.Context,
    refresh: bool = True,
    cad: float = 700,
    usd: float = 0,
    convert_cad: float = 0,
):
    """Capture the declared universe and save a fixed-rule stock watchlist and study."""
    from frontier.scan_data import run_scan

    result = run_scan(
        ctx.obj,
        refresh=refresh,
        initial_cash_cad=cad,
        initial_cash_usd=usd,
        convert_cad=convert_cad,
    )
    output(
        {
            "scan_id": result["scan_id"],
            "source": result["source"],
            "funding": result["funding"],
            "scan": result["scan"],
            "study_summary": result["study"]["summary"],
            "study_limitations": result["study"]["limitations"],
            "readiness": result["readiness"],
        }
    )


@app.command("scans")
def saved_scans(ctx: typer.Context):
    from frontier.scan_data import list_scans

    output(
        [
            {
                "scan_id": row["scan_id"],
                "created_at": row["created_at"],
                "status": row["scan"]["status"],
            }
            for row in list_scans(ctx.obj)
        ]
    )


@app.command("paper-status")
def paper_status(ctx: typer.Context):
    """Show locally saved operator state without contacting a broker."""
    from frontier.operator import operator_status

    output(operator_status(ctx.obj))


@app.command("paper-init")
def paper_init(
    ctx: typer.Context,
    account_id: str = typer.Option(...),
    cash_usd: float = typer.Option(...),
):
    """Initialize an empty dedicated Alpaca paper account; no money is transferred."""
    from frontier.operator import initialize_paper

    output(initialize_paper(ctx.obj, account_id, cash_usd))


@app.command("paper-cycle")
def paper_cycle(ctx: typer.Context):
    """Reconcile and execute eligible saved paper intents, then prepare the next decision."""
    from frontier.operator import run_paper_cycle

    output(run_paper_cycle(ctx.obj))


@app.command("paper-watch")
def paper_watch(ctx: typer.Context, interval_seconds: int = typer.Option(300, min=30)):
    """Keep running paper cycles until stopped; the host must remain awake."""
    from frontier.operator import watch_paper

    watch_paper(ctx.obj, interval_seconds)


@app.command("paper-flow")
def paper_flow(
    ctx: typer.Context,
    event_id: str = typer.Option(...),
    amount_usd: float = typer.Option(...),
):
    """Record a funding change already made in the broker simulator; never transfer funds."""
    from frontier.operator import record_paper_flow

    output(record_paper_flow(ctx.obj, event_id, amount_usd))


@app.command("paper-pause")
def paper_pause(ctx: typer.Context, resume: bool = False):
    """Pause new entries while cycles continue managing exits; resume cannot clear a risk halt."""
    from frontier.operator import pause_paper

    output(pause_paper(ctx.obj, paused=not resume))


@app.command("research-run")
def broad_research(
    ctx: typer.Context,
    max_symbols: int | None = typer.Option(None, min=2),
    rediscover: bool = False,
):
    """Resume broad histories and evaluate the declared daily/weekly research hypotheses."""
    from frontier.research_lab import run_research_lab

    result = run_research_lab(ctx.obj, max_symbols=max_symbols, rediscover=rediscover)
    output(
        {
            "run_id": result["run_id"],
            "capture": result["capture"],
            "attempts": len(result["attempts"]),
            "summary_rows": len(result["summaries"]),
        }
    )


@app.command("research-status")
def broad_research_status(ctx: typer.Context):
    """Inspect broad-research progress without fetching data or starting work."""
    from frontier.research_lab import research_status

    output(research_status(ctx.obj))


@app.command("historical-run")
def historical_research(
    ctx: typer.Context,
    start: str = "2000-01-01",
    rediscover: bool = False,
    capture_only: bool = False,
):
    """Capture long histories and test continuous cash portfolios and rolling selection."""
    from frontier.historical_lab import run_historical_lab

    result = run_historical_lab(
        ctx.obj, start=start, rediscover=rediscover, capture_only=capture_only
    )
    output({key: result[key] for key in ("run_id", "capture", "captured") if key in result})


@app.command("historical-status")
def historical_research_status(ctx: typer.Context):
    """Inspect saved historical progress without launching work."""
    from frontier.historical_lab import historical_status

    output(historical_status(ctx.obj))


if __name__ == "__main__":
    app()
