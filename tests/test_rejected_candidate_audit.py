from datetime import datetime,timezone
from tools import audit_rejected_candidates as module


def test_counts_publications_and_overlapping_gates_without_pooling_m1(monkeypatch,tmp_path):
    now=datetime(2026,11,22,12,tzinfo=timezone.utc)
    status={'updated_at':'2026-11-20T12:00:00+00:00','timeframe':'M5','chosen':{'side':'sell'},
            'primary_blocker':'Volatility protection active',
            'timing_discipline':{'passed':False,'missing':['tradable_location']},
            'higher_timeframe':{'policy':'current'}}
    records=[{'publication':status},{'publication':status},
             {'publication':{**status,'timeframe':'M1'}},
             {'publication':{**status,'updated_at':'2026-11-01T12:00:00+00:00'}}]
    monkeypatch.setattr(module,'index_rows',lambda _:[{'id':i} for i in range(len(records))])
    monkeypatch.setattr(module,'read_record',lambda _,row:records[row['id']])
    result=module.audit(tmp_path,now)
    assert result['counts']['sampled_publications']==1
    assert result['counts']['primary:volatility_guard']==1
    assert result['counts']['chosen_timing_failed']==1
    assert result['timing_missing']=={'tradable_location':1}
    assert result['recorded_htf_policy_samples']=={'current':1}
    assert result['orders_sent']==0
