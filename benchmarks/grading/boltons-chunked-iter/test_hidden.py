import pytest
from itertools import islice
import boltons.iterutils as m

def test_contract_0():
    assert list(m.chunked_iter(range(5),3,fill=-1)) == [[0,1,2],[3,4,-1]]

def test_contract_1():
    assert list(m.chunked_iter([1],4,fill=None)) == [[1,None,None,None]]

def test_contract_2():
    assert list(m.chunked_iter(range(5),3)) == [[0,1,2],[3,4]]

def test_contract_3():
    assert list(m.chunked_iter([],3,fill=0)) == []

