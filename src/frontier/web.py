"""Loopback-only, same-origin local research workstation."""

import json
import platform
import subprocess
import threading
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from frontier.data import import_dataset, list_datasets, load_dataset
from frontier.domain import RunConfig
from frontier.fixtures import generate_fixture
from frontier.store import Registry
from frontier.workflow import list_artifacts

# ponytail: one engine job per process; isolate worker processes for concurrent jobs.
_ENGINE_LOCK = threading.Lock()


@contextmanager
def _engine_job():
    """Coordinate replay jobs and retain the API's busy/failure responses."""
    if not _ENGINE_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Another engine job is running. Wait for it to finish.")
    try:
        yield
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        _ENGINE_LOCK.release()


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_directory: str


class CampaignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    allow_incomplete_actions: bool = False


class ModelCampaignRequest(CampaignRequest):
    max_proposals: int = Field(default=2, ge=1, le=2, strict=True)


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    refresh: bool = True
    initial_cash_usd: float = Field(default=0, ge=0)
    initial_cash_cad: float = Field(default=700, ge=0)
    convert_cad: float = Field(default=0, ge=0)


class BroadResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_symbols: int | None = Field(default=None, ge=2, strict=True)
    rediscover: bool = False


class HistoricalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rediscover: bool = False
    study_mode: Literal["short_horizon", "legacy"] = "short_horizon"
    source_run_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class FreezeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str


class ObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frozen_id: str
    dataset_id: str


