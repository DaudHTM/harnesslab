import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.ordinal(-1)=='st'

def test_contract_1():
    assert m.ordinal(-22)=='nd'

def test_contract_2():
    assert m.ordinal(-113)=='th'

def test_contract_3():
    assert m.ordinal('103')=='rd'

def test_contract_4():
    assert m.ordinal(0)=='th'

