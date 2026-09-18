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

app = typer.Typer(no_args_is_help=True)


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
            "execution": "local research only",
            "corporate_actions": (
                "known actions rejected; unknown coverage requires explicit opt-in"
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


if __name__ == "__main__":
    app()
