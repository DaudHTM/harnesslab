import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.dasherize('one_two_three')=='one-two-three'

def test_contract_1():
    assert m.dasherize('a__b')=='a--b'

def test_contract_2():
    assert m.dasherize('A-b_C')=='A-b-C'

def test_contract_3():
    assert m.dasherize('')==''

