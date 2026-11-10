"""Run a frozen local-model pilot or the 120-trial held-out comparison.

Checkpoints after every run and resumes an existing experiment without rerunning
finished jobs. Source changes invalidate the study, rather than mixing results.
"""
import argparse
import hashlib
import json
import os
import sys
import uuid
import tarfile
import platform
import subprocess
import time
from urllib.parse import urlparse

import httpx
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harnesslab.models import HarnessConfig
from harnesslab.provenance import harness_identity, local_model_identity
from harnesslab.report import export
from harnesslab.runner import run_claimed
from harnesslab.store import Store


def external_power():
    if platform.system()!="Darwin":
        return True
    result=subprocess.run(["pmset","-g","batt"],capture_output=True,text=True,check=True,timeout=5)
    return "AC Power" in result.stdout


def wait_for_power():
    if external_power():
        return
    print("WAITING_FOR_POWER: no new evaluation work will start until the Mac is on external power.",flush=True)
    while not external_power():
        time.sleep(15)
    print("EXTERNAL_POWER_READY",flush=True)


def model_ready():
    url=os.environ.get("HARNESSLAB_LOCAL_MODEL_URL","http://127.0.0.1:8080/v1").rstrip('/')
    parsed=urlparse(url)
    if parsed.scheme!="http" or parsed.hostname not in {"127.0.0.1","localhost","::1"} or parsed.username or parsed.password:
        raise ValueError("local inference requires an unauthenticated loopback endpoint")
    try:
        response=httpx.get(url+"/models",timeout=5,trust_env=False)
        response.raise_for_status()
        if not response.json().get("data"):
            raise ValueError("local endpoint has no loaded model")
    except (httpx.HTTPError,ValueError) as exc:
        raise RuntimeError("Local model is not ready. Start scripts/local_model.py serve, then resume the study.") from exc


