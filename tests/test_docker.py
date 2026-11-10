"""Real Docker integration. No mocks, paid models, or host directory mounts."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from harnesslab.maintenance import reconcile
from harnesslab.models import HarnessConfig
from harnesslab.repository import checkout
from harnesslab.runner import grade, resolve_task, run_claimed
from harnesslab.sandbox import DockerSandbox, execute
from harnesslab.store import Store
from scripts.bootstrap_demo import bootstrap

pytestmark=pytest.mark.skipif(os.environ.get("HARNESSLAB_TEST_DOCKER")!="1",reason="set HARNESSLAB_TEST_DOCKER=1 with a live Docker engine and built task image")
ROOT=Path(__file__).resolve().parents[1]


def test_real_container_boundaries_and_fresh_grading(tmp_path,monkeypatch):
    task=resolve_task(bootstrap(ROOT))
    workspace=tmp_path/"workspace"
    checkout(task.repository,task.commit,workspace)
    monkeypatch.setenv("HARNESSLAB_MODEL_API_KEY","must-not-enter-container")
    with DockerSandbox(workspace,image=task.image) as sandbox:
        name=sandbox.name
        metadata=json.loads(execute(["docker","inspect",name]).output)[0]
        assert metadata["HostConfig"]["NetworkMode"]=="none"
        assert metadata["HostConfig"]["ReadonlyRootfs"]
        assert metadata["Config"]["User"]=="1000:1000"
        assert not any(m["Type"]=="bind" for m in metadata.get("Mounts",[]))
        assert metadata["HostConfig"]["Memory"]==512*1024*1024
        assert metadata["HostConfig"]["PidsLimit"]==128
        assert sandbox.command(["python","-c","import os; print('HARNESSLAB_MODEL_API_KEY' in os.environ)"]).output.strip()=="False"
        assert sandbox.command(["python","-c","open('/etc/should-not-write','w').write('x')"]).code!=0
        assert sandbox.command(["python","-c","import socket;socket.create_connection(('1.1.1.1',443),timeout=.2)"]).code!=0
        assert sandbox.command(["--privileged","sh","-c","touch /etc/should-not-write"]).code!=0
        with pytest.raises(ValueError):sandbox.read(".git/config")
        sandbox.write("normalizer.py","def normalize_tags(tags):\n    return sorted({t.strip().lower() for t in tags if t.strip()})\n")
        assert sandbox.command(task.visible_command).code==0
        patch=sandbox.patch()
    assert execute(["docker","inspect",name]).code!=0
    outcome,result=grade(task,patch,"docker")
    assert outcome=="solved",result


def test_hanging_container_command_is_stopped_and_removed(tmp_path):
    task=resolve_task(bootstrap(ROOT))
    workspace=tmp_path/"workspace"
    checkout(task.repository,task.commit,workspace)
    with DockerSandbox(workspace,image=task.image) as sandbox:
        name=sandbox.name
        result=sandbox.command(["python","-c","import time;time.sleep(60)"],timeout=.1)
        assert result.timed_out
        metadata=json.loads(execute(["docker","inspect",name]).output)[0]
        assert not metadata["State"]["Running"]
    assert execute(["docker","inspect",name]).code!=0


def test_killed_worker_orphan_is_removed_by_replacement(tmp_path):
    task_path=bootstrap(ROOT)
    task=resolve_task(task_path)
    workspace=tmp_path/"workspace"
    checkout(task.repository,task.commit,workspace)
    store=Store(str(tmp_path/"crash.db"))
    exp=store.experiment("real container orphan")
    identity=store.enqueue(exp,task_path,HarnessConfig())
    script="from pathlib import Path; import os,sys; from harnesslab.store import Store; from harnesslab.sandbox import DockerSandbox; s=Store(sys.argv[1]); r=s.claim('doomed',lease_seconds=.1); box=DockerSandbox(Path(sys.argv[2]),image=sys.argv[3],run_id=r['id']); box.__enter__(); print(box.name,flush=True); os._exit(77)"
    proc=subprocess.run([sys.executable,"-c",script,store.url,str(workspace),task.image],cwd=ROOT,capture_output=True,text=True,timeout=60)
    assert proc.returncode==77,proc.stderr
    name=proc.stdout.strip().splitlines()[-1]
    try:
        assert execute(["docker","inspect",name]).code==0
        time.sleep(.15)
        replacement=store.claim("replacement")
        assert replacement["attempt"]==2
        run_claimed(store,replacement,tmp_path/"artifacts","docker")
        assert store.get(identity)["status"]=="solved",store.get(identity)
        assert execute(["docker","inspect",name]).code!=0
        assert any(e["kind"]=="orphan_cleanup" and e["data"]["containers"] for e in store.events(identity))
    finally:
        execute(["docker","rm","-f",name])


def test_terminal_orphan_is_swept_without_replacement(tmp_path):
    task=resolve_task(bootstrap(ROOT))
    workspace=tmp_path/"workspace"
    checkout(task.repository,task.commit,workspace)
    store=Store(str(tmp_path/"terminal.db"))
    exp=store.experiment("terminal orphan")
    identity=store.enqueue(exp,ROOT/"benchmarks/tasks/tag-normalization.json",HarnessConfig())
    row=store.claim("worker")
    box=DockerSandbox(workspace,image=task.image,run_id=identity)
    box.__enter__()
    try:
        store.finish(identity,"worker",row["attempt"],"infrastructure_error",{"error":"simulated worker shutdown"})
        removed=reconcile(store,apply=True)
        assert any(r.get("run_id")==identity and r["action"]=="removed" for r in removed)
        assert execute(["docker","inspect",box.name]).code!=0
    finally:
        box.__exit__()


def test_agent_command_timeout_preserves_unsolved_outcome(tmp_path,monkeypatch):
    from harnesslab import runner
    from harnesslab.providers import Reply
    class HangingProvider:
        async def reply(self,*args):
            return Reply(calls=[{"id":"hang","name":"exec__run_command","arguments":{"argv":["python","-c","import time;time.sleep(60)"]}}],input_tokens=1,output_tokens=1)
    monkeypatch.setattr(runner,"provider_for",lambda config:HangingProvider())
    path=bootstrap(ROOT)
    # Resolve the fixture's relative paths before saving a temporary manifest.
    resolved=resolve_task(path).model_dump()
    resolved["limits"]["command_seconds"]=.1
    manifest=tmp_path/"task.json"
    manifest.write_text(json.dumps(resolved))
    store=Store(str(tmp_path/"timeout.db"))
    exp=store.experiment("command timeout")
    identity=store.enqueue(exp,manifest,HarnessConfig())
    row=store.claim("worker")
    runner.run_claimed(store,row,tmp_path/"artifacts","docker")
    assert store.get(identity)["status"]=="unsolved",store.get(identity)
    kinds=[e["kind"] for e in store.events(identity)]
    assert "execution_stopped" in kinds and "patch_unavailable" in kinds
