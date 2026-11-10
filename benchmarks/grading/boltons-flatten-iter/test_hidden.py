import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert list(m.flatten_iter([b'ab',[b'cd']])) == [b'ab',b'cd']

def test_contract_1():
    assert list(m.flatten_iter(['ab',[1,[2]]])) == ['ab',1,2]

def test_contract_2():
    assert list(m.flatten_iter(iter([[1],[],(2,3)]))) == [1,2,3]

def test_contract_3():
    assert list(m.flatten_iter([])) == []

