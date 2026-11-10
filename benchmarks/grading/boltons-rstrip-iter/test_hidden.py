import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert list(m.rstrip_iter([1,0,0,2,0],0)) == [1,0,0,2]

def test_contract_1():
    assert list(m.rstrip_iter(iter([0,1,0]),0)) == [0,1]

def test_contract_2():
    assert list(m.rstrip_iter([0,0],0)) == []

def test_contract_3():
    assert list(m.rstrip_iter([],0)) == []

