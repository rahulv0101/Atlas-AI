from copy import deepcopy
import pandas as pd
import pytest
from test_smc_pullback import pullback,NOW
from atlas_ai.strategies.smc_composite import structure
from atlas_ai.strategies.smc_entry_models import event_retest,sweep_reclaim,MODELS
from atlas_ai.strategies.smc_framework import evaluate as prior


def mirror(f,c,q):
    old=f.copy();f=f.copy();f['open']=220-old.open;f['close']=220-old.close;f['high']=220-old.low;f['low']=220-old.high
    c=deepcopy(c)
    c['details']={k:('sell' if v=='buy' else 'buy' if v=='sell' else v) for k,v in c['details'].items()}
    for row in c['evidence'].values():
        row['recent_low'],row['recent_high']=220-row['recent_high'],220-row['recent_low']
        if 'recent_closes' in row:row['recent_closes']=[220-v for v in row['recent_closes']]
    q={**q,'bid':220-q['ask'],'ask':220-q['bid']}
    return f,c,q


def event_case(side='buy'):
    f,c,q=pullback();f=f.iloc[:60].copy().reset_index(drop=True)
    level=structure(f.iloc[:59])['last_swing_high']
    f.loc[59,['open','high','low','close']]=[level-1.2,level-1.,level-1.7,level-1.5]
    rows=[{'open':level-3.,'high':level+.1,'low':level-3.2,'close':level-.2},
        {'open':level-.2,'high':level+.5,'low':level-.25,'close':level+.3},
        {'open':level-.5,'high':level+.4,'low':level-.6,'close':level+.2}]
    f=pd.concat([f,pd.DataFrame(rows)],ignore_index=True);f['time']=pd.date_range(end='2026-11-13T11:55:00Z',periods=len(f),freq='5min')
    q={**q,'bid':level+.18,'ask':level+.22}
    return mirror(f,c,q) if side=='sell' else (f,c,q)