def create_app(workspace: Path) -> FastAPI:
    workspace = Path(workspace).resolve()
    data_root = workspace / "data" / "datasets"
    artifact_root = workspace / "artifacts"
    registry = Registry(workspace / "data" / "frontier.sqlite")
    app = FastAPI(title="Frontier Research", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.state.workspace = workspace
    app.state.registry = registry

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin is not None and origin != expected:
                return JSONResponse({"detail": "Cross-origin mutation requests are rejected"}, 403)
            if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
                return JSONResponse(
                    {"detail": "Only same-origin mutation requests are allowed"}, 403
                )
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "Mutation requests require application/json"}, 415)
        return await call_next(request)

    def manifest_dict(manifest):
        return manifest.model_dump(mode="json")

    def get_record(run_id):
        try:
            return registry.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(404, "Study not found") from exc

    def artifact_file(record, filename):
        if not record.get("artifact_path"):
            raise HTTPException(404, "This study has no completed artifacts")
        directory = Path(record["artifact_path"])
        if not directory.is_absolute():
            directory = workspace / directory
        directory = directory.resolve()
        root = artifact_root.resolve()
        path = (directory / filename).resolve()
        if not directory.is_relative_to(root) or not path.is_relative_to(directory):
            raise HTTPException(403, "Registry artifact path is outside the artifact root")
        if not path.is_file():
            raise HTTPException(404, "Study artifact is missing; inspect the saved job error")
        return path

    def envelope(record):
        result = None
        if record["status"] == "COMPLETED":
            result = json.loads(artifact_file(record, "result.json").read_text(encoding="utf-8"))
        return {"record": record, "result": result}

    def demo():
        with _ENGINE_LOCK:
            source = generate_fixture(workspace / "data" / "imports" / "demo")
            return manifest_dict(import_dataset(source, data_root))

    @app.get("/api/status")
    def status():
        from frontier.replay import code_identity

        datasets = list_datasets(data_root)
        runs = registry.list_runs()
        return {
            "service": "frontier-research",
            "workspace": str(workspace),
            "current_code_identity": code_identity(),
            "engine": {"name": "Nautilus Trader", "version": version("nautilus-trader")},
            "runtime": {"python": platform.python_version(), "platform": platform.platform()},
            "dataset_count": len(datasets),
            "run_count": len(runs),
            "job_running": _ENGINE_LOCK.locked(),
            "capabilities": {
                "daily_raw_replay": "Synthetic quotes from raw bars; research only",
                "separate_currency_funding": True,
                "corporate_actions": "Cash dividends with payment dates; stock splits unsupported",
                "cash_dividends": True,
                "stock_splits": False,
                "hourly_execution": (
                    "Regular-session raw-bar replay; inferred quotes and availability"
                ),
                "broker_connection": False,
                "paper_operator": "Opt-in Alpaca paper loop; see /api/operator/status",
                "automatic_fx_trading": False,
                "research_agent": (
                    "Codex proposals with measured feedback; at most 2 calls per campaign"
                ),
            },
            "data_timestamps": [
                {
                    "dataset_id": d.dataset_id,
                    "last_observation": d.end,
                    "retrieved_at": d.retrieved_at,
                    "ingested_at": d.ingested_at,
                }
                for d in datasets
            ],
        }

    @app.get("/api/operator/status")
    def paper_operator_status():
        from frontier.operator import operator_status

        return operator_status(workspace)

    @app.get("/api/research-lab/status")
    def broad_research_status():
        from frontier.research_lab import research_status

        return research_status(workspace)

    @app.get("/api/research-lab/runs/{run_id}")
    def broad_research_result(run_id: str):
        from frontier.research_lab import research_result

        try:
            result = research_result(workspace, run_id)
            return {key: value for key, value in result.items() if key != "cohorts"}
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/research-lab/runs/{run_id}/download")
    def download_broad_research(run_id: str):
        from frontier.research_lab import research_result

        try:
            research_result(workspace, run_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(
            artifact_root / "research-lab/runs" / run_id / "result.json",
            filename=f"frontier-research-{run_id}.json",
        )

    @app.get("/api/research-lab/runs/{run_id}/forward")
    def download_forward_research(run_id: str):
        from frontier.research_lab import research_result

        try:
            result = research_result(workspace, run_id)
            relative = result.get("forward_observation", {}).get("evaluation_path")
            if not relative:
                raise FileNotFoundError("No forward observations saved for this study")
            path = (workspace / relative).resolve()
            allowed = (artifact_root / "forward-studies/evaluations").resolve()
            if not path.is_relative_to(allowed) or not path.is_file():
                raise FileNotFoundError("Forward observation artifact is unavailable")
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, filename=f"frontier-forward-{run_id}.json")

    @app.post("/api/research-lab/start")
    def start_broad_research(body: BroadResearchRequest):
        from frontier.research_lab import start_research_job

        return start_research_job(workspace, **body.model_dump())

    @app.get("/api/historical-lab/status")
    def historical_status():
        from frontier.historical_lab import historical_status

        return historical_status(workspace)

    @app.post("/api/historical-lab/start")
    def historical_start(body: HistoricalRequest):
        from frontier.historical_lab import start_historical_job

        try:
            return start_historical_job(workspace, **body.model_dump())
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/historical-lab/runs/{run_id}")
    def historical_result(run_id: str):
        from frontier.historical_lab import historical_result

        try:
            return historical_result(workspace, run_id, compact=True)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/historical-lab/runs/{run_id}/download")
    def historical_download(run_id: str):
        from frontier.historical_lab import historical_result_path

        try:
            path = historical_result_path(workspace, run_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, filename=f"frontier-historical-{run_id}.json")

    @app.get("/api/scans")
    def scans():
        from frontier.scan_data import list_scans

        return list_scans(workspace)

    @app.get("/api/scans/{scan_id}")
    def scan_detail(scan_id: str):
        from frontier.scan_data import list_scans

        for saved in list_scans(workspace):
            if saved["scan_id"] == scan_id:
                return saved
        raise HTTPException(404, "Scan not found")

    @app.post("/api/scans")
    def scan(body: ScanRequest):
        from frontier.scan_data import run_scan

        with _engine_job():
            return run_scan(workspace, **body.model_dump())

    @app.get("/api/datasets")
    def datasets():
        return [manifest_dict(d) for d in list_datasets(data_root)]

    @app.get("/api/datasets/{dataset_id}")
    def dataset_detail(dataset_id: str):
        try:
            dataset = load_dataset(data_root, dataset_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        return {
            "manifest": manifest_dict(dataset.manifest),
            "preview": {
                key: json.loads(
                    getattr(dataset, key).head(15).to_json(orient="records", date_format="iso")
                )
                for key in ("bars", "actions", "fx")
            },
        }

    @app.post("/api/demo")
    def import_demo():
        return demo()

    @app.post("/api/import")
    def import_source(body: ImportRequest):
        source = Path(body.source_directory)
        if not source.is_absolute():
            source = workspace / source
        source = source.resolve()
        roots = [(workspace / "data" / kind).resolve() for kind in ("imports", "raw")]
        roots = [root for root in roots if root.is_relative_to(workspace)]
        if not any(source.is_relative_to(root) for root in roots):
            raise HTTPException(403, "Copy the source folder into data/imports or data/raw first")
        # A directory symlink or an individual source-file symlink cannot escape this boundary.
        for name in ("dataset.json", "bars.csv", "actions.csv", "fx.csv"):
            candidate = source / name
            if candidate.exists() and not any(candidate.resolve().is_relative_to(r) for r in roots):
                raise HTTPException(403, "Source files must stay inside data/imports or data/raw")
        try:
            with _ENGINE_LOCK:
                return manifest_dict(import_dataset(source, data_root))
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/runs")
    def runs():
        return registry.list_runs()

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str):
        return envelope(get_record(run_id))

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str):
        return FileResponse(
            artifact_file(get_record(run_id), "report.html"), media_type="text/html"
        )

    @app.post("/api/runs")
    def run(body: RunConfig):
        from frontier.replay import run_research

        with _engine_job():
            return envelope(run_research(body, data_root, registry, artifact_root))

    @app.post("/api/campaigns")
    def campaign(body: CampaignRequest):
        from frontier.campaign import run_campaign

        with _engine_job():
            return run_campaign(
                body.dataset_id,
                data_root,
                registry,
                artifact_root,
                allow_incomplete_actions=body.allow_incomplete_actions,
            )

    @app.get("/api/model-campaigns")
    def model_campaigns():
        return list_artifacts(artifact_root, "model-campaigns")

    @app.get("/api/campaigns")
    def campaigns():
        return list_artifacts(artifact_root, "campaigns")

    @app.post("/api/model-campaigns")
    def model_campaign(body: ModelCampaignRequest):
        from frontier.research import run_model_campaign

        with _engine_job():
            return run_model_campaign(
                body.dataset_id,
                data_root,
                registry,
                artifact_root,
                max_proposals=body.max_proposals,
                allow_incomplete_actions=body.allow_incomplete_actions,
            )

    @app.get("/api/frozen")
    def frozen():
        return list_artifacts(artifact_root, "frozen")

    @app.post("/api/frozen")
    def freeze(body: FreezeRequest):
        from frontier.observation import freeze_run

        record = get_record(body.run_id)
        try:
            return freeze_run(record, artifact_root)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/observations")
    def observations():
        return list_artifacts(artifact_root, "observations")

    @app.post("/api/observations")
    def observation(body: ObservationRequest):
        from frontier.observation import observe

        try:
            return observe(body.frozen_id, body.dataset_id, data_root, artifact_root)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sources/status")
    def sources_status():
        from frontier.sources import longbridge_status

        try:
            longbridge = longbridge_status()
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            longbridge = {
                "provider": "longbridge_standalone_cli",
                "status": "unavailable",
                "authenticated": False,
                "hint": str(exc),
                "scope": "Standalone CLI authentication; separate from the app connector",
            }
        return {
            "longbridge": longbridge,
            "acquisition": {
                "us_hourly": (
                    "Saved hourly snapshot available"
                    if any(d.interval == "1h" for d in list_datasets(data_root))
                    else "No hourly snapshot imported"
                ),
                "canada_hourly": "Not yet verified",
                "codex_connectors": (
                    "Session access is separate from standalone CLI authentication"
                ),
            },
        }

    @app.api_route("/api", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    @app.api_route("/api/{unknown:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def api_not_found(unknown: str = ""):
        raise HTTPException(404, "Unknown API endpoint")

    static_root = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    @app.get("/{path:path}")
    def static(path: str):
        candidate = (static_root / path).resolve()
        if not candidate.is_relative_to(static_root.resolve()):
            raise HTTPException(404, "File not found")
        if path and candidate.is_file():
            return FileResponse(candidate)
        index = static_root / "index.html"
        if not index.is_file():
            raise HTTPException(503, "Frontend missing. Run npm --prefix frontend ci and build.")
        return FileResponse(index)

    return app


def serve(workspace: Path, port: int = 8765):
    workspace = Path(workspace).resolve()
    if not list_datasets(workspace / "data" / "datasets"):
        source = generate_fixture(workspace / "data" / "imports" / "demo")
        import_dataset(source, workspace / "data" / "datasets")
    uvicorn.run(create_app(workspace), host="127.0.0.1", port=port)
