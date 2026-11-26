from copy import deepcopy
import pandas as pd
import pytest
from tools.recover_unconfirmed_forecast_tail import trim_unreferenced
from tools.recover_unconfirmed_forecast_tail import rebind_contract


def evidence():
    cutoff=pd.Timestamp('2026-11-26T12:10Z')
    frames={tf:[{'time':at.isoformat(),'close':100.} for at in pd.date_range(end=cutoff,periods=40,freq=freq)]
            for tf,freq in [('M5','5min'),('H1','h')]}
    state={'last_available':cutoff.isoformat(),'forecasts':{'control':[{'available_at':cutoff.isoformat()}],'candidate':[]}}
    return frames,state


def test_only_unevaluated_tail_is_removed_without_changing_existing_data():
    frames,state=evidence();before=deepcopy(frames);original=deepcopy(state)
    trimmed,counts=trim_unreferenced(frames,state)
    assert counts=={'M5':1,'H1':1}
    assert trimmed['M5']==frames['M5'][:-1] and frames==before and state==original


def test_referenced_forecast_tail_cannot_be_trimmed():
    frames,state=evidence();state['forecasts']['candidate']=[{'available_at':'2026-11-26T12:15Z'}]
    with pytest.raises(ValueError,match='references_tail'):trim_unreferenced(frames,state)


def test_no_tail_or_missing_evaluated_inputs_cannot_trigger_recovery():
    frames,state=evidence();frames={k:v[:-1] for k,v in frames.items()}
    with pytest.raises(ValueError,match='no_unreferenced_tail'):trim_unreferenced(frames,state)
    frames['M5'].pop()
    with pytest.raises(ValueError,match='evaluated_M5_input_missing'):trim_unreferenced(frames,state)


def test_contract_rebinding_preserves_all_review_rules():
    old={'plan_sha256':'old','rule':'no backdated fills','costs':'unchanged'}
    new=rebind_contract(old,'old','new')
    assert old['plan_sha256']=='old' and new=={**old,'plan_sha256':'new'}
    with pytest.raises(ValueError):rebind_contract(old,'wrong','new')
