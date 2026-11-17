import pytest
from tools.learn_candidate_ranker import save_signed,digest
from tools.summarize_deployed_m5 import summarize


def fixture_run(path):
    flags={'full_live_parity':False,'frequency_claim_allowed':False,'expected_live_trades_per_day':None,'broker_eligible':False,'orders_sent':0}
    save_signed(path,'protocol',{**flags,'settings':{'timeframe':'M5','backtest_initial_balance':10000},'broker_spec_basis':'frozen'})
    save_signed(path,'candidates',{'strategies':['example'],'rows':[]})
    stats={'trades':0,'wins':0,'net_cash':0,'profit_factor':None,'mean_net_r':None,'max_drawdown_r':0,'rejections':{}}
    save_signed(path,'report',{**flags,'state':'completed_partial_parity_diagnostic','missing_live_evidence':['broker_state'],
        'protocol_sha256':digest(path/'protocol.json'),'candidate_receipt_sha256':digest(path/'candidates.json'),
        'diagnostic':stats,'strict_missing_evidence_screen':stats})


def test_empty_replay_does_not_claim_zero_live_frequency(tmp_path):
    fixture_run(tmp_path)
    result=summarize(tmp_path)
    assert result['diagnostic']['trades']==0
    assert result['expected_live_trades_per_day'] is None
    assert result['missing_live_evidence']==['broker_state']


@pytest.mark.parametrize('tamper',['candidates','authority','frequency'])
def test_changed_receipts_or_broadened_claims_are_rejected(tmp_path,tamper):
    import json
    fixture_run(tmp_path)
    if tamper=='candidates':
        save_signed(tmp_path,'candidates',{'strategies':[],'rows':[{}]})
    else:
        report=json.loads((tmp_path/'report.json').read_text())
        report['broker_eligible' if tamper=='authority' else 'frequency_claim_allowed']=True
        save_signed(tmp_path,'report',report)
    with pytest.raises(ValueError):summarize(tmp_path)


def test_unaccounted_candidates_cannot_be_exported(tmp_path):
    import json
    fixture_run(tmp_path)
    save_signed(tmp_path,'candidates',{'strategies':['example'],'rows':[{}]})
    report=json.loads((tmp_path/'report.json').read_text())
    report['candidate_receipt_sha256']=digest(tmp_path/'candidates.json')
    save_signed(tmp_path,'report',report)
    with pytest.raises(ValueError,match='candidate_accounting_mismatch'):
        summarize(tmp_path)
