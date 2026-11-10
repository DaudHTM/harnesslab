"""Continue verification and the free study after the existing engine waiter.

Stops on failed/missing Docker evidence or a failed Compose check. Run logs are
kept by the caller; each study also writes its own resumable checkpoint.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_study import wait_for_power


def main(engine_pid):
    observed_at = time.time()
    while True:
        process = subprocess.run(
            ["ps", "-p", str(engine_pid), "-o", "command="],
            capture_output=True, text=True, check=False,
        )
        if process.returncode != 0:
            break
        if "scripts/local_containers.py start" not in process.stdout:
            raise RuntimeError("engine process identity changed; refusing to continue")
        time.sleep(15)
    evidence = ROOT / "docs/evidence/docker.xml"
    if not evidence.exists() or evidence.stat().st_mtime < observed_at:
        raise RuntimeError("engine verification did not produce fresh Docker evidence")
    suites = ET.parse(evidence).getroot().findall("testsuite")
    if (sum(int(s.get("tests", 0)) for s in suites) < 5 or
            any(int(s.get(k, 0)) for s in suites for k in ["errors", "failures", "skipped"])):
        raise RuntimeError("Docker verification did not pass all required checks")
    wait_for_power()
    subprocess.run([sys.executable, "scripts/verify_compose.py", "--private-engine"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/local_containers.py", "stop"], cwd=ROOT, check=True)
    subprocess.run([
        sys.executable, "scripts/run_study.py", "pilot", "--backend", "macos",
        "--wait-for-power", "--then-held-out",
    ], cwd=ROOT, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-engine-pid", type=int, required=True)
    args = parser.parse_args()
    if args.after_engine_pid <= 1 or args.after_engine_pid == os.getpid():
        parser.error("expected the existing engine waiter PID")
    main(args.after_engine_pid)
