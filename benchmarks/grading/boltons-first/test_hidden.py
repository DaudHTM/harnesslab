import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert m.first([2,0,3],key=lambda x:x==0,default=9) == 0

def test_contract_1():
    assert m.first([1,3,4],key=lambda x:x%2==0) == 4

def test_contract_2():
    assert m.first([1,3],key=lambda x:x%2==0,default='none') == 'none'

def test_contract_3():
    assert m.first([0,False,5]) == 5

