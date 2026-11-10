"""Publish a completed study with raw evidence and honest paired summaries."""
import argparse
import json
import os
import sys
import shutil
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harnesslab.report import export
from harnesslab.store import Store


def publish(identity, output=ROOT/"docs/results"):
    store=Store(os.environ.get("HARNESSLAB_DATABASE_URL",str(ROOT/".harnesslab/state.db")))
    lock=store.study_lock(identity)
    if not lock:
        raise ValueError("experiment is not a frozen study")
    metadata=json.loads(lock["metadata"])
    data=export(store,identity)
    if not data["runs"] or any(r["status"] in {"queued","running"} for r in data["runs"]):
        raise ValueError("study has unfinished jobs; keep the checkpoint and publish after completion")
    phase=metadata["phase"]
    output.mkdir(parents=True,exist_ok=True)
    stem=f"{phase}-{identity[:12]}"
    raw=output/(stem+".json")
    raw.write_text(json.dumps({"study":metadata,**data},indent=2).replace(str(ROOT),"${PROJECT_ROOT}")+"\n")
    source=ROOT/".harnesslab/studies"/identity/"reproduction.tar.gz"
    archive_note="This historical study predates automatic source archives; its fingerprint and traces are retained, but it is not a complete reproduction bundle."
    if source.is_file():
        expected=Path(str(source)+".sha256")
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if not expected.is_file() or digest!=expected.read_text().strip():
            raise ValueError("study source archive checksum mismatch")
        target=output/(stem+"-source.tar.gz")
        shutil.copyfile(source,target)
        archive_note=f"[Reproduction source archive]({target.name}) · SHA-256 `{digest}`. Model weights are excluded and can be downloaded by pinned revision/checksum."
    lines=[f"# {'Development pilot' if phase=='pilot' else 'Held-out comparison'}: local Qwen3", "",
           f"Experiment `{identity}` · published {datetime.now(timezone.utc).isoformat()}","",
           "This is a measured local-model study. Synthetic fixture results are not included. " +
           ("These development results are not a held-out performance claim." if phase=="pilot" else "Authored regression tasks are not a broad real-world SWE benchmark."),"",
           f"- Tasks: {len(metadata['tasks'])}; repetitions per configuration: {metadata['repetitions']}.",
           f"- Backend: `{metadata['backend']}`; source fingerprint: `{lock['source_sha256']}`.",
           f"- Model: `{metadata['configs'][0]['model']}`; provider API charges: $0 (local inference).",
           f"- Seed: {metadata['seed']}; fixed-seed repetitions measure repeatability, not independent stochastic samples.","",
           "| Configuration | Finished | Valid trials | Solved | Success | Infra errors | Median seconds | p95 seconds |",
           "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    def number(value):return "—" if value is None else f"{value:.2f}"
    for c in data["comparison"]:
        rate="—" if c['success_rate'] is None else f"{100*c['success_rate']:.1f}%"
        lines.append(f"| {c['harness']} `{c['config_hash'][:8]}` | {c['completed']}/{c['total']} | {c['valid_trials']} | {c['solved']} | {rate} | {c['infrastructure_errors']} | {number(c['median_seconds'])} | {number(c['p95_seconds'])} |")
    lines += ["","Valid trials include solved, unsolved, and budget-exceeded outcomes. Infrastructure errors and cancelled jobs are excluded from the success denominator and remain in the raw results. Latencies reflect this host and may include infrastructure noise.","","## Paired outcomes",""]
    for pair in data["paired_comparisons"]:
        lines += [f"- Common tasks: {pair['common_tasks']}; balanced trial counts: {pair['balanced_trials']}.",
                  f"- Resilient better: {pair['resilient_better_tasks']}; baseline better: {pair['baseline_better_tasks']}; ties: {pair['tied_tasks']}.",
                  f"- Mean task-level success difference (resilient minus baseline): {number(pair['mean_task_success_difference'])}."]
    lines += ["","No significance claim is made. Task-level pairing keeps repeated trials together; descriptive trial-level intervals are available in the raw export.","","## Failure evidence",""]
    statuses=Counter(r["status"] for r in data["runs"])
    lines.append("Outcomes: "+", ".join(f"{k}={v}" for k,v in sorted(statuses.items()))+".")
    lines += ["","| Task | Harness | Outcome | Added lines | Deleted lines |","| --- | --- | --- | ---: | ---: |"]
    for run in data["runs"]:
        path=Path(run["result"].get("patch",""))
        patch=path.read_text() if path.is_file() else ""
        added=sum(line.startswith('+') and not line.startswith('+++ ') for line in patch.splitlines())
        deleted=sum(line.startswith('-') and not line.startswith('--- ') for line in patch.splitlines())
        lines.append(f"| {Path(run['task_path']).stem} | {run['config']['name']} | {run['status']} | {added} | {deleted} |")
    lines += ["","A nonempty patch is not sufficient evidence of correctness. The grader's original regression tests and hidden checks decide the outcome; large deletions are retained for diagnosis rather than counted as successful fixes.","",
              f"Known API spend: ${data['accounting']['actual_usd']:.4f}; unsettled calls: {data['accounting']['unsettled_calls']}; reserved uncertain API spend: ${data['accounting']['unsettled_reserved_usd']:.4f}.","",
              f"[Raw runs, traces, configuration hashes, and paired outcomes]({raw.name})","",archive_note,""]
    report=output/(stem+".md")
    report.write_text("\n".join(lines))
    print(report,flush=True)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("experiment_id")
    parser.add_argument("--output",type=Path,default=ROOT/"docs/results")
    args=parser.parse_args()
    publish(args.experiment_id,args.output)
