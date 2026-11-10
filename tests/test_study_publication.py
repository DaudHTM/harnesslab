import json
from pathlib import Path

import pytest

from harnesslab.models import HarnessConfig
from harnesslab.store import Store
from scripts.publish_study import publish


def test_publication_refuses_unfinished_jobs_and_keeps_infra_errors(tmp_path,monkeypatch):
    path=str(tmp_path/"state.db")
    monkeypatch.setenv("HARNESSLAB_DATABASE_URL",path)
    store=Store(path)
    identity=store.experiment("publication")
    metadata={"phase":"pilot","tasks":["task"],"repetitions":1,"backend":"test","configs":[HarnessConfig(provider="local",model="fixture-model").model_dump()],"seed":42}
    store.lock_study(identity,"test-source",metadata)
    run=store.enqueue(identity,Path("task.json"),HarnessConfig(provider="local",model="fixture-model"))
    with pytest.raises(ValueError,match="unfinished"):
        publish(identity,tmp_path/"reports")
    claim=store.claim("worker",experiment=identity)
    store.finish(run,"worker",claim["attempt"],"infrastructure_error",{"error":"test outage","duration_seconds":2})
    report=publish(identity,tmp_path/"reports")
    assert "infrastructure_error=1" in report.read_text()
    raw=json.loads(report.with_suffix('.json').read_text())
    assert raw['runs'][0]['result']['error']=='test outage'
    assert raw['comparison'][0]['valid_trials']==0


def test_regular_workers_do_not_take_frozen_study_jobs(tmp_path):
    store=Store(str(tmp_path/"scope.db"))
    study=store.experiment("controlled study")
    store.lock_study(study,"source",{})
    controlled=store.enqueue(study,Path("task.json"),HarnessConfig())
    regular=store.experiment("interactive experiment")
    interactive=store.enqueue(regular,Path("task.json"),HarnessConfig())
    assert store.claim("interactive-worker")["id"]==interactive
    assert store.claim("study-worker",experiment=study)["id"]==controlled
