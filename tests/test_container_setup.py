import importlib.util
import sys
from pathlib import Path

from harnesslab.sandbox import command_environment
from scripts.local_containers import start_command
from harnesslab import agent
from harnesslab.models import HarnessConfig
from harnesslab.providers import FakeProvider
from harnesslab.runner import resolve_task
from harnesslab.sandbox import LocalSandbox
from scripts.bootstrap_demo import bootstrap
import asyncio
import pytest


def test_trusted_docker_connection_is_preserved_without_model_keys(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST","unix:///tmp/private-engine.sock")
    monkeypatch.setenv("HARNESSLAB_MODEL_API_KEY","sentinel-model-key")
    env=command_environment(["docker","inspect","container"])
    assert env["DOCKER_HOST"]=="unix:///tmp/private-engine.sock"
    assert "HARNESSLAB_MODEL_API_KEY" not in env
    assert "DOCKER_HOST" not in command_environment(["python","candidate.py"])


def test_private_vm_never_mounts_home():
    command=start_command()
    assert "--mount-none" in command
    assert "--vm-type=vz" in command
    assert "--memory=2" in command and "--cpus=2" in command


def test_docker_mcp_processes_receive_only_trusted_connection_variables(tmp_path,monkeypatch):
    monkeypatch.setenv("DOCKER_HOST","unix:///tmp/private-engine.sock")
    monkeypatch.setenv("HARNESSLAB_MODEL_API_KEY","sentinel-key")
    captured=[]
    def capture(**kwargs):
        captured.append(kwargs)
        raise RuntimeError("captured configuration")
    monkeypatch.setattr(agent,"StdioServerParameters",capture)
    task=resolve_task(bootstrap(Path(__file__).resolve().parents[1]))
    with LocalSandbox(tmp_path,allow_unsafe=True) as sandbox:
        sandbox.name="owned-container"
        with pytest.raises(RuntimeError,match="captured"):
            asyncio.run(agent.run_agent(sandbox,task,HarnessConfig(),FakeProvider(),lambda *a:None,lambda:False))
    assert captured[0]["env"]["DOCKER_HOST"]=="unix:///tmp/private-engine.sock"
    assert "HARNESSLAB_MODEL_API_KEY" not in captured[0]["env"]
