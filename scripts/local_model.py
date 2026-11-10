"""Pinned, checksum-verified local inference setup. No account or API billing."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tarfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".harnesslab/local-model"
RELEASE = "b12110"
BINARY_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{RELEASE}/llama-{RELEASE}-bin-macos-arm64.tar.gz"
BINARY_SHA = "4f5b8de12e0b9516658ca6a5764c6ffb3d7c659c3dd538556b1413c7b4050662"
MODEL_REPO = "ggml-org/Qwen3-4B-Instruct-2507-Q8_0-GGUF"
MODEL_REV = "e6f794d44f9395d0184a966c27b5ae99ea356fcb"
MODEL_FILE = "qwen3-4b-instruct-2507-q8_0.gguf"
MODEL_SHA = "ae916ede1c010a26955ee8ae2e908bf8815a3f135ec860439ab924701c69d5f1"
MODEL_SIZE = 4280403520


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(8*1024*1024):
            digest.update(block)
    return digest.hexdigest()


def download(url, target, expected_sha):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) == expected_sha:
            print("Verified cached", target.name, flush=True)
            return
        raise RuntimeError(f"checksum mismatch for existing {target}; inspect it before retrying")
    partial = target.with_suffix(target.suffix + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    with httpx.Client(timeout=httpx.Timeout(120, connect=30), follow_redirects=True) as client:
        with client.stream("GET", url, headers={"Range": f"bytes={offset}-"} if offset else {}) as response:
            response.raise_for_status()
            if offset and (response.status_code != 206 or not response.headers.get("content-range", "").startswith(f"bytes {offset}-")):
                raise RuntimeError("download server did not honor resume range")
            last_progress = offset // (256*1024*1024)
            with partial.open("ab" if offset else "wb") as output:
                for block in response.iter_bytes(4*1024*1024):
                    output.write(block)
                    offset += len(block)
                    progress = offset // (256*1024*1024)
                    if progress > last_progress:
                        print(f"{target.name}: {offset/1024**3:.2f} GiB downloaded", flush=True)
                        last_progress = progress
    actual = sha256(partial)
    if actual != expected_sha:
        raise RuntimeError(f"checksum mismatch for downloaded {target.name}: {actual}")
    partial.replace(target)
    print("Verified", target.name, flush=True)


def setup():
    if (platform.system(), platform.machine()) != ("Darwin", "arm64"):
        raise RuntimeError("This pinned binary targets Apple Silicon. On other hosts, run a compatible llama-server and set HARNESSLAB_LOCAL_MODEL_URL.")
    archive = RUNTIME / "llama.tar.gz"
    download(BINARY_URL, archive, BINARY_SHA)
    binary_dir = RUNTIME / RELEASE
    if not binary_dir.exists():
        binary_dir.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(binary_dir, filter="data")
    download(f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REV}/{MODEL_FILE}", RUNTIME / MODEL_FILE, MODEL_SHA)
    (RUNTIME / "provenance.json").write_text(json.dumps({"runtime_release": RELEASE, "runtime_archive_sha256": BINARY_SHA,
        "model_repository": MODEL_REPO, "model_revision": MODEL_REV, "model_sha256": MODEL_SHA, "model_bytes": MODEL_SIZE,
        "quantization": "Q8_0", "license": "Apache-2.0", "provider_api_cost_usd": 0}, indent=2) + "\n")
    print("Ready. Run: .venv/bin/python scripts/local_model.py serve", flush=True)


def serve(port=8080):
    candidates = list((RUNTIME / RELEASE).rglob("llama-server"))
    if not candidates or not (RUNTIME / MODEL_FILE).is_file():
        raise RuntimeError("run setup first")
    command = [str(candidates[0]), "-m", str(RUNTIME / MODEL_FILE), "--host", "127.0.0.1", "--port", str(port),
               "--ctx-size", "16384", "--parallel", "1", "--n-gpu-layers", "99", "--jinja", "--temp", "0.2", "--seed", "42",
               "--cors-origins", f"http://127.0.0.1:{port}", "--no-cors-credentials", "--no-webui", "--no-slots"]
    print("Starting pinned local model on loopback only", flush=True)
    os.execv(command[0], command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "serve"])
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    setup() if args.action == "setup" else serve(args.port)
