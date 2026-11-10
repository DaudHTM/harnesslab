import pytest
from itertools import islice
import more_itertools as m

def test_contract_0():
    it=iter(range(6)); m.consume(it,2); assert next(it)==2

def test_contract_1():
    it=iter([4,5]); m.consume(it,0); assert next(it)==4

def test_contract_2():
    it=iter([1]); m.consume(it,9); assert list(it)==[]

def test_contract_3():
    it=iter(range(3)); m.consume(it); assert list(it)==[]

