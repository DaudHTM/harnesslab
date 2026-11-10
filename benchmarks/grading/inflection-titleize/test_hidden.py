import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.titleize('employee_salary')=='Employee Salary'

def test_contract_1():
    assert m.titleize('rawScaledScorer')=='Raw Scaled Scorer'

def test_contract_2():
    assert m.titleize('the_man_without_a_past')=='The Man Without A Past'

def test_contract_3():
    assert m.titleize('')==''

