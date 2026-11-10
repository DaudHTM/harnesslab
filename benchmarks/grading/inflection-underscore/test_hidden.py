import pytest
from itertools import islice
import inflection as m

def test_contract_0():
    assert m.underscore('HTTPServer')=='http_server'

def test_contract_1():
    assert m.underscore('XMLHttpRequest')=='xml_http_request'

def test_contract_2():
    assert m.underscore('DeviceType')=='device_type'

def test_contract_3():
    assert m.underscore('some-name')=='some_name'

def test_contract_4():
    assert m.underscore('IO')=='io'

