import pandas as pd
from atlas_ai.testing.smc_followthrough import followthrough, evaluate, MODEL


def test_requires_both_closed_directional_bodies_and_progressing_closes():
    now=pd.Timestamp('2026-11-20T12:10Z')
    f=pd.DataFrame({'time':pd.date_range(end=now,periods=33,freq='5min'),
                    'open':[100]*30+[100,101,1], 'close':[100]*30+[101,102,1000]})
    assert followthrough(f,'buy',now)
    assert not followthrough(f,'sell',now)
    f.loc[30,'open']=102
    assert not followthrough(f,'buy',now)
    f.loc[30,['open','close']]=[100,103]
    assert not followthrough(f,'buy',now)


def test_rejection_does_not_mutate_baseline_or_broaden_authority(monkeypatch):
    from atlas_ai.testing import smc_followthrough as module
    base={'candidate':{'strategy':'baseline'},'side':'buy','setup_id':'x'}
    monkeypatch.setattr(module,'sweep_reclaim',lambda *args:base)
    monkeypatch.setattr(module,'followthrough',lambda *args:False)
    result=evaluate(None,None,None,None)
    assert result['candidate'] is None and base['candidate']=={'strategy':'baseline'}
    assert result['strategy']==MODEL and not result['broker_eligible']
    monkeypatch.setattr(module,'followthrough',lambda *args:True)
    result=evaluate(None,None,None,None)
    assert result['candidate']['strategy']==MODEL and base['setup_id']=='x'
