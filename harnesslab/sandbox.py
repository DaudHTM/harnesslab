"""Execution boundaries. LocalSandbox is deliberately opt-in and NOT isolation."""
import os
import signal
import subprocess
import tempfile
import tarfile
import io
import time
import uuid
import sys
import re
import threading
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Result:
    code: int
    output: str
    timed_out: bool = False


def command_environment(argv):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"}
    if argv and Path(argv[0]).name == "docker":
        # The trusted Docker client needs its daemon connection/context. These
        # variables are never passed as environment options to task containers.
        env["HOME"] = os.environ.get("HOME", "/tmp")
        for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_API_VERSION"):
            if name in os.environ:
                env[name] = os.environ[name]
    return env


def execute(argv: list[str], cwd: Path | None = None, timeout: float = 20,
            limit: int = 12000, cancel: Callable[[], bool] = lambda: False, env: dict | None = None) -> Result:
    # Drain output continuously but retain only a bounded prefix. No RAM/disk flood.
    retained = bytearray()
    truncated = False
    proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True, env=env if env is not None else command_environment(argv))
    def drain():
        nonlocal truncated
        while block := proc.stdout.read(8192):
            room = max(0, limit - len(retained))
            retained.extend(block[:room])
            truncated |= len(block) > room
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    try:
        while proc.poll() is None:
            if cancel() or time.monotonic() >= deadline:
                timed_out = time.monotonic() >= deadline
                break
            time.sleep(0.03)
    finally:
        # Kill the process group even if the main process left background children.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        reader.join(timeout=2)
        proc.stdout.close()
    return Result(124 if timed_out else proc.returncode,
                  retained.decode(errors="replace") + ("\n[truncated]" if truncated else ""), timed_out)


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if path == root.resolve() or root.resolve() not in path.parents or ".git" in Path(relative).parts:
        raise ValueError("path must stay inside workspace and outside .git")
    return path


