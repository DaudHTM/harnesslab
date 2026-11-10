"""Record real CLI output as a three-minute asciinema walkthrough.

Reading pauses are intentional. Model case steps replay saved evidence and do
not make new inference calls. Browser access is not needed for this recording.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def record(duration=180):
    backend = "macos" if platform.system() == "Darwin" else "docker"
    py = str(ROOT / ".venv/bin/python")
    cli = [py, "-m", "harnesslab.cli"]
    task = "benchmarks/tasks/tag-normalization.json"
    case_code = "import json,sys; from pathlib import Path; d=json.loads(Path(sys.argv[1]).read_text()); r=d['runs'][0]; print('Provider:',r['config']['provider']); print('Outcome:',r['status']); print('Usage:',r['result']); print('Tool calls:',[e['data']['name'] for e in r['events'] if e['kind']=='tool_call']); print('Completion feedback:',[e['data'] for e in r['events'] if e['kind']=='completion_rejected'])"
    corpus_code = "import json; from pathlib import Path; d=json.loads(Path('benchmarks/validation.json').read_text()); print('Validated base/reference pairs:',d['validated'],'/',d['total']); print('Backend:',d['backend']); c=json.loads(Path('benchmarks/catalog.json').read_text()); print('Development:',sum(t['split']=='development' for t in c['tasks'])); print('Held-out:',sum(t['split']=='held-out' for t in c['tasks'])); print('Study: 20 tasks x 2 configurations x 3 fixed-seed repetitions; no provider API fees.')"
    steps = [
        ("1. Validate independently: the broken base fails; the gold patch passes.", cli+["tasks","validate",task,"--backend",backend]),
        ("2. Exercise the MCP execution pipeline with an explicitly scripted fixture.", cli+["run",task,"--backend",backend]),
        ("3. Inject a read timeout. The resilient harness retries the read once.", cli+["run",task,"--backend",backend,"--config","resilient","--fault","mcp_timeout"]),
        ("4. Replay real local-model evidence: a claimed fix with an empty patch failed hidden tests.", [py,"-c",case_code,"docs/evidence/empty-patch-baseline.json"]),
        ("5. Replay the follow-up: empty-patch feedback led to an applied fix and passing hidden tests.", [py,"-c",case_code,"docs/evidence/empty-patch-feedback.json"]),
        ("6. Inspect the corpus. Synthetic regressions are labeled; held-out results are separate.", [py,"-c",corpus_code]),
    ]
    target = ROOT / "docs/evidence/demo.cast"
    started = time.monotonic()
    with target.open("w") as cast:
        cast.write(json.dumps({"version":2,"width":110,"height":36,"timestamp":int(time.time()),"title":"HarnessLab: independent grading, MCP recovery, and free local inference","env":{"TERM":"xterm-256color"}})+"\n")
        def emit(text):
            clean = text.replace(str(ROOT), "${PROJECT_ROOT}").replace("\n", "\r\n")
            cast.write(json.dumps([round(time.monotonic()-started,3),"o",clean])+"\n")
            cast.flush()
        emit("HarnessLab · a recorded CLI walkthrough\nScripted infrastructure checks and saved real-model evidence are labeled separately.\n\n")
        for index, (description, command) in enumerate(steps):
            emit("\n\x1b[36m"+description+"\x1b[0m\n")
            display = " ".join(command) if "-c" not in command else "python [inspect saved evidence]"
            emit("$ "+display+"\n")
            with subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True) as proc:
                for line in proc.stdout:
                    emit(line)
                status = proc.wait()
                emit(f"[exit {status}]\n")
                if status:
                    raise RuntimeError(f"demo step {index+1} failed")
            remaining = duration*(index+1)/len(steps) - (time.monotonic()-started)
            if remaining > 0:
                time.sleep(remaining)
        emit("\nEnd. Reproduce these commands using README.md. Model success is verified by tests, not prose.\n")
    print(target, flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--duration",type=int,default=180)
    record(parser.parse_args().duration)
