import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert m.take(3,range(6)) == [0,1,2]

def test_contract_1():
    assert m.take(9,[1,2]) == [1,2]

def test_contract_2():
    assert m.take(0,range(3)) == []

def test_contract_3():
    it=iter(range(5)); assert m.take(2,it)==[0,1]; assert next(it)==2

def test_contract_4():
    with pytest.raises(ValueError): m.take(-1,[1])

