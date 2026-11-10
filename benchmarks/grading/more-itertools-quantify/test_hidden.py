import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert m.quantify([0,1,2,3],lambda x:x%2==0)==2

def test_contract_1():
    assert m.quantify([0,0,1],lambda x:x==0)==2

def test_contract_2():
    assert m.quantify([0,1,'',2])==2

def test_contract_3():
    assert m.quantify([],lambda x:True)==0

