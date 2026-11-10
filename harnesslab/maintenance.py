"""Conservative reconciliation of containers belonging to terminal jobs."""
import json
import re

from harnesslab.sandbox import execute

TERMINAL = {"solved", "unsolved", "infrastructure_error", "cancelled", "budget_exceeded"}


def reconcile(store, apply=False, command=execute):
    listing = command(["docker","ps","-aq","--filter","label=harnesslab.managed=true"],timeout=10)
    if listing.code:
        raise RuntimeError(listing.output)
    result = []
    for container in listing.output.splitlines():
        if not re.fullmatch(r"[0-9a-f]{12,64}",container):
            raise ValueError("invalid container ID from Docker")
        inspected = command(["docker","inspect",container],timeout=10)
        if inspected.code:
            result.append({"container":container,"action":"already_removed"})
            continue
        metadata = json.loads(inspected.output)[0]
        labels = metadata.get("Config",{}).get("Labels") or {}
        run_id = labels.get("harnesslab.run","")
        if labels.get("harnesslab.managed") != "true" or not re.fullmatch(r"[0-9a-f]{32}",run_id):
            result.append({"container":container,"action":"retain_unrecognized"})
            continue
        run = store.get(run_id)
        if not run or run["status"] not in TERMINAL:
            result.append({"container":container,"run_id":run_id,"action":"retain_unknown_or_active"})
            continue
        row = {"container":container,"run_id":run_id,"job_status":run["status"],"action":"eligible"}
        if apply:
            removed = command(["docker","rm","-f",container],timeout=15)
            row["action"] = "removed" if removed.code == 0 else "remove_failed"
            if removed.code:
                row["error"] = removed.output
        result.append(row)
    return result
