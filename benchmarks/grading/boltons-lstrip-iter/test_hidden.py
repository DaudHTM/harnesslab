import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert list(m.lstrip_iter([0,0,1,0,2],0)) == [1,0,2]

def test_contract_1():
    assert list(m.lstrip_iter(iter([None,None,3,None])) ) == [3,None]

def test_contract_2():
    assert list(m.lstrip_iter([0,0],0)) == []

def test_contract_3():
    assert list(m.lstrip_iter([],0)) == []

