from types import SimpleNamespace

import pytest

from scripts import run_study


def test_external_power_gate_recognizes_ac_and_battery(monkeypatch):
    monkeypatch.setattr(run_study.platform,"system",lambda:"Darwin")
    monkeypatch.setattr(run_study.subprocess,"run",lambda *a,**kw:SimpleNamespace(stdout="Now drawing from 'Battery Power'\n"))
    assert not run_study.external_power()
    monkeypatch.setattr(run_study.subprocess,"run",lambda *a,**kw:SimpleNamespace(stdout="Now drawing from 'AC Power'\n"))
    assert run_study.external_power()


def test_power_wait_starts_no_work_until_ac(monkeypatch,capsys):
    states=iter([False,False,True])
    sleeps=[]
    monkeypatch.setattr(run_study,"external_power",lambda:next(states))
    monkeypatch.setattr(run_study.time,"sleep",lambda duration:sleeps.append(duration))
    run_study.wait_for_power()
    assert sleeps==[15]
    output=capsys.readouterr().out
    assert "WAITING_FOR_POWER" in output and "EXTERNAL_POWER_READY" in output


def test_held_out_gates_before_creating_database_jobs(monkeypatch):
    def wait():raise RuntimeError("waiting for power")
    monkeypatch.setattr(run_study,"wait_for_power",wait)
    monkeypatch.setattr(run_study,"Store",lambda *a,**kw:pytest.fail("created jobs before power gate"))
    with pytest.raises(RuntimeError,match="waiting for power"):
        run_study.main("held-out","macos")


def test_model_preflight_cannot_contact_remote_paid_endpoint(monkeypatch):
    monkeypatch.setenv("HARNESSLAB_LOCAL_MODEL_URL","https://api.example.com/v1")
    monkeypatch.setattr(run_study.httpx,"get",lambda *a,**kw:pytest.fail("contacted remote endpoint"))
    with pytest.raises(ValueError,match="loopback"):
        run_study.model_ready()
