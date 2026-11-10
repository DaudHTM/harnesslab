"""Materialize the demo and all curated source snapshots for Compose."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.bootstrap_demo import bootstrap
from scripts.build_corpus import build

if __name__=="__main__":
    bootstrap(ROOT)
    build(fetch=True)
