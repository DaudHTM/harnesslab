import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.humanize('author_id')=='Author'

def test_contract_1():
    assert m.humanize('author_id_number')=='Author id number'

def test_contract_2():
    assert m.humanize('employee_salary')=='Employee salary'

def test_contract_3():
    assert m.humanize('')==''

