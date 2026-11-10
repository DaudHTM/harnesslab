"""Named, reproducible fault checks against real runtime boundaries.

These scenarios use deterministic fixtures. They do not measure a model's
capability or prompt-injection resistance, and never call a paid API.
"""
import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    "mcp_timeout": "tests/test_core.py::test_complete_run[resilient-mcp_timeout]",
    "malformed_output": "tests/test_core.py::test_complete_run[resilient-malformed_output]",
    "hanging_command": "tests/test_faults.py::test_hanging_command_is_killed",
    "worker_crash": "tests/test_faults.py::test_worker_process_crash_and_recovery",
    "provider_rate_limit": "tests/test_faults.py::test_provider_rate_limit_retry_is_bounded",
    "budget_exhaustion": "tests/test_core.py::test_token_budget_stops_before_model",
    "path_injection": "tests/test_faults.py::test_mcp_rejects_injected_path_escape",
    "live_cancellation": "tests/test_faults.py::test_live_cancellation_unwinds_stdio_without_infrastructure_error",
    "mcp_crash": "tests/test_maintenance_and_mcp.py::test_crashed_stdio_server_fails_without_hanging",
    "mcp_unresponsive": "tests/test_maintenance_and_mcp.py::test_unresponsive_stdio_server_has_bounded_handshake",
}


def run(names, destination):
    destination.mkdir(parents=True,exist_ok=True)
    results=[]
    for name in names:
        started=time.monotonic()
        xml_path=destination/(name+".xml")
        proc=subprocess.run([sys.executable,"-m","pytest",SCENARIOS[name],"-q","--junitxml="+str(xml_path)],cwd=ROOT,capture_output=True,text=True,timeout=45)
        results.append({"scenario":name,"passed":proc.returncode==0,"duration_seconds":time.monotonic()-started,"test":SCENARIOS[name],"output":proc.stdout+proc.stderr})
        if xml_path.exists():
            tree=ET.parse(xml_path)
            for node in tree.iter():node.attrib.pop("hostname",None)
            tree.write(xml_path,encoding="unicode",xml_declaration=True)
        print(name,"PASS" if proc.returncode==0 else "FAIL",flush=True)
    summary={"schema_version":1,"kind":"deterministic infrastructure fault scenarios", "learned_model_benchmark":False,"passed":sum(r["passed"] for r in results),"total":len(results),"scenarios":results}
    (destination/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("scenario",choices=["all",*SCENARIOS],default="all",nargs="?")
    parser.add_argument("--output",type=Path,default=ROOT/"docs/evidence/fault-matrix")
    args=parser.parse_args()
    summary=run(list(SCENARIOS) if args.scenario=="all" else [args.scenario],args.output)
    raise SystemExit(0 if summary["passed"]==summary["total"] else 1)
