import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert list(m.unique_iter(['A','a','B','b'],key=str.lower)) == ['A','B']

def test_contract_1():
    assert list(m.unique_iter([1,-1,2,-2],key=abs)) == [1,2]

def test_contract_2():
    assert list(m.unique_iter([2,1,2])) == [2,1]

def test_contract_3():
    assert list(m.unique_iter([],key=abs)) == []

