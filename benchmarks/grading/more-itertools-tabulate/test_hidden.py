import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert list(islice(m.tabulate(lambda x:x*x,3),3)) == [9,16,25]

def test_contract_1():
    assert list(islice(m.tabulate(lambda x:x,-2),4)) == [-2,-1,0,1]

def test_contract_2():
    assert list(islice(m.tabulate(lambda x:x+1),3)) == [1,2,3]

def test_contract_3():
    assert list(islice(m.tabulate(str,10),2)) == ['10','11']

