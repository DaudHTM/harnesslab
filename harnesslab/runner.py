import asyncio
import json
import shutil
import tempfile
import threading
import time
import uuid
import logging
from pathlib import Path

from harnesslab.agent import AgentStopped, run_agent
from harnesslab.models import HarnessConfig, Outcome, read_task
from harnesslab.providers import provider_for
from harnesslab.provenance import harness_identity, image_identity, grading_identity
from harnesslab.repository import apply_patch, checkout, patch
from harnesslab.sandbox import DockerSandbox, LocalSandbox, MacOSSandbox, cleanup_run_containers, sandbox_class
from harnesslab.store import LostLease
from harnesslab.errors import error_details


def resolve_task(path):
    task = read_task(path)
    base = path.resolve().parent
    if not task.repository.startswith(("https://", "http://", "git@")):
        task.repository = str((base / task.repository).resolve())
    task.grading_dir = str((base / task.grading_dir).resolve())
    task.reference_patch = str((base / task.reference_patch).resolve())
    return task


def grade(task, content, backend="docker", allow_unsafe=False, cancel=lambda: False, run_id="standalone"):
    with tempfile.TemporaryDirectory(prefix="harnesslab-grade-") as temp:
        workspace = Path(temp) / "workspace"
        checkout(task.repository, task.commit, workspace)
        try:
            apply_patch(workspace, content)
        except ValueError as exc:
            return Outcome.UNSOLVED, {"error": str(exc)}
        cls = sandbox_class(backend)
        with cls(workspace, image=task.image, grading=Path(task.grading_dir), allow_unsafe=allow_unsafe, run_id=run_id) as sandbox:
            command = task.grade_command
            if backend in {"local", "macos"}:
                command = [str(Path(__import__("sys").executable)) if p == "python" else p.replace("/grading", task.grading_dir) for p in command]
            result = sandbox.command(command, task.limits.command_seconds, task.limits.output_chars, cancel)
            if cancel():
                return Outcome.CANCELLED, {"output": result.output}
            if result.timed_out:
                return Outcome.UNSOLVED, {"output": result.output, "reason": "grading_timeout"}
            return (Outcome.SOLVED if result.code == 0 else Outcome.UNSOLVED), {"code": result.code, "output": result.output}


def validate_task(path, backend="docker", allow_unsafe=False):
    task = resolve_task(Path(path))
    before, before_result = grade(task, "", backend, allow_unsafe)
    after, after_result = grade(task, Path(task.reference_patch).read_text(), backend, allow_unsafe)
    valid = before == Outcome.UNSOLVED and before_result.get("code", 0) != 0 and after == Outcome.SOLVED
    return {"task": task.id, "valid": valid, "before": before_result, "after": after_result}