class LocalSandbox:
    def __init__(self, workspace: Path, *, allow_unsafe: bool = False, **kwargs):
        if not allow_unsafe:
            raise ValueError("local execution requires --allow-unsafe-local; use only trusted fixtures")
        self.workspace = workspace

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def command(self, argv, timeout=20, limit=12000, cancel=lambda: False):
        if argv and argv[0] == "python":
            argv = [sys.executable, *argv[1:]]
        return execute(argv, self.workspace, timeout, limit, cancel)

    def read(self, path):
        target = safe_path(self.workspace, path)
        if target.stat().st_size > 100000:
            raise ValueError("file exceeds 100KB read limit")
        return target.read_text()

    def write(self, path, content):
        target = safe_path(self.workspace, path)
        if len(content.encode()) > 100000:
            raise ValueError("file exceeds 100KB write limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return "written"

    def files(self):
        return sorted(str(p.relative_to(self.workspace)) for p in self.workspace.rglob("*")
                      if p.is_file() and ".git" not in p.parts and not p.is_symlink())[:1000]


class DockerSandbox:
    def __init__(self, workspace: Path, *, image: str, grading: Path | None = None, run_id="standalone", **kwargs):
        self.workspace, self.image, self.grading = workspace, image, grading
        self.name = "harnesslab-" + uuid.uuid4().hex[:16]
        self.run_id = run_id

    def _docker(self, args, timeout=30, limit=12000, cancel=lambda: False):
        return execute(["docker", *args], timeout=timeout, limit=limit, cancel=cancel)

    def __enter__(self):
        args = ["create", "--name", self.name, "--label", "harnesslab.managed=true", "--label", f"harnesslab.run={self.run_id}",
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "128", "--memory", "512m", "--cpus", "1", "--user", "1000:1000",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m,mode=1777", "--workdir", "/workspace"]
        args.extend(["--tmpfs", "/workspace:rw,nosuid,size=256m,uid=1000,gid=1000",
                     "--tmpfs", "/grading:rw,noexec,nosuid,size=32m,uid=1000,gid=1000"])
        # No host mounts: files are copied into an internal writable image directory.
        result = self._docker([*args, self.image, "sleep", "infinity"])
        if result.code:
            raise RuntimeError(result.output)
        try:
            started = self._docker(["start", self.name])
            if started.code:
                raise RuntimeError(started.output)
            for source, target in [(self.workspace, "/workspace"), (self.grading, "/grading")]:
                if source:
                    with io.BytesIO() as archive:
                        with tarfile.open(fileobj=archive, mode="w") as tar:
                            tar.add(source, arcname=".")
                        argv = ["docker", "exec", "-i", "--", self.name, "tar", "--no-same-owner", "-xf", "-", "-C", target]
                        copied = subprocess.run(argv, input=archive.getvalue(), capture_output=True, timeout=30, env=command_environment(argv))
                        if copied.returncode:
                            raise RuntimeError(copied.stderr.decode(errors="replace"))
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *args):
        self._docker(["rm", "-f", self.name])

    def command(self, argv, timeout=20, limit=12000, cancel=lambda: False):
        result = self._docker(["exec", "--", self.name, *argv], timeout, limit, cancel)
        if result.timed_out or cancel():
            self._docker(["kill", self.name])
        return result

    def read(self, path):
        safe_path(Path("/workspace"), path)
        result = self.command(["python", "-c", "from pathlib import Path; import sys; p=Path(sys.argv[1]).resolve(); assert p.is_relative_to('/workspace') and '.git' not in p.parts; assert p.stat().st_size<=100000; print(p.read_text(),end='')", path], limit=100000)
        if result.code:
            raise ValueError(result.output)
        return result.output

    def write(self, path, content):
        safe_path(Path("/workspace"), path)
        if len(content.encode()) > 100000:
            raise ValueError("file exceeds 100KB write limit")
        result = self.command(["python", "-c", "from pathlib import Path; import sys; p=Path(sys.argv[1]).resolve(); assert p.is_relative_to('/workspace') and '.git' not in p.parts; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(sys.argv[2])", path, content])
        if result.code:
            raise ValueError(result.output)
        return "written"

    def files(self):
        result = self.command(["git", "ls-files", "--cached", "--others", "--exclude-standard"])
        if result.code:
            raise RuntimeError(result.output)
        return result.output.splitlines()[:1000]

    def patch(self):
        self.command(["git", "add", "-N", "."])
        result = self.command(["git", "diff", "--binary", "HEAD"], limit=1000000)
        if result.code or "[truncated]" in result.output:
            raise RuntimeError("cannot collect complete patch")
        return result.output


class MacOSSandbox:
    """Native, deny-by-default process isolation for curated local evaluations.

    Uses deprecated sandbox-exec, not a container. It has no aggregate disk or
    memory quota; use Docker for the portable resource-limited backend.
    """
    def __init__(self, workspace: Path, *, grading: Path | None = None, **kwargs):
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").exists():
            raise RuntimeError("macos backend requires macOS sandbox-exec")
        self.workspace = workspace.resolve()
        self.grading = grading.resolve() if grading else None
        self.scratch = tempfile.TemporaryDirectory(prefix="harnesslab-native-")
        self.temp = Path(self.scratch.name).resolve()
        reads = [self.workspace, self.temp, Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
                 Path("/System"), Path("/usr"), Path("/bin"), Path("/sbin"), Path("/Library/Developer/CommandLineTools")]
        if self.grading:
            reads.append(self.grading)
        subpaths = "".join(f"(subpath {json.dumps(str(p))})" for p in reads)
        # dyld needs read access to the root directory itself (not its descendants).
        self.policy = ('(version 1)(deny default)(allow process-exec)(allow process-fork)(allow sysctl-read)'
            '(allow file-read-metadata)(allow file-read* (literal "/")' + subpaths +
            '(literal "/dev/null")(literal "/dev/random")(literal "/dev/urandom"))'
            '(allow file-write* (subpath ' + json.dumps(str(self.workspace)) + ')(subpath ' + json.dumps(str(self.temp)) +
            ')(literal "/dev/null"))(deny network*)')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.scratch.cleanup()

    def command(self, argv, timeout=20, limit=12000, cancel=lambda: False):
        if argv and argv[0] == "python":
            argv = [sys.executable, *argv[1:]]
        if argv and argv[0] == "git" and Path("/Library/Developer/CommandLineTools/usr/bin/git").is_file():
            argv = ["/Library/Developer/CommandLineTools/usr/bin/git", *argv[1:]]
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(self.temp), "TMPDIR": str(self.temp),
               "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        return execute(["/usr/bin/sandbox-exec", "-p", self.policy, *argv], self.workspace, timeout, limit, cancel, env)

    def read(self, path):
        code = "from pathlib import Path; import sys; root=Path(sys.argv[1]); p=(root/sys.argv[2]).resolve(); assert p.is_relative_to(root) and '.git' not in p.parts; assert p.stat().st_size<=100000; print(p.read_text(),end='')"
        result = self.command(["python", "-I", "-c", code, str(self.workspace), path], limit=100000)
        if result.code:
            raise ValueError(result.output)
        return result.output

    def write(self, path, content):
        if len(content.encode()) > 100000:
            raise ValueError("file exceeds 100KB write limit")
        code = "from pathlib import Path; import sys; root=Path(sys.argv[1]); p=(root/sys.argv[2]).resolve(); assert p.is_relative_to(root) and '.git' not in p.parts; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(sys.argv[3])"
        result = self.command(["python", "-I", "-c", code, str(self.workspace), path, content])
        if result.code:
            raise ValueError(result.output)
        return "written"

    def files(self):
        result = self.command(["git", "ls-files", "--cached", "--others", "--exclude-standard"])
        if result.code:
            raise RuntimeError(result.output)
        return result.output.splitlines()[:1000]

    def patch(self):
        added = self.command(["git", "add", "-N", "."])
        if added.code:
            raise RuntimeError(added.output)
        result = self.command(["git", "diff", "--binary", "HEAD"], limit=1000000)
        if result.code or "[truncated]" in result.output:
            raise RuntimeError("cannot collect complete patch: " + result.output)
        return result.output


def sandbox_class(backend):
    try:
        return {"docker": DockerSandbox, "local": LocalSandbox, "macos": MacOSSandbox}[backend]
    except KeyError:
        raise ValueError("backend must be docker, macos, or local") from None


def cleanup_run_containers(run_id: str):
    """Remove only containers carrying this exact HarnessLab run label."""
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("invalid run ID for cleanup")
    found = execute(["docker", "ps", "-aq", "--filter", "label=harnesslab.managed=true", "--filter", f"label=harnesslab.run={run_id}"], timeout=10)
    if found.code:
        raise RuntimeError(found.output)
    ids = found.output.splitlines()
    if any(not re.fullmatch(r"[0-9a-f]{12,64}", identity) for identity in ids):
        raise RuntimeError("invalid Docker container listing")
    for identity in ids:
        removed = execute(["docker", "rm", "-f", identity], timeout=15)
        if removed.code:
            raise RuntimeError(removed.output)
    return ids
