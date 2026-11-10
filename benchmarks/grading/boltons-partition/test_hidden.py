import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert m.partition([1,2,3,4],lambda x:x%2==0,lambda x:x>2) == ([2,4],[3],[1])

def test_contract_1():
    assert m.partition([0,1,2]) == ([1,2],[0])

def test_contract_2():
    assert m.partition([],bool) == ([],[])

def test_contract_3():
    assert m.partition([3],lambda x:True,lambda x:True) == ([3],[],[])