def run_claimed(store, row, artifacts: Path, backend="docker", allow_unsafe=False, fault=None):
    identity, owner, attempt = row["id"], row["owner"], row["attempt"]
    stopped, lost = threading.Event(), threading.Event()

    def heartbeat():
        while not stopped.wait(5):
            try:
                if not store.heartbeat(identity, owner, attempt):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    def cancel():
        current = store.get(identity)
        if not current or current["owner"] != owner or current["attempt"] != attempt or current["status"] != "running":
            lost.set()
            return True
        if current["lease"] < time.time() and not store.heartbeat(identity, owner, attempt):
            lost.set()
        return lost.is_set() or bool(current["cancelled"])

    def emit(kind, data):
        store.event(identity, attempt, kind, data, owner)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    started = time.monotonic()
    totals = {}
    try:
        task = resolve_task(Path(row["task_path"]))
        config = HarnessConfig.model_validate_json(row["config"])
        if config.provider == "fake" and task.id != "tag-normalization":
            raise ValueError("The scripted provider supports only tag-normalization. Use a real model for corpus evaluations.")
        if config.provider != "fake" and backend == "local":
            raise ValueError("Real-model code requires docker or macos isolation; unsafe local mode is for scripted fixtures only.")
        provenance = {"harness": harness_identity(), "image": image_identity(task.image) if backend == "docker" else None,
                      "task_manifest_sha256": __import__("hashlib").sha256(Path(row["task_path"]).read_bytes()).hexdigest(),
                      "grading_sha256": grading_identity(task.grading_dir)}
        lock = store.study_lock(row["experiment_id"])
        if lock and lock["source_sha256"] != provenance["harness"]["source_sha256"]:
            raise ValueError("Harness source changed after study freeze; start a new study instead of mixing implementations.")
        if lock:
            expected = json.loads(lock["metadata"]).get("task_fingerprints", {}).get(task.id)
            if expected and (expected["manifest_sha256"] != provenance["task_manifest_sha256"] or expected["grading_sha256"] != provenance["grading_sha256"]):
                raise ValueError("Task or grading bundle changed after study freeze")
        if config.provider == "local":
            from harnesslab.provenance import local_model_identity
            provenance["local_model"] = local_model_identity(config.model)
        if backend == "docker":
            # Execute the resolved immutable image, not a tag that can move mid-run.
            task = task.model_copy(update={"image": provenance["image"]["id"]})
        if backend == "docker" and attempt > 1:
            removed = cleanup_run_containers(identity)
            emit("orphan_cleanup", {"containers": removed})
        emit("attempt_started", {"task": task.id, "commit": task.commit, "config_hash": config.digest(), "config": config.model_dump(), "backend": backend, "fault": fault, "provenance": provenance, "warning": "fake provider is a scripted integration fixture" if config.provider == "fake" else None})
        with tempfile.TemporaryDirectory(prefix="harnesslab-run-") as temp:
            workspace = Path(temp) / "workspace"
            checkout(task.repository, task.commit, workspace)
            cls = sandbox_class(backend)
            with cls(workspace, image=task.image, run_id=identity, allow_unsafe=allow_unsafe) as sandbox:
                try:
                    outcome, totals = asyncio.run(run_agent(sandbox, task, config, provider_for(config), emit, cancel, fault,
                        reserve=lambda step, amount: store.reserve(identity, owner, attempt, step, amount),
                        settle=lambda step, amount: store.settle(identity, attempt, step, amount)))
                except AgentStopped as exc:
                    outcome, totals = exc.outcome, exc.totals
                try:
                    content = sandbox.patch() if hasattr(sandbox, "patch") else patch(workspace)
                except RuntimeError as exc:
                    if outcome is None:
                        raise
                    # Docker intentionally kills a timed-out/cancelled sandbox.
                    # Missing its final diff must not erase the stop outcome.
                    emit("patch_unavailable", {"reason":"stopped_sandbox", "error":str(exc)})
                    content=""
            destination = artifacts / identity / str(attempt)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "patch.diff").write_text(content)
            if outcome is None:
                outcome, grading = grade(task, content, backend, allow_unsafe, cancel, identity)
                emit("grading", grading)
            result = {**totals, "duration_seconds": time.monotonic() - started, "patch": str(destination / "patch.diff"), "provider": config.provider}
            emit("attempt_finished", {"outcome": outcome, **result})
            store.finish(identity, owner, attempt, outcome, result)
    except LostLease:
        pass  # A replacement worker owns the job; this worker cannot publish.
    except Exception as exc:
        try:
            causes = error_details(exc)
            message = "; ".join(c["type"] + ": " + c["message"] for c in causes)
            emit("attempt_error", {"type": type(exc).__name__, "error": message, "causes": causes})
            store.finish(identity, owner, attempt, Outcome.INFRA_ERROR, {"error": message, "causes": causes, "duration_seconds": time.monotonic()-started, **totals})
        except LostLease:
            pass
    finally:
        stopped.set()
        thread.join(timeout=6)


def work(store, artifacts, backend="docker", allow_unsafe=False, once=False, fault=None, experiment=None):
    owner = uuid.uuid4().hex
    next_cleanup = 0.0
    while True:
        if backend == "docker" and time.monotonic() >= next_cleanup:
            from harnesslab.maintenance import reconcile
            try:
                reconciled = reconcile(store, apply=True)
                if reconciled:
                    logging.getLogger(__name__).info("Container reconciliation: %s", reconciled)
            except (RuntimeError, OSError, ValueError) as exc:
                logging.getLogger(__name__).warning("Container reconciliation unavailable: %s", exc)
            next_cleanup = time.monotonic()+30
        row = store.claim(owner, experiment=experiment)
        if row:
            run_claimed(store, row, Path(artifacts), backend, allow_unsafe, fault)
        elif once:
            return
        else:
            time.sleep(1)
