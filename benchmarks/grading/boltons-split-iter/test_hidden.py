import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert list(m.split_iter([1,0,2,0,3], 0, 1)) == [[1],[2,0,3]]

def test_contract_1():
    assert list(m.split_iter(iter([1,0,2,0,3]), 0, 1)) == [[1],[2,0,3]]

def test_contract_2():
    assert list(m.split_iter([1,0,2], 0, 0)) == [[1,0,2]]

def test_contract_3():
    assert list(m.split_iter([1,0,2,0,3], 0, -1)) == [[1],[2],[3]]

