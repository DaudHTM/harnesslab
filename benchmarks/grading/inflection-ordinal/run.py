import os, sys
from pathlib import Path
import pytest
sys.path.insert(0, os.getcwd())
p=Path(__file__).resolve().parent
raise SystemExit(pytest.main(['-q','--import-mode=importlib','-c',str(p/'pytest.ini'),str(p/'test_hidden.py'),str(p/'test_upstream.py')]))
