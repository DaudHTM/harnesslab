import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.parameterize('Donald E. Knuth')=='donald-e-knuth'

def test_contract_1():
    assert m.parameterize('  Alpha  Beta  ',separator='_')=='alpha_beta'

def test_contract_2():
    assert m.parameterize('Café Déjà')=='cafe-deja'

def test_contract_3():
    assert m.parameterize('Hello World',separator='')=='helloworld'

def test_contract_4():
    assert m.parameterize('')==''

