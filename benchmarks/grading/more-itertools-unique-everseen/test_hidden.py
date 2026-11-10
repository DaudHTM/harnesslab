import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    assert list(m.unique_everseen(['A','a','B','b'],str.lower))==['A','B']

def test_contract_1():
    assert list(m.unique_everseen([[1],[1],[2]],tuple))==[[1],[2]]

def test_contract_2():
    assert list(m.unique_everseen([2,1,2]))==[2,1]

def test_contract_3():
    assert list(m.unique_everseen([],abs))==[]

