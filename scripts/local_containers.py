"""Optional free Docker test engine on macOS: project-local tools, private VM.

No Docker Desktop account, global Docker-context changes, or home-directory
mounts. VM startup waits for external power when requested.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.local_model import download
from scripts.run_study import wait_for_power
BASE=ROOT/".harnesslab/containers"
LIMA_VERSION="2.3.0"
LIMA_SHA="b7af444bd8f91d3c307477e562f2cf3bd7595d62b9429185e4fa841563578cfc"
DOCKER_VERSION="29.9.3"
DOCKER_SHA="79145e169bca0b9571d02de8e1cd311a36e0e8fdb4599b6661a87b1bb3afbe13"
COMPOSE_VERSION="5.7.0"
COMPOSE_SHA="54495ff81dd8cae11861455f0308a293a530149beba8f1d90ff3f295b11cf035"
INSTANCE="harnesslab"
LIMA_HOME=Path(f"/tmp/harnesslab-lima-{os.getuid()}")


def environment():
    env=dict(os.environ)
    env["PATH"]=str(BASE/"lima/bin")+":"+str(BASE/"docker-cli/docker")+":"+env.get("PATH","/usr/bin:/bin")
    env["LIMA_HOME"]=str(LIMA_HOME)
    env["DOCKER_HOST"]="unix://"+str(LIMA_HOME/INSTANCE/"sock/docker.sock")
    env["DOCKER_CONFIG"]=str(BASE/"docker-config")
    env["HARNESSLAB_DOCKER_SOCKET"]=f"/run/user/{os.getuid()}/docker.sock"
    env.pop("DOCKER_CONTEXT",None)
    return env


def setup():
    if (platform.system(),platform.machine())!=("Darwin","arm64"):
        raise RuntimeError("This optional engine setup targets Apple Silicon; use an existing Docker engine on other hosts.")
    BASE.mkdir(parents=True,exist_ok=True)
    for name,url,digest,destination in [
        ("lima-2.3.0.tar.gz",f"https://github.com/lima-vm/lima/releases/download/v{LIMA_VERSION}/lima-{LIMA_VERSION}-Darwin-arm64.tar.gz",LIMA_SHA,"lima"),
        ("docker-29.9.3.tgz",f"https://download.docker.com/mac/static/stable/aarch64/docker-{DOCKER_VERSION}.tgz",DOCKER_SHA,"docker-cli")]:
        archive=BASE/name
        download(url,archive,digest)
        target=BASE/destination
        if not target.exists():
            target.mkdir()
            with tarfile.open(archive) as tar:tar.extractall(target,filter="data")
    config=BASE/"docker-config"
    config.mkdir(mode=0o700,exist_ok=True)
    config.chmod(0o700)
    plugin=config/"cli-plugins/docker-compose"
    download(f"https://github.com/docker/compose/releases/download/v{COMPOSE_VERSION}/docker-compose-darwin-aarch64",plugin,COMPOSE_SHA)
    plugin.chmod(0o755)
    (BASE/"provenance.json").write_text(json.dumps({"lima_version":LIMA_VERSION,"lima_archive_sha256":LIMA_SHA,
        "docker_cli_version":DOCKER_VERSION,"docker_cli_sha256":DOCKER_SHA,"compose_version":COMPOSE_VERSION,"compose_sha256":COMPOSE_SHA,
        "mount_home":False,"cpus":2,"memory_gib":2,"disk_gib":8},indent=2)+"\n")
    subprocess.run([str(BASE/"lima/bin/limactl"),"--version"],env=environment(),check=True)
    print("Container tools ready. Start with --wait-for-power before VM boot.",flush=True)


def start_command():
    return [str(BASE/"lima/bin/limactl"),"start","--name="+INSTANCE,"--vm-type=vz","--cpus=2","--memory=2","--disk=8","--mount-none","--tty=false","template:docker"]


def start(require_power=False):
    if require_power:wait_for_power()
    if not (BASE/"lima/bin/limactl").is_file():
        raise RuntimeError("run setup first")
    if LIMA_HOME.exists() and (not LIMA_HOME.is_dir() or LIMA_HOME.stat().st_uid!=os.getuid()):
        raise RuntimeError("private VM directory is not owned by this user")
    LIMA_HOME.mkdir(mode=0o700,exist_ok=True)
    LIMA_HOME.chmod(0o700)
    subprocess.run(start_command(),env=environment(),check=True)
    subprocess.run(["docker","version"],env=environment(),check=True)
    print("PRIVATE_DOCKER_READY",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["setup","start","stop","env"])
    parser.add_argument("--wait-for-power",action="store_true")
    parser.add_argument("--verify",action="store_true",help="After startup, build the task image and run real Docker integration tests.")
    args=parser.parse_args()
    if args.action=="setup":setup()
    elif args.action=="start":
        start(args.wait_for_power)
        if args.verify:
            env=environment()
            subprocess.run(["docker","build","-f","docker/task.Dockerfile","-t","harnesslab-task:local","."],cwd=ROOT,env=env,check=True)
            env["HARNESSLAB_TEST_DOCKER"]="1"
            subprocess.run([sys.executable,"-m","pytest","tests/test_docker.py","-q","--junitxml=docs/evidence/docker.xml"],cwd=ROOT,env=env,check=True)
    elif args.action=="stop":subprocess.run([str(BASE/"lima/bin/limactl"),"stop",INSTANCE],env=environment(),check=True)
    else:
        import shlex
        for key in ["PATH","LIMA_HOME","DOCKER_HOST","DOCKER_CONFIG","HARNESSLAB_DOCKER_SOCKET"]:
            print("export "+key+"="+shlex.quote(environment()[key]))
