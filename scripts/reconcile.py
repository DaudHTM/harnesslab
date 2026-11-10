"""Inspect or sweep orphan containers belonging to terminal HarnessLab jobs.

Unknown jobs and running jobs are always retained. --apply enables deletion;
--watch repeats this application maintenance loop without installing a scheduler.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harnesslab.sandbox import execute
from harnesslab.store import Store

from harnesslab.maintenance import reconcile


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--watch",action="store_true")
    parser.add_argument("--interval",type=float,default=30)
    args=parser.parse_args()
    if args.interval < 5:
        parser.error("interval must be at least five seconds")
    store=Store(os.environ.get("HARNESSLAB_DATABASE_URL",str(ROOT / ".harnesslab/state.db")))
    while True:
        print(json.dumps(reconcile(store,args.apply),indent=2),flush=True)
        if not args.watch:
            break
        time.sleep(args.interval)
