import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert m.all_equal(['A','a'],key=str.lower)

def test_contract_1():
    assert m.all_equal([1,-1,1],key=abs)

def test_contract_2():
    assert not m.all_equal([1,2],key=abs)

def test_contract_3():
    assert m.all_equal([])

def test_contract_4():
    assert m.all_equal([3])