def main(phase, backend, resume=None, require_power=False):
    initial_source=harness_identity()
    power_gated=phase=="held-out" or require_power
    if power_gated:
        wait_for_power()
    if harness_identity()["source_sha256"]!=initial_source["source_sha256"]:
        raise RuntimeError("runtime changed while waiting for power; restart the coordinator before starting a study")
    model_ready()
    store = Store(os.environ.get("HARNESSLAB_DATABASE_URL", str(ROOT / ".harnesslab/state.db")))
    source = harness_identity()
    catalog_file = ROOT / "benchmarks/catalog.json"
    catalog = json.loads(catalog_file.read_text())
    if resume:
        identity = resume
        lock = store.study_lock(identity)
        if not lock or lock["source_sha256"] != source["source_sha256"]:
            raise RuntimeError("missing study lock or harness changed since freeze")
        saved=json.loads(lock["metadata"])
        if saved["phase"]!=phase or saved["backend"]!=backend:
            raise RuntimeError("resume must preserve the study phase and execution backend")
    else:
        configs = [HarnessConfig.model_validate_json((ROOT / "configs" / f"local-{name}.json").read_text()) for name in ["baseline", "resilient"]]
        selected = [t for t in catalog["tasks"] if t["split"] == ("development" if phase == "pilot" else "held-out")]
        if phase == "pilot":
            groups = defaultdict(list)
            for task in selected:
                groups[task["source"]].append(task)
            selected = [groups[name][i] for i in range(4) for name in sorted(groups) if len(groups[name]) > i][:5]
        repetitions = 1 if phase == "pilot" else 3
        identity = store.experiment(f"Local Qwen3 · {phase} · {source['source_sha256'][:8]}")
        metadata = {"phase": phase, "created": datetime.now(timezone.utc).isoformat(), "backend": backend,
                    "catalog_sha256": hashlib.sha256(catalog_file.read_bytes()).hexdigest(), "harness": source,
                    "model": local_model_identity(configs[0].model), "tasks": [t["id"] for t in selected],
                    "repetitions": repetitions, "configs": [c.model_dump() for c in configs], "seed": 42,
                    "task_fingerprints": {t["id"]:{"manifest_sha256":t["manifest_sha256"],"grading_sha256":t["grading_sha256"]} for t in selected},
                    "limitation": "Fixed-seed repeated trials measure repeatability; they are not independent stochastic samples."}
        store.lock_study(identity, source["source_sha256"], metadata)
        for task in selected:
            for _ in range(repetitions):
                for config in configs:
                    store.enqueue(identity, ROOT / "benchmarks/tasks" / (task["id"] + ".json"), config)
    destination = ROOT / ".harnesslab/studies" / identity
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "manifest.json").write_text(store.study_lock(identity)["metadata"] + "\n")
    archive_path = destination / "reproduction.tar.gz"
    if not archive_path.exists():
        if resume:
            raise RuntimeError("study predates reproduction archives; publish its checkpoint as historical evidence and create a new study")
        # Allowlist project source and the selected grading bundles. Exclude API
        # keys, .env files, model weights, caches, and unrelated workspace files.
        files = list((ROOT/"harnesslab").glob("*.py")) + list((ROOT/"scripts").glob("*.py"))
        files += [ROOT/p for p in ["pyproject.toml","requirements-lock.txt","README.md","Dockerfile","compose.yaml","docker/task.Dockerfile",
            "benchmarks/catalog.json","benchmarks/validation.json","benchmarks/sources.json","benchmarks/corpus_specs.py",
            "configs/local-baseline.json","configs/local-resilient.json","frontend/package.json","frontend/pnpm-lock.yaml",
            "frontend/pnpm-workspace.yaml","frontend/tsconfig.json","frontend/vite.config.ts","frontend/index.html"]]
        for folder in ["benchmarks/tasks","benchmarks/patches","benchmarks/grading","benchmarks/fixtures","tests","frontend/src"]:
            files += [p for p in (ROOT/folder).rglob("*") if p.is_file() and not any(part in {"__pycache__",".pytest_cache"} for part in p.relative_to(ROOT).parts)]
        temporary_archive = destination / "reproduction.tar.gz.tmp"
        with tarfile.open(temporary_archive,"w:gz",dereference=True) as archive:
            for path in sorted(set(files)):
                archive.add(path,arcname=str(path.relative_to(ROOT)))
        temporary_archive.replace(archive_path)
        Path(str(archive_path)+".sha256").write_text(hashlib.sha256(archive_path.read_bytes()).hexdigest()+"\n")
    checksum_path=Path(str(archive_path)+".sha256")
    if not checksum_path.is_file() or hashlib.sha256(archive_path.read_bytes()).hexdigest()!=checksum_path.read_text().strip():
        raise RuntimeError("study reproduction archive failed checksum verification")
    print("STUDY", identity, flush=True)
    owner = uuid.uuid4().hex
    awake=None
    if power_gated and platform.system()=="Darwin":
        # -s is an AC-only assertion; it does not prevent battery idle sleep.
        awake=subprocess.Popen(["/usr/bin/caffeinate","-s","-w",str(os.getpid())])
    failures=0
    while True:
        if power_gated:
            wait_for_power()
        row=store.claim(owner,experiment=identity)
        if not row:
            break
        run_claimed(store, row, ROOT / ".harnesslab/artifacts", backend)
        state = store.get(row["id"])
        print(Path(row["task_path"]).stem, json.loads(row["config"])["name"], state["status"], flush=True)
        temporary = destination / "results.tmp"
        temporary.write_text(json.dumps(export(store, identity), indent=2) + "\n")
        temporary.replace(destination / "results.json")
        failures=failures+1 if state["status"]=="infrastructure_error" else 0
        if failures>=3:
            print("STOPPED_AFTER_INFRASTRUCTURE_ERRORS: inspect the checkpoint and resume after fixing the dependency.",flush=True)
            break
    if awake is not None:
        awake.terminate()
        awake.wait(timeout=5)
    print("CHECKPOINT", destination / "results.json", flush=True)
    return identity


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["pilot", "held-out"])
    parser.add_argument("--backend", choices=["docker", "macos"], default="docker")
    parser.add_argument("--resume")
    parser.add_argument("--wait-for-power",action="store_true",help="Also gate the development pilot on external power; held-out studies always wait.")
    parser.add_argument("--then-held-out",action="store_true",help="After a completed pilot, publish it and run/publish the held-out comparison.")
    args = parser.parse_args()
    if args.then_held_out and args.phase!="pilot":
        parser.error("--then-held-out is only valid with the pilot phase")
    identity=main(args.phase,args.backend,args.resume,args.wait_for_power)
    if args.then_held_out:
        from publish_study import publish
        publish(identity)
        held_out=main("held-out",args.backend,require_power=True)
        publish(held_out)
