import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harnesslab.api import create_app
from harnesslab.models import HarnessConfig, Task
from harnesslab.report import compare
from harnesslab.runner import validate_task, work
from harnesslab.sandbox import LocalSandbox, execute, safe_path
from harnesslab.store import LostLease, Store
from scripts.bootstrap_demo import bootstrap


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_task():
    return bootstrap(ROOT)


def test_boundaries(tmp_path):
    with pytest.raises(ValueError):
        LocalSandbox(tmp_path)
    for path in ["../escape", "/etc/passwd", ".git/config"]:
        with pytest.raises(ValueError):
            safe_path(tmp_path, path)
    (tmp_path / "link").symlink_to("/etc")
    with pytest.raises(ValueError):
        safe_path(tmp_path, "link/passwd")


def test_deadline_and_output():
    result = execute([sys.executable, "-c", "import time; print('started',flush=True); time.sleep(10)"], timeout=.1)
    assert result.timed_out and result.code == 124
    result = execute([sys.executable, "-c", "print('a'*100000)"], limit=100)
    assert len(result.output) < 150 and "[truncated]" in result.output


def test_independent_grader(fixture_task):
    result = validate_task(fixture_task, "local", True)
    assert result["valid"], result
    assert result["before"]["code"] != 0
    assert result["after"]["code"] == 0


def test_concurrent_claim_and_fencing(tmp_path, fixture_task):
    store = Store(str(tmp_path / "state.db"))
    exp = store.experiment("test")
    identity = store.enqueue(exp, fixture_task, HarnessConfig())
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda n: store.claim(str(n)), [1, 2]))
    assert sum(row is not None for row in claims) == 1
    first = next(row for row in claims if row)
    with store.connection(True) as db:
        db.execute("UPDATE runs SET lease=? WHERE id=?", (time.time()-1, identity))
    second = store.claim("replacement")
    assert second["attempt"] == 2
    assert not store.heartbeat(identity, first["owner"], 1)
    with pytest.raises(LostLease):
        store.finish(identity, first["owner"], 1, "solved", {})
    with pytest.raises(LostLease):
        store.event(identity, 1, "stale", {}, first["owner"])


@pytest.mark.parametrize("name,fault", [("baseline", None), ("resilient", "mcp_timeout"), ("resilient", "malformed_output")])
def test_complete_run(tmp_path, fixture_task, name, fault):
    store = Store(str(tmp_path / "state.db"))
    exp = store.experiment("test")
    identity = store.enqueue(exp, fixture_task, HarnessConfig(name=name))
    work(store, tmp_path / "artifacts", "local", True, once=True, fault=fault)
    row = store.get(identity)
    assert row["status"] == "solved", row
    events = store.events(identity)
    assert [e["seq"] for e in events] == list(range(1, len(events)+1))
    assert any(e["kind"] == "grading" for e in events)
    visible = next(e for e in events if e["kind"] == "tool_result" and e["data"]["name"] == "exec__run_tests")
    assert json.loads(visible["data"]["output"])["code"] == 0
    assert compare(store, exp)[0]["scripted_fixture"]
    if fault == "mcp_timeout":
        assert any(e["kind"] == "tool_timeout" for e in events)


def test_cancellation(tmp_path, fixture_task):
    store = Store(str(tmp_path / "state.db"))
    exp = store.experiment("cancel")
    identity = store.enqueue(exp, fixture_task, HarnessConfig())
    store.cancel(identity)
    assert store.claim("worker") is None
    assert store.get(identity)["status"] == "cancelled"


