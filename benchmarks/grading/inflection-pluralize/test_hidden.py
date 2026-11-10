import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.pluralize('person')=='people'

def test_contract_1():
    assert m.pluralize('category')=='categories'

def test_contract_2():
    assert m.pluralize('sheep')=='sheep'

def test_contract_3():
    assert m.pluralize('CamelOctopus')=='CamelOctopi'

def test_contract_4():
    assert m.pluralize('')==''

