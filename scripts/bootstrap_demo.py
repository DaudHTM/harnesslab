"""Materialize the authored fixture as a reproducible Git repository, without network."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def bootstrap(root: Path):
    repo = root / ".harnesslab/repos/tag-utils"
    if not (repo / ".git").is_dir():
        shutil.copytree(root / "benchmarks/fixtures/tag-utils", repo, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        env = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}
        for args in [["init"], ["config", "user.email", "fixture@harnesslab.local"], ["config", "user.name", "HarnessLab Fixture"], ["add", "."], ["commit", "-m", "Frozen authored normalization fixture"]]:
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    tasks = root / "benchmarks/tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "id": "tag-normalization", "repository": "../../.harnesslab/repos/tag-utils", "commit": commit,
                "issue": "normalize_tags must strip surrounding whitespace, lowercase tags, discard empty tags, remove duplicates, and return sorted results. Preserve the public function signature.",
                "grading_dir": "../grading/tag-normalization", "reference_patch": "../patches/tag-normalization.diff", "split": "development",
                "provenance": "Authored integration fixture; deliberately introduced bug; not an upstream issue or held-out benchmark."}
    (tasks / "tag-normalization.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return tasks / "tag-normalization.json"


if __name__ == "__main__":
    print(bootstrap(Path(__file__).resolve().parents[1]))
