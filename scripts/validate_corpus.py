"""Validate the frozen base/reference pairs; this does not call any model."""
import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harnesslab.runner import validate_task


def validate(backend="docker", allow_unsafe=False, workers=2):
    catalog_path = ROOT / "benchmarks/catalog.json"
    catalog = json.loads(catalog_path.read_text())
    results = []
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(validate_task, ROOT / "benchmarks/tasks" / (t["id"] + ".json"), backend, allow_unsafe): t for t in catalog["tasks"]}
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"task": task["id"], "valid": False, "error": str(exc)}
            results.append({**result, "split": task["split"], "snapshot_commit": task["snapshot_commit"], "hidden_sha256": task["hidden_sha256"], "patch_sha256": task["patch_sha256"]})
            print(task["id"], "PASS" if result["valid"] else "FAIL", flush=True)
    output = {"schema_version": 1, "created": datetime.now(timezone.utc).isoformat(), "backend": backend,
              "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
              "validated": sum(r["valid"] for r in results), "total": len(results), "tasks": sorted(results, key=lambda r: r["task"])}
    target = ROOT / "benchmarks/validation.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["docker", "macos", "local"], default="docker")
    parser.add_argument("--allow-unsafe-local", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1,9), default=2)
    args = parser.parse_args()
    result = validate(args.backend, args.allow_unsafe_local, args.workers)
    print(f"{result['validated']}/{result['total']} validated")
    raise SystemExit(0 if result["validated"] == result["total"] else 1)
