import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert list(m.tail(2,[1,2,3,4,5])) == [4,5]

def test_contract_1():
    assert list(m.tail(8,[1,2])) == [1,2]

def test_contract_2():
    assert list(m.tail(0,[1,2])) == []

def test_contract_3():
    assert list(m.tail(2,iter([1,2,3]))) == [2,3]