def test_api(tmp_path, fixture_task):
    client = TestClient(create_app(str(tmp_path / "state.db"), fixture_task.parent, tmp_path / "artifacts"))
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.post("/api/experiments", json={"name": "demo", "tasks": ["tag-normalization"], "configs": [{"name": "baseline"}]})
    assert response.status_code == 201, response.text
    exp = response.json()["id"]
    run = client.get(f"/api/experiments/{exp}").json()["runs"][0]
    assert client.post(f"/api/runs/{run['id']}/cancel").status_code == 202
    assert client.get(f"/api/runs/{run['id']}/stream").status_code == 200
    assert client.get("/api/runs/unknown").status_code == 404
    assert client.post("/api/experiments", json={"name": "bad", "tasks": ["../../etc/passwd"], "configs": [{}]}).status_code == 400


def test_paid_config_requires_prices():
    with pytest.raises(ValueError):
        HarnessConfig(provider="anthropic", model="example")


def test_atomic_budget(tmp_path, fixture_task):
    store = Store(str(tmp_path / "budget.db"))
    exp = store.experiment("limited", budget_usd=1)
    ids = [store.enqueue(exp, fixture_task, HarnessConfig()) for _ in range(2)]
    rows = [store.claim(str(n)) for n in range(2)]
    def reserve(row):
        return store.reserve(row["id"], row["owner"], row["attempt"], 0, .75)
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(reserve, rows))
    assert outcomes.count(True) == 1
    assert store.accounting(exp)["unsettled_reserved_usd"] == .75
    accepted = rows[outcomes.index(True)]
    store.settle(accepted["id"], 1, 0, .1)
    rejected = rows[outcomes.index(False)]
    assert reserve(rejected)
    assert store.accounting(exp)["actual_usd"] == .1


def test_token_budget_stops_before_model(tmp_path, fixture_task):
    from harnesslab.models import read_task
    task = read_task(fixture_task)
    task.limits.tokens = 1
    # Preserve relative repository/grading resolution by writing alongside the fixture.
    path = fixture_task.parent / "tiny-budget.json"
    path.write_text(task.model_dump_json())
    try:
        store = Store(str(tmp_path / "budget.db"))
        exp = store.experiment("budget")
        identity = store.enqueue(exp, path, HarnessConfig())
        work(store, tmp_path / "artifacts", "local", True, once=True)
        assert store.get(identity)["status"] == "budget_exceeded"
        assert not any(e["kind"] == "model_response" for e in store.events(identity))
    finally:
        path.unlink()


def test_running_cancellation_and_wall_deadline():
    from harnesslab.agent import AgentStopped, guarded
    async def check():
        with pytest.raises(AgentStopped) as cancelled:
            await guarded(asyncio.sleep(10), time.monotonic() + 10, lambda: True, {})
        assert cancelled.value.outcome == "cancelled"
        with pytest.raises(AgentStopped) as budget:
            await guarded(asyncio.sleep(10), time.monotonic() + .05, lambda: False, {})
        assert budget.value.outcome == "budget_exceeded"
    asyncio.run(check())


def test_ambiguous_call_keeps_reservation(tmp_path, fixture_task):
    store = Store(str(tmp_path / "ambiguous.db"))
    exp = store.experiment("uncertain")
    identity = store.enqueue(exp, fixture_task, HarnessConfig())
    row = store.claim("worker")
    assert store.reserve(identity, "worker", row["attempt"], 0, .4)
    store.finish(identity, "worker", row["attempt"], "infrastructure_error", {"error": "provider timed out"})
    assert store.accounting(exp) == {"actual_usd": 0, "unsettled_reserved_usd": .4, "unsettled_calls": 1}


def test_api_to_worker_to_patch(tmp_path, fixture_task):
    url = str(tmp_path / "flow.db")
    artifacts = tmp_path / "artifacts"
    client = TestClient(create_app(url, fixture_task.parent, artifacts))
    response = client.post("/api/experiments", json={"name": "full flow", "tasks": ["tag-normalization"], "configs": [{"name": "baseline"}, {"name": "resilient"}]})
    exp = response.json()["id"]
    work(Store(url), artifacts, "local", True, once=True)
    detail = client.get(f"/api/experiments/{exp}").json()
    assert all(row["status"] == "solved" for row in detail["runs"]), detail
    identity = detail["runs"][0]["id"]
    assert "+    return sorted({tag.strip()" in client.get(f"/api/runs/{identity}/patch").json()["patch"]
    assert "attempt_finished" in client.get(f"/api/runs/{identity}/stream").text
    exported = client.get(f"/api/experiments/{exp}/export").json()
    assert len(exported["runs"]) == 2
    assert exported["accounting"]["unsettled_calls"] == 0


