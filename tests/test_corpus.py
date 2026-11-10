import hashlib
import json
from collections import Counter
from pathlib import Path

from harnesslab.models import read_task
from harnesslab.provenance import grading_identity


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_catalog_integrity():
    catalog = json.loads((ROOT / "benchmarks/catalog.json").read_text())
    assert len(catalog["tasks"]) == 30
    assert Counter(t["source"] for t in catalog["tasks"]) == {"boltons": 10, "inflection": 10, "more-itertools": 10}
    assert Counter(t["split"] for t in catalog["tasks"]) == {"development": 10, "held-out": 20}
    for item in catalog["tasks"]:
        task = read_task(ROOT / "benchmarks/tasks" / (item["id"] + ".json"))
        assert task.commit == item["snapshot_commit"]
        assert task.split == item["split"]
        grade = ROOT / "benchmarks/tasks" / task.grading_dir
        patch = ROOT / "benchmarks/tasks" / task.reference_patch
        assert hashlib.sha256((grade / "test_hidden.py").read_bytes()).hexdigest() == item["hidden_sha256"]
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == item["patch_sha256"]
        assert (grade / "LICENSE.upstream").is_file()
        assert grading_identity(grade) == item["grading_sha256"]
        assert hashlib.sha256((ROOT/"benchmarks/tasks"/(item["id"]+".json")).read_bytes()).hexdigest() == item["manifest_sha256"]


def test_validation_report_matches_frozen_catalog():
    catalog = ROOT / "benchmarks/catalog.json"
    validation = json.loads((ROOT / "benchmarks/validation.json").read_text())
    assert validation["catalog_sha256"] == hashlib.sha256(catalog.read_bytes()).hexdigest()
    assert validation["validated"] == validation["total"] == 30
    assert all(t["before"].get("code") != 0 and t["after"].get("code") == 0 for t in validation["tasks"])
