"""Build PostgreSQL in the workspace and run a private Unix-socket test server."""
import argparse
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from local_model import download

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".harnesslab/postgres"
VERSION = "17.11"
SOURCE_SHA = "dd27f2b3c59e73ed14aa3324901242bf69a032a6347805f274e6260322d42979"
PREFIX = BASE / "install"
DATA = BASE / "data"
# PostgreSQL's socket path has a platform length limit. Do not place it under
# the long project path; use a fixed private per-user directory in /tmp.
SOCKET = Path(f"/tmp/harnesslab-pg-{os.getuid()}")


def setup():
    archive = BASE / f"postgresql-{VERSION}.tar.bz2"
    download(f"https://ftp.postgresql.org/pub/source/v{VERSION}/{archive.name}", archive, SOURCE_SHA)
    source = BASE / f"postgresql-{VERSION}"
    if not source.exists():
        with tarfile.open(archive) as tar:
            tar.extractall(BASE, filter="data")
    if not (PREFIX / "bin/postgres").is_file():
        with (BASE / "build.log").open("a") as log:
            for command in [["./configure", f"--prefix={PREFIX}", "--without-icu", "--without-readline", "--without-zlib"], ["make", "-j2"], ["make", "install"]]:
                print("Building:", command[0], flush=True)
                subprocess.run(command, cwd=source, check=True, stdout=log, stderr=subprocess.STDOUT)
    (BASE / "provenance.json").write_text(json.dumps({"version": VERSION, "source_sha256": SOURCE_SHA, "source": f"https://ftp.postgresql.org/pub/source/v{VERSION}/"}, indent=2)+"\n")
    if not DATA.exists():
        subprocess.run([str(PREFIX / "bin/initdb"), "-D", str(DATA), "--auth=trust", "--username=harnesslab", "--no-locale", "--encoding=UTF8"], check=True)
    print("Ready. Run scripts/local_postgres.py start", flush=True)


def start():
    if SOCKET.exists() and (not SOCKET.is_dir() or SOCKET.stat().st_uid != os.getuid()):
        raise RuntimeError("socket directory is not owned by the current user")
    SOCKET.mkdir(mode=0o700, exist_ok=True)
    SOCKET.chmod(0o700)
    # No TCP listener and no changes to any system PostgreSQL installation.
    subprocess.run([str(PREFIX / "bin/pg_ctl"), "-D", str(DATA), "-l", str(BASE / "server.log"),
                    "-o", f"-k {SOCKET} -p 55432 -c listen_addresses=''", "-w", "start"], check=True)
    print(f"HARNESSLAB_TEST_POSTGRES_URL=postgresql://harnesslab@/postgres?host={SOCKET}&port=55432", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "start", "stop"])
    args = parser.parse_args()
    if args.action == "setup":
        setup()
    elif args.action == "start":
        start()
    else:
        subprocess.run([str(PREFIX / "bin/pg_ctl"), "-D", str(DATA), "-m", "fast", "-w", "stop"], check=True)
