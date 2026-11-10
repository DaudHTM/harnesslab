import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert m.one([1,2],default='many') == 'many'

def test_contract_1():
    assert m.one([0,4,0]) == 4

def test_contract_2():
    assert m.one([1,2,3],key=lambda x:x>1,default=99) == 99

def test_contract_3():
    assert m.one([],default=8) == 8

