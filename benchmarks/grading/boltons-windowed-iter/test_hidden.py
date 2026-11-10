import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert list(m.windowed_iter([1,2],3,fill=-1)) == [(1,2,-1),(2,-1,-1)]

def test_contract_1():
    assert list(m.windowed_iter(iter([1,2,3]),2,fill='x')) == [(1,2),(2,3),(3,'x')]

def test_contract_2():
    assert list(m.windowed_iter([1,2],3)) == []

def test_contract_3():
    assert list(m.windowed_iter([],2,fill=0)) == []

