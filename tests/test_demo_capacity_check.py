import pytest
from tools.demo_capacity_check import capacity


def test_capacity_requires_both_risk_and_free_margin():
    assert capacity(150,600,20,1000)['passes']
    assert not capacity(150,50,20,1000)['passes']
    assert not capacity(150,600,20,10)['passes']


@pytest.mark.parametrize('risk',[None,float('nan'),float('inf'),-1,0])
def test_unknown_or_invalid_risk_is_not_a_pass(risk):
    assert not capacity(risk,600,20,1000)['passes']
