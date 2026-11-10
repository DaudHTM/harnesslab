"""Deterministic failure scenarios. These measure infrastructure, not AI skill."""
import asyncio
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from harnesslab.agent import run_agent
from harnesslab.models import HarnessConfig
from harnesslab.providers import FakeProvider
from harnesslab.repository import checkout
from harnesslab.runner import resolve_task, run_claimed
from harnesslab.sandbox import LocalSandbox, execute
from harnesslab.store import Store
from scripts.bootstrap_demo import bootstrap

ROOT = Path(__file__).resolve().parents[1]


def test_worker_process_crash_and_recovery(tmp_path):
    task = bootstrap(ROOT)
    url = str(tmp_path / "crash.db")
    store = Store(url)
    exp = store.experiment("worker crash scenario")
    identity = store.enqueue(exp, task, HarnessConfig())
    script = "from harnesslab.store import Store; import os,sys; s=Store(sys.argv[1]); r=s.claim('doomed',lease_seconds=.2); s.event(r['id'],r['attempt'],'fault_injected',{'scenario':'worker_crash'},'doomed'); os._exit(77)"
    proc = subprocess.run([sys.executable, "-c", script, url], cwd=ROOT, timeout=10, capture_output=True)
    assert proc.returncode == 77
    assert store.get(identity)["status"] == "running"
    time.sleep(.25)
    row = store.claim("replacement")
    assert row["attempt"] == 2
    backend = "macos" if platform.system() == "Darwin" else "local"
    run_claimed(store, row, tmp_path / "artifacts", backend, allow_unsafe=True)
    assert store.get(identity)["status"] == "solved"
    assert any(e["kind"] == "attempt_interrupted" for e in store.events(identity))


def test_hanging_command_is_killed():
    started = time.monotonic()
    result = execute([sys.executable, "-c", "import time; time.sleep(60)"], timeout=.1)
    assert result.code == 124 and result.timed_out
    assert time.monotonic() - started < 3


def test_provider_rate_limit_retry_is_bounded(tmp_path):
    task = resolve_task(bootstrap(ROOT))
    workspace = tmp_path / "workspace"
    checkout(task.repository, task.commit, workspace)
    class LimitedProvider(FakeProvider):
        limited = False
        async def reply(self, *args):
            if not self.limited:
                self.limited = True
                request = httpx.Request("POST", "http://127.0.0.1/model")
                response = httpx.Response(429, request=request, headers={"retry-after": "0"})
                raise httpx.HTTPStatusError("injected rate limit", request=request, response=response)
            return await super().reply(*args)
    events, settled = [], []
    with LocalSandbox(workspace, allow_unsafe=True) as sandbox:
        outcome, totals = asyncio.run(run_agent(sandbox, task, HarnessConfig(name="resilient", mcp_transport="in-process"), LimitedProvider(),
            lambda k,d: events.append((k,d)), lambda: False, settle=lambda step,cost: settled.append((step,cost))))
    assert outcome is None
    assert len([e for e in events if e[0] == "provider_rate_limit"]) == 1
    assert settled[0] == (0, 0)
    assert totals["input_tokens"] == 120


def test_mcp_rejects_injected_path_escape(tmp_path):
    from mcp import Client
    from harnesslab.mcp_tools import servers
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "private.txt").write_text("do not disclose this sentinel")
    task = resolve_task(bootstrap(ROOT))
    async def check():
        with LocalSandbox(workspace, allow_unsafe=True) as sandbox:
            async with Client(servers(sandbox, task)["repo"]) as client:
                result = await client.call_tool("read_file", {"path": "../private.txt"})
                assert result.is_error
                assert "do not disclose this sentinel" not in str(result)
                assert "path must stay inside workspace" in str(result)
    asyncio.run(check())


def test_sdk_cancellation_group_preserves_outcome():
    from harnesslab.agent import AgentStopped, _find_stopped
    stopped = AgentStopped("cancelled", {"input_tokens": 7})
    grouped = ExceptionGroup("SDK cleanup", [ExceptionGroup("nested", [stopped])])
    assert _find_stopped(grouped) is stopped


def test_live_cancellation_unwinds_stdio_without_infrastructure_error(tmp_path, monkeypatch):
    import threading
    from harnesslab import runner
    started = threading.Event()
    class WaitingProvider:
        async def reply(self, *args):
            started.set()
            await asyncio.sleep(30)
    monkeypatch.setattr(runner, "provider_for", lambda config: WaitingProvider())
    task = bootstrap(ROOT)
    store = Store(str(tmp_path / "cancel-live.db"))
    exp = store.experiment("live cancellation")
    identity = store.enqueue(exp, task, HarnessConfig())
    row = store.claim("worker")
    backend = "macos" if platform.system() == "Darwin" else "local"
    thread = threading.Thread(target=runner.run_claimed, args=(store,row,tmp_path / "artifacts",backend,True))
    thread.start()
    assert started.wait(10)
    store.cancel(identity)
    thread.join(10)
    assert not thread.is_alive()
    assert store.get(identity)["status"] == "cancelled", store.get(identity)
