import asyncio
import json
import platform
import sys
from pathlib import Path

import httpx
import pytest

from harnesslab.models import HarnessConfig
from harnesslab.providers import LocalProvider
from harnesslab.runner import work
from harnesslab.sandbox import MacOSSandbox
from harnesslab.store import Store
from scripts.bootstrap_demo import bootstrap


@pytest.mark.skipif(platform.system() != "Darwin", reason="native macOS isolation")
def test_native_boundaries(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("boundary sentinel")
    with MacOSSandbox(workspace) as sandbox:
        assert sandbox.write("answer.py", "print(42)\n") == "written"
        assert sandbox.command(["python", "answer.py"]).output.strip() == "42"
        assert sandbox.read("answer.py") == "print(42)\n"
        for code in [f"from pathlib import Path; print(Path({str(outside)!r}).read_text())",
                     f"from pathlib import Path; Path({str(outside)!r}).write_text('changed')",
                     "import socket; socket.create_connection(('127.0.0.1',8000),timeout=1)"]:
            result = sandbox.command(["python", "-c", code])
            assert result.code != 0 and "Operation not permitted" in result.output
    assert outside.read_text() == "boundary sentinel"


@pytest.mark.skipif(platform.system() != "Darwin", reason="native macOS isolation")
def test_native_stdio_run(tmp_path):
    root = Path(__file__).resolve().parents[1]
    task = bootstrap(root)
    store = Store(str(tmp_path / "native.db"))
    exp = store.experiment("native stdio")
    identity = store.enqueue(exp, task, HarnessConfig())
    work(store, tmp_path / "artifacts", "macos", once=True)
    assert store.get(identity)["status"] == "solved"


def test_local_provider_has_no_key_requirement(monkeypatch):
    original = httpx.AsyncClient
    def respond(request):
        assert request.url.host == "127.0.0.1"
        assert "authorization" not in request.headers
        payload = json.loads(request.content)
        assert payload["temperature"] == .2 and payload["seed"] == 42
        return httpx.Response(200, json={"choices": [{"message": {"content": "done"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    config = HarnessConfig(provider="local", model="local-model")
    reply = asyncio.run(LocalProvider().reply([{"role": "user", "content": "hello"}], [], config))
    assert reply.text == "done" and reply.input_tokens == 2


def test_local_provider_rejects_remote_endpoint(monkeypatch):
    monkeypatch.setenv("HARNESSLAB_LOCAL_MODEL_URL", "https://api.example.com/v1")
    with pytest.raises(ValueError, match="loopback"):
        asyncio.run(LocalProvider().reply([], [], HarnessConfig(provider="local", model="x")))


def test_resilient_rejects_unwritten_fix(tmp_path):
    import subprocess
    from harnesslab.agent import run_agent
    from harnesslab.providers import Reply
    from harnesslab.runner import resolve_task
    from harnesslab.sandbox import LocalSandbox
    from harnesslab.repository import checkout
    root = Path(__file__).resolve().parents[1]
    task = resolve_task(bootstrap(root))
    workspace = tmp_path / "workspace"
    checkout(task.repository, task.commit, workspace)
    class PretendProvider:
        async def reply(self, *args):
            return Reply(text="I implemented the fix.", input_tokens=1, output_tokens=1)
    events = []
    with LocalSandbox(workspace, allow_unsafe=True) as sandbox:
        result, _ = asyncio.run(run_agent(sandbox, task, HarnessConfig(name="resilient", mcp_transport="in-process"),
            PretendProvider(), lambda kind,data: events.append((kind,data)), lambda: False))
    assert result == "unsolved"
    assert len([e for e in events if e[0] == "completion_rejected"]) == 3
