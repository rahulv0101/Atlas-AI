import json
import pytest
from tools.audit_natural_lifecycle import audit_journal
from test_day_trading_observation import fills, evidence


def journal(tmp_path, protected=True, after_exit=False):
    seen={key:{**value,'ticket':key} for key,value in fills().items()};entry,exit_row=list(seen.values())
    position={'position_id':'10','side':'buy','current_price':100.,'sl':99.,'tp':102.}
    rows=[{'observed_at':'2026-11-23T08:00:00+00:00','broker_ok':True,
           'positions':[position] if protected and not after_exit else [],'new_deals':[entry]},
          {'observed_at':'2026-11-23T08:01:00+00:00','broker_ok':True,'positions':[], 'new_deals':[exit_row]}]
    if after_exit:
        rows.append({'observed_at':'2026-11-23T08:02:00+00:00','broker_ok':True,'positions':[position],'new_deals':[]})
        rows.append({'observed_at':'2026-11-23T08:03:00+00:00','broker_ok':True,'positions':[],'new_deals':[]})
    path=tmp_path/'journal.jsonl';path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    return path,seen


def test_raw_journal_confirms_historical_protected_cycle_without_claiming_current_version(tmp_path):
    path,seen=journal(tmp_path)
    result=audit_journal(path,seen,evidence())
    assert result['protected_lifecycle_count']==1
    assert not result['current_build_verified'] and not result['new_model_verified']
    assert not result['profitability_proven'] and result['orders_sent']==0


def test_missing_or_late_protection_cannot_verify_lifecycle(tmp_path):
    for protected,late in ((False,False),(True,True)):
        path,seen=journal(tmp_path,protected,late)
        assert audit_journal(path,seen,evidence())['protected_lifecycle_count']==0


def test_checkpoint_fills_cannot_override_raw_journal(tmp_path):
    path,seen=journal(tmp_path)
    next(iter(seen.values()))['net']=999
    with pytest.raises(ValueError,match='checkpoint_fill_missing'):
        audit_journal(path,seen,evidence())
