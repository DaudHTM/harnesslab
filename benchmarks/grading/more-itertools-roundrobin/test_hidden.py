import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert list(m.roundrobin('ABC','D','EF')) == list('ADEBFC')

def test_contract_1():
    assert list(m.roundrobin([1,2,3])) == [1,2,3]

def test_contract_2():
    assert list(m.roundrobin([], [1,2])) == [1,2]

def test_contract_3():
    assert list(m.roundrobin()) == []

