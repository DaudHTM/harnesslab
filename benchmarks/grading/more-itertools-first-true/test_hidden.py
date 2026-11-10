import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert m.first_true([1,0,2],9,lambda x:x==0)==0

def test_contract_1():
    assert m.first_true([1,3,4],None,lambda x:x%2==0)==4

def test_contract_2():
    assert m.first_true([1,3],'none',lambda x:x%2==0)=='none'

def test_contract_3():
    assert m.first_true([0,False,4])==4

