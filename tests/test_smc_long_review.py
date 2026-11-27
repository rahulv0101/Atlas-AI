from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tools import smc_long_review as tool
from tools.learn_candidate_ranker import save_signed


def registry(tmp_path):
    d=tmp_path/'study';source=d/'model'/'frozen_source';source.mkdir(parents=True)
    script=source/'model.py';script.write_text('# frozen')
    save_signed(d/'model','manifest',{'source_hashes':{'model.py':tool.digest(script)}})
    save_signed(d,'protocol',{'models':['model'],'broker_eligible':False})
    receipts={}
    for phase in ('development','holdout'):
        target=d/phase;target.mkdir();(target/'M5.csv').write_text('time,close\n')
        save_signed(target,'inputs',{'M5':tool.digest(target/'M5.csv')})
        receipts[phase]=tool.digest(target/'inputs.json')
    now=datetime.now(timezone.utc)
    r={'schema':'atlas_smc_long_review_v1','directory':str(d),'source_root':str(source),
       'protocol_sha256':tool.digest(d/'protocol.json'),'worker_sha256':tool.digest(tool.__file__),
       'source_manifest_sha256':tool.digest(d/'model/manifest.json'),'input_receipts':receipts,
       'deadline':(now+timedelta(days=1)).isoformat(),'broker_eligible':False,'auto_promotion':False,'orders_sent':0}
    save_signed(tmp_path,'smc_long_review_active',r)
    return tmp_path/'smc_long_review_active.json',r,now


def test_historical_worker_respects_sleep_deadline_and_restart_budget(tmp_path):
    path,r,now=registry(tmp_path);launch=Mock(return_value=SimpleNamespace(pid=123))
    assert tool.ensure(tmp_path,{},can_start=False,now=now,start=launch)['state']=='waiting_for_backend_and_operator'
    launch.assert_not_called()
    assert tool.ensure(tmp_path,{},can_start=True,now=now,start=launch)['state']=='historical_review_started'
    assert launch.call_args.args[0][-2:]==['--registry',str(path)]
    assert tool.ensure(tmp_path,{'smc_long_review_starts':[now.timestamp()]*3},can_start=True,now=now,start=launch)['state']=='restart_budget_exhausted_review_required'
    assert tool.ensure(tmp_path,{},can_start=True,now=now+timedelta(days=2),start=launch)['state']=='deadline_review_required'


def test_changed_inputs_or_worker_cannot_be_silently_resumed(tmp_path):
    from pathlib import Path
    path,r,now=registry(tmp_path)
    assert tool.validate(path,tmp_path)==r
    p=Path(r['directory'])/'holdout'/'M5.csv';p.write_text('revised')
    with pytest.raises(ValueError,match='historical_input_data_changed'):tool.validate(path,tmp_path)
