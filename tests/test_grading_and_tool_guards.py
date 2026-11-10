import asyncio
import json
import platform
import shutil
import sys
import time
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from harnesslab import agent
from harnesslab.errors import error_details
from harnesslab.mcp_tools import servers
from harnesslab.models import HarnessConfig
from harnesslab.providers import FakeProvider
from harnesslab.repository import apply_patch, checkout
from harnesslab.runner import grade, resolve_task
from harnesslab.sandbox import LocalSandbox
from harnesslab.store import Store
from harnesslab.report import compare
from scripts.bootstrap_demo import bootstrap

ROOT=Path(__file__).resolve().parents[1]


def test_large_truncation_is_rejected_but_context_edit_succeeds(tmp_path):
    target=tmp_path/"module.py"
    original="# preserve surrounding module\n"*100+"value = 1\n"
    target.write_text(original)
    task=resolve_task(bootstrap(ROOT))
    async def check():
        with LocalSandbox(tmp_path,allow_unsafe=True) as sandbox:
            async with Client(servers(sandbox,task)["repo"]) as client:
                rejected=await client.call_tool("write_file",{"path":"module.py","content":"value = 2\n"})
                assert rejected.is_error and "ENTIRE file" in str(rejected)
                assert target.read_text()==original
                edited=await client.call_tool("replace_text",{"path":"module.py","old":"value = 1","new":"value = 2"})
                assert not edited.is_error
                assert target.read_text()==original.replace("value = 1","value = 2")
    asyncio.run(check())


@pytest.mark.parametrize("patch",[
    'diff --git "a/tests/x.py" "b/tests/x.py"\n--- "a/tests/x.py"\n+++ "b/tests/x.py"\n@@ -1 +1 @@\n-old\n+new\n',
    'diff --git a/pyproject.toml b/pyproject.toml\nold mode 100644\nnew mode 100755\n',
    'diff --git a/tests/x.py b/lib/x.py\nsimilarity index 100%\nrename from tests/x.py\nrename to lib/x.py\n',
    'diff --git a/test_root.py b/test_root.py\n--- a/test_root.py\n+++ b/test_root.py\n@@ -1 +1 @@\n-old\n+new\n',
])
def test_protected_patch_paths_use_git_parsing(tmp_path,patch):
    task=resolve_task(bootstrap(ROOT))
    workspace=tmp_path/"workspace"
    checkout(task.repository,task.commit,workspace)
    with pytest.raises(ValueError,match="protected"):
        apply_patch(workspace,patch)


def test_candidate_cannot_shadow_pytest_to_skip_grading(tmp_path):
    task=resolve_task(bootstrap(ROOT))
    grading=tmp_path/"grading"
    grading.mkdir()
    # Exercise the actual generated runner, not a test-only reimplementation.
    shutil.copy(ROOT/"benchmarks/grading/boltons-split-iter/run.py",grading/"run.py")
    (grading/"pytest.ini").write_text("[pytest]\n")
    (grading/"test_hidden.py").write_text("from normalizer import normalize_tags\ndef test_trim():\n    assert normalize_tags([' X ']) == ['x']\n")
    (grading/"test_upstream.py").write_text("from normalizer import normalize_tags\ndef test_original():\n    assert normalize_tags(['X']) == ['x']\n")
    task.grading_dir=str(grading)
    task.grade_command=["python","-I","/grading/run.py"]
    candidate="diff --git a/pytest.py b/pytest.py\nnew file mode 100644\n--- /dev/null\n+++ b/pytest.py\n@@ -0,0 +1,2 @@\n+def main(*args, **kwargs):\n+    return 0\n"
    backend="macos" if platform.system()=="Darwin" else "local"
    outcome,result=grade(task,candidate,backend,allow_unsafe=True)
    assert outcome=="unsolved" and result["code"]!=0
    assert "test_trim" in result["output"]


def test_harness_deadline_covers_silent_mcp_startup(tmp_path,monkeypatch):
    original=StdioServerParameters
    monkeypatch.setattr(agent,"StdioServerParameters",lambda **kw:original(command=sys.executable,args=["-c","import time;time.sleep(30)"]))
    task=resolve_task(bootstrap(ROOT))
    task.limits.wall_seconds=.15
    started=time.monotonic()
    with LocalSandbox(tmp_path,allow_unsafe=True) as sandbox:
        with pytest.raises(agent.AgentStopped) as stopped:
            asyncio.run(agent.run_agent(sandbox,task,HarnessConfig(),FakeProvider(),lambda *args:None,lambda:False))
    assert stopped.value.outcome=="budget_exceeded"
    assert time.monotonic()-started<10  # Includes bounded child-process cleanup.


def test_nested_error_diagnostics_keep_root_cause():
    grouped=ExceptionGroup("SDK wrapper",[ExceptionGroup("nested",[ConnectionError("tool process exited")])])
    assert error_details(grouped)==[{"type":"ConnectionError","message":"tool process exited"}]


def test_comparison_uses_ledger_without_loading_large_traces(tmp_path,monkeypatch):
    store=Store(str(tmp_path/"ledger.db"))
    exp=store.experiment("fast reporting")
    identity=store.enqueue(exp,ROOT/"benchmarks/tasks/tag-normalization.json",HarnessConfig())
    row=store.claim("worker")
    assert store.reserve(identity,"worker",row["attempt"],0,.1)
    store.settle(identity,1,0,.03)
    store.finish(identity,"worker",1,"solved",{"duration_seconds":1})
    monkeypatch.setattr(store,"events",lambda *args:pytest.fail("comparison loaded the trace instead of the ledger"))
    assert compare(store,exp)[0]["cost_usd"]==.03


def test_timeout_state_survives_tool_output_truncation(tmp_path,monkeypatch):
    from harnesslab.providers import Reply
    class Provider:
        async def reply(self,*args):
            return Reply(calls=[{"id":"timeout","name":"exec__run_command","arguments":{"argv":["ignored"]}}])
    async def timed_out(self,*args):
        return json.dumps({"code":124,"output":"x"*20000,"timed_out":True})
    monkeypatch.setattr(agent.ToolRouter,"call",timed_out)
    task=resolve_task(bootstrap(ROOT))
    events=[]
    with LocalSandbox(tmp_path,allow_unsafe=True) as sandbox:
        with pytest.raises(agent.AgentStopped) as stopped:
            asyncio.run(agent.run_agent(sandbox,task,HarnessConfig(mcp_transport="in-process"),Provider(),lambda k,d:events.append((k,d)),lambda:False))
    assert stopped.value.outcome=="unsolved"
    assert any(kind=="execution_stopped" for kind,_ in events)