def test_cleanup_is_scoped(monkeypatch):
    from harnesslab import sandbox
    calls = []
    def fake_execute(argv, **kwargs):
        calls.append(argv)
        return sandbox.Result(0, "a"*12 + "\n" if "ps" in argv else "")
    monkeypatch.setattr(sandbox, "execute", fake_execute)
    sandbox.cleanup_run_containers("b"*32)
    assert "label=harnesslab.run=" + "b"*32 in calls[0]
    assert calls[1] == ["docker", "rm", "-f", "a"*12]
    with pytest.raises(ValueError):
        sandbox.cleanup_run_containers("arbitrary-container")


def test_expired_cancelled_worker_is_reaped(tmp_path, fixture_task):
    store = Store(str(tmp_path / "reap.db"))
    exp = store.experiment("dead cancelled worker")
    identity = store.enqueue(exp, fixture_task, HarnessConfig())
    store.claim("dead", lease_seconds=.01)
    store.cancel(identity)
    time.sleep(.02)
    assert store.claim("replacement") is None
    assert store.get(identity)["status"] == "cancelled"


def test_report_groups_by_configuration_and_pairs_tasks(tmp_path, fixture_task):
    from harnesslab.report import paired_comparisons
    store = Store(str(tmp_path / "report.db"))
    exp = store.experiment("paired")
    for config, status in [(HarnessConfig(), "solved"), (HarnessConfig(), "unsolved"), (HarnessConfig(name="resilient"), "solved"), (HarnessConfig(name="resilient"), "solved"), (HarnessConfig(context_chars=2000), "unsolved")]:
        identity = store.enqueue(exp, fixture_task, config)
        row = store.claim("w")
        store.finish(identity, "w", row["attempt"], status, {"duration_seconds": 1})
    assert len(compare(store, exp)) == 3  # Same display name with different policy stays separate.
    pairs = paired_comparisons(store, exp)
    balanced = next(p for p in pairs if p["balanced_trials"])
    assert balanced["common_tasks"] == 1
    assert balanced["mean_task_success_difference"] == .5


def test_same_owner_can_renew_after_host_sleep(tmp_path, fixture_task):
    store = Store(str(tmp_path / "sleep.db"))
    exp = store.experiment("host sleep")
    identity = store.enqueue(exp, fixture_task, HarnessConfig())
    row = store.claim("owner", lease_seconds=.01)
    time.sleep(.02)
    assert store.heartbeat(identity, "owner", 1)
    assert store.claim("replacement") is None
    assert store.get(identity)["attempt"] == 1


def test_sse_reconnect_resumes_after_last_event_id(tmp_path,fixture_task):
    url=str(tmp_path/"resume.db")
    store=Store(url)
    exp=store.experiment("SSE resume")
    identity=store.enqueue(exp,fixture_task,HarnessConfig())
    row=store.claim("worker")
    store.event(identity,row["attempt"],"first",{},"worker")
    store.event(identity,row["attempt"],"second",{},"worker")
    store.finish(identity,"worker",row["attempt"],"solved",{})
    client=TestClient(create_app(url,fixture_task.parent,tmp_path/"artifacts"))
    response=client.get(f"/api/runs/{identity}/stream",headers={"Last-Event-ID":"1"})
    assert "id: 2\n" in response.text and "id: 1\n" not in response.text
    assert '"schema_version": 1' in response.text
