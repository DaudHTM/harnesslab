import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert m.nth([4,5,6],0)==4

def test_contract_1():
    assert m.nth(range(7),3)==3

def test_contract_2():
    assert m.nth([],0,'missing')=='missing'

def test_contract_3():
    marker=object(); assert m.nth([1],8,marker) is marker

def test_contract_4():
    assert m.nth(iter([]),3,0)==0

def test_contract_5():
    it=iter(range(5)); assert m.nth(it,2)==2; assert next(it)==3

