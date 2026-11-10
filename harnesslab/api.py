import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from harnesslab.models import HarnessConfig, StrictModel, read_task
from harnesslab.report import compare, export
from harnesslab.store import Store


def create_app(database_url=None, task_root=None, artifact_root=None):
    app = FastAPI(title="HarnessLab", version="0.1.0")
    db = Store(database_url or os.environ.get("HARNESSLAB_DATABASE_URL", ".harnesslab/state.db"))
    root = Path(task_root or "benchmarks/tasks").resolve()
    artifacts = Path(artifact_root or ".harnesslab/artifacts").resolve()

    class CreateExperiment(StrictModel):
        name: str = Field(min_length=1, max_length=100)
        tasks: list[str] = Field(min_length=1, max_length=100)
        configs: list[HarnessConfig] = Field(min_length=1, max_length=5)
        repetitions: int = Field(default=1, ge=1, le=10)
        budget_usd: float = Field(default=5, gt=0, le=1000)

    def get_run(identity):
        row = db.get(identity)
        if not row:
            raise HTTPException(404, "Run not found")
        return row

    @app.get("/api/health")
    def health():
        return {"status": "ok", "schema_version": 1}

    @app.get("/api/tasks")
    def tasks():
        return [{"id": p.stem, "task": read_task(p).model_dump(exclude={"reference_patch", "grading_dir"})} for p in root.glob("*.json")]

    @app.get("/api/experiments")
    def experiments():
        return db.experiments()

    @app.post("/api/experiments", status_code=201)
    def create(body: CreateExperiment):
        paths = []
        for task in body.tasks:
            p = (root / (task + ".json")).resolve()
            if p.parent != root or not p.is_file():
                raise HTTPException(400, "Unknown curated task")
            read_task(p)
            paths.append(p)
        identity = db.experiment(body.name, body.budget_usd)
        for path in paths:
            for config in body.configs:
                for _ in range(body.repetitions):
                    db.enqueue(identity, path, config)
        return {"id": identity}

    @app.get("/api/experiments/{identity}")
    def experiment(identity: str):
        return {"id": identity, "runs": db.runs(identity), "comparison": compare(db, identity), "accounting": db.accounting(identity)}

    @app.get("/api/experiments/{identity}/export")
    def download(identity: str):
        return export(db, identity)

    @app.get("/api/runs/{identity}")
    def run(identity: str):
        return get_run(identity)

    @app.post("/api/runs/{identity}/cancel", status_code=202)
    def cancel(identity: str):
        get_run(identity)
        db.cancel(identity)
        return {"status": "cancellation_requested"}

    @app.get("/api/runs/{identity}/events")
    def events(identity: str, after: int = 0):
        get_run(identity)
        return db.events(identity, max(0, after))

    @app.get("/api/runs/{identity}/stream")
    async def stream(identity: str, request: Request, after: int = 0):
        get_run(identity)

        async def generate():
            cursor = max(0, after)
            try:
                cursor=max(cursor,int(request.headers.get("last-event-id","0")))
            except ValueError:
                pass
            while not await request.is_disconnected():
                for event in db.events(identity, cursor):
                    cursor = event["seq"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if get_run(identity)["status"] not in {"queued", "running"}:
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(.5)
        return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/runs/{identity}/patch")
    def patch(identity: str):
        row = get_run(identity)
        path = (artifacts / identity / str(row["attempt"]) / "patch.diff").resolve()
        if not path.is_relative_to(artifacts) or not path.is_file():
            raise HTTPException(404, "Patch unavailable")
        return {"patch": path.read_text()}

    dist = Path(__file__).resolve().parents[1] / "frontend/dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
