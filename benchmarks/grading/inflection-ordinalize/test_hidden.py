import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.ordinalize(-1)=='-1st'

def test_contract_1():
    assert m.ordinalize(-12)=='-12th'

def test_contract_2():
    assert m.ordinalize(-103)=='-103rd'

def test_contract_3():
    assert m.ordinalize(22)=='22nd'

def test_contract_4():
    assert m.ordinalize(0)=='0th'

