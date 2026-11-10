"""Rebuild the authored mutation corpus from pinned, licensed upstream snapshots.

No upstream Git history, gold patches, or HarnessLab files enter agent snapshots.
Use --fetch to download missing upstream repositories. Existing source checkouts
must match the pinned commit and be clean; this script never resets a checkout.
"""
import argparse
import ast
import difflib
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.corpus_specs import SPECS
from harnesslab.provenance import grading_identity

FILES = {"boltons": "boltons/iterutils.py", "more-itertools": "more_itertools/recipes.py", "inflection": "inflection/__init__.py"}
TESTS = {"boltons": "tests/test_iterutils.py", "more-itertools": "tests/test_recipes.py", "inflection": "test_inflection.py"}
IMPORTS = {"boltons": "boltons.iterutils", "more-itertools": "more_itertools", "inflection": "inflection"}
ENV = {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
       "GIT_AUTHOR_NAME": "HarnessLab Corpus", "GIT_COMMITTER_NAME": "HarnessLab Corpus",
       "GIT_AUTHOR_EMAIL": "corpus@harnesslab.local", "GIT_COMMITTER_EMAIL": "corpus@harnesslab.local",
       "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args, **kwargs):
    return subprocess.check_output(["git", "-C", str(repo), *args], env=ENV, **kwargs)


def mutate(text, function, before, after):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == function)
    lines = text.splitlines(keepends=True)
    block = "".join(lines[node.lineno-1:node.end_lineno])
    if block.count(before) != 1:
        raise ValueError(f"{function}: mutation anchor must occur exactly once")
    lines[node.lineno-1:node.end_lineno] = [block.replace(before, after, 1)]
    changed = "".join(lines)
    ast.parse(changed)
    return changed


def snapshot(source, commit, destination):
    archive = git(source, "archive", commit)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter="data")


def build(fetch=False):
    sources = json.loads((ROOT / "benchmarks/sources.json").read_text())["sources"]
    for source in sources:
        repo = ROOT / ".harnesslab/upstream" / source["name"]
        if not repo.exists():
            if not fetch:
                raise RuntimeError(f"missing {repo}; run with --fetch")
            repo.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", source["repository"] + ".git", str(repo)], check=True)
            git(repo, "checkout", "--detach", source["commit"])
        if git(repo, "rev-parse", "HEAD", text=True).strip() != source["commit"] or git(repo, "status", "--porcelain", text=True).strip():
            raise RuntimeError(f"{repo} must be clean at pinned commit {source['commit']}; checkout the pin explicitly")
        if hashlib.sha256((repo / "LICENSE").read_bytes()).hexdigest() != source["license_sha256"]:
            raise RuntimeError("license hash mismatch")
    by_name = {s["name"]: s for s in sources}
    catalog = []
    for index, (name, function, before, after, issue, assertions) in enumerate(SPECS):
        source = by_name[name]
        identity = name + "-" + function.replace("_", "-")
        path = FILES[name]
        upstream = ROOT / ".harnesslab/upstream" / name
        original = (upstream / path).read_text()
        broken = mutate(original, function, before, after)
        repo = ROOT / ".harnesslab/corpus" / identity
        fingerprint = hashlib.sha256((source["commit"] + path + broken).encode()).hexdigest()
        marker = repo / ".git/harnesslab-fingerprint"
        if marker.exists() and marker.read_text() != fingerprint:
            # New task construction gets a new immutable repository, never a reset.
            repo = repo.parent / (identity + "-" + fingerprint[:12])
            marker = repo / ".git/harnesslab-fingerprint"
        if not marker.exists():
            if repo.exists():
                raise RuntimeError(f"refusing to overwrite incomplete snapshot: {repo}")
            repo.mkdir(parents=True)
            snapshot(upstream, source["commit"], repo)
            (repo / path).write_text(broken)
            for args in [("init",), ("config", "core.autocrlf", "false"), ("config", "user.email", "corpus@harnesslab.local"), ("config", "user.name", "HarnessLab Corpus"), ("add", "--force", "."), ("commit", "--no-verify", "--no-gpg-sign", "-m", f"Frozen authored regression fixture: {identity}")]:
                git(repo, *args)
            marker.write_text(fingerprint)
        if marker.read_text() != fingerprint or git(repo, "status", "--porcelain", text=True).strip():
            raise RuntimeError(f"snapshot changed: {repo}")
        commit = git(repo, "rev-parse", "HEAD", text=True).strip()
        grading = ROOT / "benchmarks/grading" / identity
        grading.mkdir(parents=True, exist_ok=True)
        hidden = f"import pytest\nfrom itertools import islice\nimport {IMPORTS[name]} as m\n\n"
        for n, assertion in enumerate(assertions):
            hidden += f"def test_contract_{n}():\n    " + assertion + "\n\n"
        (grading / "test_hidden.py").write_text(hidden)
        (grading / "test_upstream.py").write_bytes((upstream / TESTS[name]).read_bytes())
        (grading / "LICENSE.upstream").write_bytes((upstream / "LICENSE").read_bytes())
        (grading / "pytest.ini").write_text("[pytest]\naddopts =\n")
        (grading / "run.py").write_text("import os, sys\nfrom pathlib import Path\nimport pytest\nsys.path.insert(0, os.getcwd())\np=Path(__file__).resolve().parent\nraise SystemExit(pytest.main(['-q','--import-mode=importlib','-c',str(p/'pytest.ini'),str(p/'test_hidden.py'),str(p/'test_upstream.py')]))\n")
        patch = "".join(difflib.unified_diff(broken.splitlines(True), original.splitlines(True), fromfile="a/"+path, tofile="b/"+path))
        patch_path = ROOT / "benchmarks/patches" / (identity + ".diff")
        patch_path.write_text(patch)
        # Freeze 3 boltons + 3 more-itertools + 4 inflection tasks as development.
        position = index % 10
        split = "development" if position < (4 if name == "inflection" else 3) else "held-out"
        manifest = {"schema_version": 1, "id": identity, "repository": f"../../.harnesslab/corpus/{repo.name}", "commit": commit,
                    "issue": issue + " Preserve the public API and do not modify tests.", "image": "harnesslab-task:local",
                    "visible_command": ["python", "-m", "pytest", "-q", TESTS[name]],
                    "grade_command": ["python", "-I", "/grading/run.py"], "grading_dir": f"../grading/{identity}",
                    "reference_patch": f"../patches/{identity}.diff", "split": split,
                    "provenance": f"Authored regression mutation on {source['repository']} at {source['commit']}; {source['license']}. Synthetic task, not an upstream issue.",
                    "limits": {"steps": 40, "wall_seconds": 300, "command_seconds": 30, "tokens": 100000, "cost_usd": 1, "output_chars": 16000}}
        task_path = ROOT / "benchmarks/tasks" / (identity + ".json")
        task_path.write_text(json.dumps(manifest, indent=2) + "\n")
        catalog.append({"id": identity, "source": name, "source_commit": source["commit"], "snapshot_commit": commit, "split": split,
                        "hidden_sha256": hashlib.sha256(hidden.encode()).hexdigest(), "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
                        "grading_sha256": grading_identity(grading), "manifest_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest()})
        print(identity, split)
    (ROOT / "benchmarks/catalog.json").write_text(json.dumps({"schema_version": 1, "construction": "authored mutation regression suite", "tasks": catalog}, indent=2) + "\n")
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    build(parser.parse_args().fetch)
