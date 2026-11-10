import hashlib
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from harnesslab.sandbox import execute


def harness_identity():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    sources = sorted((root / "harnesslab").glob("*.py"))
    sources += [root / name for name in ["pyproject.toml", "requirements-lock.txt"] if (root / name).is_file()]
    for path in sources:
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    try:
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).strip())
    except subprocess.CalledProcessError:
        commit, dirty = None, True
    import platform
    return {"git_commit": commit, "dirty": dirty, "source_sha256": digest.hexdigest(), "python": sys.version.split()[0], "os": platform.system(), "os_release": platform.release(), "machine": platform.machine()}


def image_identity(image):
    result = execute(["docker", "image", "inspect", image, "--format", "{{json .}}"], timeout=10, limit=200000)
    if result.code:
        raise RuntimeError("Task image not available locally; build it first: " + result.output)
    data = json.loads(result.output)
    return {"reference": image, "id": data["Id"], "repo_digests": data.get("RepoDigests", [])}


def grading_identity(folder):
    root = Path(folder).resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(part in {"__pycache__", ".pytest_cache"} for part in path.relative_to(root).parts):
            digest.update(str(path.relative_to(root)).encode()+b"\0"+path.read_bytes()+b"\0")
    return digest.hexdigest()


@lru_cache(maxsize=8)
def _hash_model(path, size, modified_ns):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while block := source.read(8*1024*1024):
            digest.update(block)
    return digest.hexdigest()


def local_model_identity(model):
    root = Path(__file__).resolve().parents[1] / ".harnesslab/local-model"
    manifest_path = root / "provenance.json"
    if not manifest_path.is_file():
        return {"identity": model, "weights_verified": False, "note": "externally managed local endpoint"}
    manifest = json.loads(manifest_path.read_text())
    weights = root / (model + ".gguf")
    if not weights.is_file():
        return {"identity": model, "weights_verified": False, "note": "external model is not the managed pinned download"}
    stat = weights.stat()
    actual = _hash_model(str(weights), stat.st_size, stat.st_mtime_ns)
    if actual != manifest["model_sha256"]:
        raise ValueError("managed local-model checksum changed")
    return {**manifest, "identity": model, "weights_verified": True}
