import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from harnesslab.models import HarnessConfig


def wilson(solved, total):
    if not total:
        return [0, 1]
    z = 1.96
    p = solved / total
    center = (p + z*z/(2*total))/(1+z*z/total)
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))/(1+z*z/total)
    return [max(0, center-half), min(1, center+half)]


def compare(store, experiment):
    groups = defaultdict(list)
    costs = store.costs_by_run(experiment)
    for run in store.runs(experiment):
        config = json.loads(run["config"])
        groups[(config["name"], config["model"], config["provider"], HarnessConfig.model_validate(config).digest())].append(run)
    result = []
    for (name, model, provider, config_hash), runs in groups.items():
        terminal = [r for r in runs if r["status"] not in {"queued", "running"}]
        valid = [r for r in terminal if r["status"] in {"solved", "unsolved", "budget_exceeded"}]
        solved = sum(r["status"] == "solved" for r in valid)
        # Sum usage from all attempt traces, including interrupted attempts.
        cost = 0
        for run in runs:
            if run["id"] in costs:
                cost += costs[run["id"]]
                continue
            # Legacy traces predating the reservation ledger remain readable.
            attempts = {}
            for event in store.events(run["id"]):
                if event["kind"] == "model_response":
                    attempts[event["attempt"]] = event["data"]["usage"]["cost_usd"]
            cost += sum(attempts.values())
        durations = sorted(parsed["duration_seconds"] for r in terminal if "duration_seconds" in (parsed := json.loads(r["result"] or "{}")))
        result.append({"harness": name, "model": model, "provider": provider, "config_hash": config_hash, "scripted_fixture": provider == "fake", "total": len(runs), "completed": len(terminal), "valid_trials": len(valid), "solved": solved, "success_rate": solved/len(valid) if valid else None, "success_interval_95": wilson(solved, len(valid)), "interval_method": "descriptive Wilson interval over trials; repeated trials are correlated by task", "cost_usd": cost, "cost_per_success_usd": cost/solved if solved else None, "median_seconds": statistics.median(durations) if durations else None, "p95_seconds": durations[max(0, math.ceil(.95*len(durations))-1)] if durations else None, "infrastructure_errors": sum(r["status"] == "infrastructure_error" for r in terminal)})
    return result


def paired_comparisons(store, experiment):
    """Pair by task, keeping repeated trials together instead of inflating N."""
    groups = defaultdict(lambda: defaultdict(list))
    configs = {}
    for run in store.runs(experiment):
        if run["status"] not in {"solved", "unsolved", "budget_exceeded"}:
            continue
        config = HarnessConfig.model_validate_json(run["config"])
        digest = config.digest()
        configs[digest] = config
        groups[digest][Path(run["task_path"]).stem].append(int(run["status"] == "solved"))
    result = []
    for left, left_config in configs.items():
        for right, right_config in configs.items():
            if left_config.name != "baseline" or right_config.name != "resilient" or (left_config.provider, left_config.model) != (right_config.provider, right_config.model):
                continue
            tasks = []
            for identity in sorted(groups[left].keys() & groups[right].keys()):
                a, b = groups[left][identity], groups[right][identity]
                tasks.append({"task": identity, "baseline_trials": len(a), "resilient_trials": len(b), "baseline_success_rate": statistics.mean(a), "resilient_success_rate": statistics.mean(b), "difference": statistics.mean(b)-statistics.mean(a)})
            result.append({"baseline_config_hash": left, "resilient_config_hash": right, "model": left_config.model,
                           "common_tasks": len(tasks), "balanced_trials": all(t["baseline_trials"] == t["resilient_trials"] for t in tasks),
                           "mean_task_success_difference": statistics.mean(t["difference"] for t in tasks) if tasks else None,
                           "resilient_better_tasks": sum(t["difference"] > 0 for t in tasks), "baseline_better_tasks": sum(t["difference"] < 0 for t in tasks),
                           "tied_tasks": sum(t["difference"] == 0 for t in tasks), "tasks": tasks,
                           "interpretation": "Descriptive paired comparison; no significance claim. Infrastructure-error and cancelled trials are excluded."})
    return result


def export(store, experiment):
    runs = store.runs(experiment)
    return {"schema_version": 1, "experiment_id": experiment, "comparison": compare(store, experiment), "paired_comparisons": paired_comparisons(store, experiment), "accounting": store.accounting(experiment), "runs": [{**r, "config": json.loads(r["config"]), "result": json.loads(r["result"] or "{}"), "events": store.events(r["id"])} for r in runs]}