@pytest.mark.parametrize('side',['buy','sell'])
def test_structure_break_can_follow_impulse_and_reclaim_opposing_M5_structure(side):
    f,c,q=event_case(side)
    assert prior(f,c,q,NOW)['candidate'] is None
    r=event_retest(f,c,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['candidate']['side']==side and r['candidate']['strategy']==MODELS[0]
    assert r['structure_shift']['type']=='CHOCH'
    assert r['displacement_bar_utc']<r['structure_shift']['bar_utc']
    assert r['invalidation_basis']=='selected_zone_plus_actual_first_visit_extreme'
    assert r['reward_risk_before_fees_slippage']>=2 and not r['broker_eligible']


def sweep_case(side='buy'):
    f,c,q=pullback();f=f.iloc[:62].copy().reset_index(drop=True)
    f['time']=pd.date_range(end='2026-11-13T11:55:00Z',periods=len(f),freq='5min')
    for tf in ['H1','M15']:c['evidence'][tf]['recent_high']=140.
    q={**q,'bid':float(f.close.iloc[-1])-.02,'ask':float(f.close.iloc[-1])+.02}
    return mirror(f,c,q) if side=='sell' else (f,c,q)


@pytest.mark.parametrize('side',['buy','sell'])
def test_sweep_reclaim_does_not_require_an_unrelated_gap_or_order_block(side):
    f,c,q=sweep_case(side);r=sweep_reclaim(f,c,q,NOW)
    assert r['stage']=='candidate_ready',r
    assert r['candidate']['strategy']==MODELS[1] and r['candidate']['side']==side
    assert r['confirmation']['type']=='sweep_candle_extreme_reclaim'
    assert 'FVG' not in r and 'order_block' not in r and not r['broker_eligible']


@pytest.mark.parametrize('model,case',[(event_retest,event_case),(sweep_reclaim,sweep_case)])
def test_both_models_keep_freshness_target_and_execution_boundaries(model,case):
    f,c,q=case();baseline=model(f,c,q,NOW);assert baseline['candidate']
    extra=f.tail(1).copy();extra['time']=pd.Timestamp('2026-11-13T12:00:00Z');extra['low']=1.;extra['high']=9999.;extra['close']=2.
    assert model(pd.concat([f,extra],ignore_index=True),c,q,NOW)==baseline
    c['details']['H4']='sell';assert model(f,c,q,NOW)['candidate'] is None
    f,c,q=case();c['evidence']['M15']['recent_high']=q['ask']+.1
    assert model(f,c,q,NOW)['candidate'] is None
    from atlas_ai.strategies.inventory import base_inventory
    assert not set(MODELS)&{s.name for s in base_inventory('M5',top_down=True)}


def test_event_needs_real_impulse_and_sweep_needs_a_real_liquidity_take():
    f,c,q=event_case();f.loc[60,'open']=f.loc[60,'close']-.01
    assert event_retest(f,c,q,NOW)['candidate'] is None
    f,c,q=sweep_case();f.loc[60,'low']=f.low.iloc[:60].min()+.1
    assert sweep_reclaim(f,c,q,NOW)['candidate'] is None


def test_offline_matched_preparation_does_not_contact_broker_or_activate_model(tmp_path,monkeypatch):
    from atlas_ai.config.settings import Settings
    from atlas_ai.testing.historical_broker import BrokerSpec
    from atlas_ai.learning.observation_checkpoint import account_scope
    from atlas_ai.atomic_files import atomic_json
    from dataclasses import asdict
    from tools import smc_validation as tool
    from tools.guarded_research_audit import safe_settings
    from tools.learn_candidate_ranker import save_signed,digest,read
    root=tmp_path/'code';(root/'atlas_ai').mkdir(parents=True);(root/'tools').mkdir()
    (root/'atlas_ai/helper.py').write_text('# source\n')
    storage=tmp_path/'storage';source=storage/'source';source.mkdir(parents=True)
    cfg=Settings(0,'','',timeframe='M5',top_down_confluence_enabled=True,storage_dir=str(storage))
    old={'settings':safe_settings(cfg),'account_scope':account_scope(cfg),'history_start':'2026-01-01T00:00:00Z',
        'history_end':'2026-07-01T00:00:00Z','spec':asdict(BrokerSpec(.01,.01,1.,1.,.01,1.,.01,2)),
        'cost_evidence':{'currency':'ZAR'},'limits':{'lot_cap':.01}}
    save_signed(source,'manifest',old);inputs={}
    for tf in ['D1','H4','H1','M15','M5']:
        p=source/(tf+'.csv');p.write_text('unchanged closed source\n');inputs[tf]=digest(p)
    save_signed(source,'inputs',inputs)
    save_signed(storage,'acceptance_plan',{'deadline':'2030-01-01T00:00:00Z'})
    atomic_json(storage/'smc_validation_active.json',{'run_dir':str(source)})
    monkeypatch.setattr(tool,'ROOT',root);monkeypatch.setattr(tool,'load_settings',lambda:cfg)
    def forbidden(*a,**k):raise AssertionError('offline comparison must not contact broker')
    monkeypatch.setattr(tool,'check_account',forbidden);monkeypatch.setattr(tool,'broker_snapshot',forbidden)
    out=storage/'new';tool.initialize(out,MODELS[0],source,activate=False,reuse_costs=True)
    assert read(storage/'smc_validation_active.json')['run_dir']==str(source)
    assert read(out/'manifest.json')['spec']==old['spec']
    assert not read(out/'manifest.json')['paper_activation_requested']
    assert all(digest(out/(tf+'.csv'))==expected for tf,expected in inputs.items())


def test_development_selection_cannot_use_a_lucky_holdout_or_activate_broker():
    from tools.research_smc_entries import training_selection
    a={'stages':{'development':{'review_passed':True,'mean_r':.1},'holdout':{'mean_r':-9.}}}
    b={'stages':{'development':{'review_passed':False,'mean_r':.2},'holdout':{'mean_r':999.}}}
    result=training_selection({'a':a,'b':b})
    assert result['selected_for_forward_paper']=='a' and result['selected_for_broker'] is None
    assert not result['broker_eligible']
    a['stages']['development']['review_passed']=False
    assert training_selection({'a':a,'b':b})['selected_for_forward_paper'] is None


def test_cached_predictions_must_match_the_replayed_quote_time_and_candle(tmp_path):
    import json
    from tools.research_smc_entries import PredictionReader
    now=pd.Timestamp('2026-11-13T12:00:00Z');bar=now-pd.Timedelta(minutes=5)
    quote={'bid':100.,'ask':100.1,'point':.01,'at':now.isoformat()}
    path=tmp_path/'predictions.jsonl';path.write_text(json.dumps({'now':now.isoformat(),'input_last_bar':bar.isoformat(),
        'quote':quote,'predictions':{'model':{'candidate':None,'stage':'waiting'}}})+'\n')
    reader=PredictionReader(path,'model')
    try:
        f=pd.DataFrame({'time':[bar]})
        assert reader(f,{},quote,now)['stage']=='waiting'
        with pytest.raises(ValueError,match='quote_or_time'):reader(f,{},dict(quote,bid=99.),now)
        with pytest.raises(ValueError,match='bar_changed'):reader(pd.DataFrame({'time':[bar-pd.Timedelta(minutes=5)]}),{},quote,now)
    finally:reader.close()


def test_shared_context_does_not_change_either_models_prediction(monkeypatch):
    from atlas_ai.strategies import smc_entry_models as module
    f,c,q=event_case();direct=[event_retest(f,c,q,NOW),sweep_reclaim(f,c,q,NOW)]
    original=module.context_observation;cache=[]
    def shared(*args):
        if not cache:cache.append(original(*args))
        return cache[0]
    monkeypatch.setattr(module,'context_observation',shared)
    assert [event_retest(f,c,q,NOW),sweep_reclaim(f,c,q,NOW)]==direct
