import subprocess
import ast
import os
from pathlib import Path

from harnesslab.sandbox import execute


def checkout(repository: str, commit: str, destination: Path):
    for args in [["git", "clone", "--no-hardlinks", "--no-checkout", "--", repository, str(destination)],
                 ["git", "-C", str(destination), "checkout", "--detach", commit],
                 ["git", "-C", str(destination), "config", "user.email", "agent@harnesslab.local"],
                 ["git", "-C", str(destination), "config", "user.name", "HarnessLab"]]:
        result = execute(args, timeout=120)
        if result.code:
            raise RuntimeError(result.output)


def patch(workspace: Path):
    subprocess.run(["git", "-C", str(workspace), "add", "-N", "."], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(workspace), "diff", "--binary", "HEAD"], check=True, capture_output=True, text=True).stdout


def apply_patch(workspace: Path, content: str):
    if not content.strip():
        return
    # Let Git decode quoted, binary, and mode-only paths. Header-only string
    # checks miss e.g. +++ "b/tests/test.py" and chmod-only changes.
    inspected = subprocess.run(["git", "-C", str(workspace), "apply", "--numstat", "-z", "-"], input=content.encode(), capture_output=True)
    if inspected.returncode:
        raise ValueError("invalid patch: " + inspected.stderr.decode(errors="replace"))
    names = []
    for entry in inspected.stdout.split(b"\0"):
        if entry:
            fields = entry.split(b"\t", 2)
            if len(fields) != 3 or not fields[2]:
                raise ValueError("unsupported patch path metadata")
            names.append(os.fsdecode(fields[2]))
    # Numstat reports the destination of renames/copies. Check their source too.
    for line in content.splitlines():
        if line.startswith(("rename from ", "copy from ")):
            raw = line.split(" from ", 1)[1]
            try:
                names.append(ast.literal_eval(raw) if raw.startswith('"') else raw)
            except (ValueError, SyntaxError):
                raise ValueError("invalid quoted patch path") from None
    protected = {".git", "test", "tests", "grading", "conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"}
    for name in names:
        parts = [part.casefold() for part in Path(name).parts]
        if any(part in protected for part in parts) or (parts and (parts[-1].startswith("test_") or parts[-1].endswith("_test.py"))):
            raise ValueError("patch changes protected test/configuration paths")
    result = subprocess.run(["git", "-C", str(workspace), "apply", "--whitespace=nowarn", "-"], input=content, capture_output=True, text=True)
    if result.returncode:
        raise ValueError("invalid patch: " + result.stderr)
