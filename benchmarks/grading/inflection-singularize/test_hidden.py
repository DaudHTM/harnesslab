import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.singularize('people')=='person'

def test_contract_1():
    assert m.singularize('categories')=='category'

def test_contract_2():
    assert m.singularize('sheep')=='sheep'

def test_contract_3():
    assert m.singularize('CamelOctopi')=='CamelOctopus'

def test_contract_4():
    assert m.singularize('')==''

