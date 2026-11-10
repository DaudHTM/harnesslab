import json
import os
from pathlib import Path
from typing import Annotated

import typer

from harnesslab.models import HarnessConfig
from harnesslab.report import compare, export
from harnesslab.runner import validate_task, work
from harnesslab.store import Store


app = typer.Typer(no_args_is_help=True, help="Run, evaluate, and inspect coding-agent harnesses.")
tasks = typer.Typer(no_args_is_help=True)
app.add_typer(tasks, name="tasks")


def store():
    return Store(os.environ.get("HARNESSLAB_DATABASE_URL", ".harnesslab/state.db"))


def configuration(name, path=None):
    return HarnessConfig.model_validate_json(Path(path).read_text()) if path else HarnessConfig(name=name)


@tasks.command("validate")
def validate(paths: list[Path], backend: str = "docker", allow_unsafe_local: bool = False):
    results = [validate_task(p, backend, allow_unsafe_local) for p in paths]
    typer.echo(json.dumps(results, indent=2))
    if not all(r["valid"] for r in results):
        raise typer.Exit(1)


@app.command()
def run(task: Path, config: str = "baseline", config_file: Path | None = None,
        backend: str = "docker", allow_unsafe_local: bool = False,
        fault: str | None = None):
    """Queue and execute a task; fake provider is the default and makes no API calls."""
    if backend not in {"docker", "macos", "local"}:
        raise typer.BadParameter("backend must be docker, macos, or local")
    if backend == "local" and not allow_unsafe_local:
        raise typer.BadParameter("local execution requires --allow-unsafe-local")
    db = store()
    experiment = db.experiment(task.stem)
    identity = db.enqueue(experiment, task, configuration(config, config_file))
    work(db, ".harnesslab/artifacts", backend, allow_unsafe_local, once=True, fault=fault, experiment=experiment)
    typer.echo(json.dumps(db.get(identity), indent=2))
    if db.get(identity)["status"] != "solved":
        raise typer.Exit(1)


@app.command()
def worker(backend: str = "docker", allow_unsafe_local: bool = False, once: bool = False):
    """Process durable queued jobs. Run multiple worker processes for concurrency."""
    if backend not in {"docker", "macos", "local"} or (backend == "local" and not allow_unsafe_local):
        raise typer.BadParameter("choose docker or macos, or explicitly allow unsafe local execution")
    work(store(), ".harnesslab/artifacts", backend, allow_unsafe_local, once)


@app.command("experiment")
def experiment_command(spec: Path):
    """Queue the task × configuration × repetition matrix from a JSON file."""
    data = json.loads(spec.read_text())
    db = store()
    experiment = db.experiment(data["name"], data.get("budget_usd", 5))
    for task in data["tasks"]:
        for config in data["configs"]:
            conf = HarnessConfig.model_validate(config)
            for _ in range(data.get("repetitions", 1)):
                db.enqueue(experiment, spec.parent / task, conf)
    typer.echo(experiment)


@app.command("compare")
def compare_command(experiment_id: str):
    typer.echo(json.dumps(compare(store(), experiment_id), indent=2))


@app.command("export")
def export_command(experiment_id: str, output: Path):
    output.write_text(json.dumps(export(store(), experiment_id), indent=2))
    typer.echo(str(output))


@app.command()
def cancel(run_id: str):
    store().cancel(run_id)
    typer.echo("Cancellation requested")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Serve the local API. Workers run separately."""
    import uvicorn
    uvicorn.run("harnesslab.api:app", host=host, port=port)


if __name__ == "__main__":
    app()
