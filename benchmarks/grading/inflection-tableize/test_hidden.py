import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.tableize('RawScaledScorer')=='raw_scaled_scorers'

def test_contract_1():
    assert m.tableize('Person')=='people'

def test_contract_2():
    assert m.tableize('Category')=='categories'

def test_contract_3():
    assert m.tableize('people')=='people'

def test_contract_4():
    assert m.tableize('')==''

