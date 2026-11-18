"""Outcome-independent volatility calibration audit and held-period comparison."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.trader import AtlasTrader
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.m5_proposal import matched_volatility,calibrate,volatility_policy
from atlas_ai.testing.policy_replay import replay
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.atomic_files import atomic_json
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.research_entry_horizon import load_frames
from tools.m5_stop_research import review


def main():
    root=Path(__file__).resolve().parents[1]
    source=root/'storage/m5_calibration_20261116_v3'
    sp,old=signed(source,'protocol'),signed(source,'calibration')
    if old['protocol_sha256']!=digest(source/'protocol.json'):raise ValueError('calibration_protocol_changed')
    hashes=signed(source,'inputs');frames={}
    for tf in ['M1','M5']:
        if digest(source/(tf+'.csv'))!=hashes[tf]:raise ValueError('calibration_input_changed')
        frames[tf]=pd.read_csv(source/(tf+'.csv'))
    pairs=matched_volatility(frames['M1'],frames['M5'])
    calibration=calibrate(pairs,pd.Timestamp(sp['development_start']),pd.Timestamp(sp['split']))
    for key in ['scale','elevated_pct','extreme_pct','pairs','dates']:
        if abs(calibration[key]-old[key])>1e-12:raise ValueError('calibration_not_reproduced')
    reference=root/'storage/demo_representative_m5_primary_20261118'
    p,r=signed(reference,'protocol'),signed(reference,'report')
    if r['protocol_sha256']!=digest(reference/'protocol.json') or r['candidates_sha256']!=digest(reference/'candidates.json'):raise ValueError('matched_reference_changed')
    data=root/'storage/smc_entry_rerun_20261116/smc_event_retest_v5'
    f=load_frames(data,p['input_hashes'])['M5']
    start,end=pd.Timestamp(sp['split']),pd.Timestamp(sp['validation_end'])
    cache=[row for row in signed(reference,'candidates')['corrected'] if start<=pd.Timestamp(row['available_at'])<end]
    output=root/'storage/m5_volatility_isolation_20261118';output.mkdir(exist_ok=False)
    coverage={}
    for label,begin,finish in [('calibration',pd.Timestamp(sp['development_start']),start),('validation',start,end)]:
        sample=pairs[(pairs.index>=begin)&(pairs.index<finish)].m5
        coverage[label]={'valid_paired_windows':len(sample),'median_M5_pct':float(sample.median()),
            'current_extreme_fraction':float((sample>=.07).mean()),'scaled_extreme_fraction':float((sample>=calibration['extreme_pct']).mean()),
            'screenshot_value_percentile':float((sample<=.0735).mean())}
    protocol={**p,'experiment':'volatility_boundary_only_on_corrected_geometry','validation_period':[start.isoformat(),end.isoformat()],
        'calibration':calibration,'coverage':coverage,'calibration_sha256':digest(source/'calibration.json'),
        'comparison_source_report_sha256':digest(reference/'report.json'),'no_parameter_search':True,
        'live_policy_changed':False,'broker_eligible':False,'orders_sent':0}
    save_signed(output,'protocol',protocol);save_signed(output,'candidates',{'rows':cache})
    def progress(**kw):atomic_json(output/'progress.json',kw)
    execution=f.copy();execution['spread']=execution.spread.shift(1)
    results={}
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny),tempfile.TemporaryDirectory() as temp:
        cfg=settings_for(protocol,temp)
        for lane in ['current_boundaries','M5_scaled_boundaries']:
            progress(stage='portfolio_replay',lane=lane,candidate_bars=len(cache))
            def evaluate():
                return replay(execution,cache,cfg,BrokerSpec(**p['spec']),ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),
                    KnowledgeStore(temp),p['limits'],start=start.to_pydatetime(),end=end.to_pydatetime(),
                    audit=lambda row:progress(stage='portfolio_replay',lane=lane,bar=row['index']) if row['index']%500==0 else None)
            if lane=='M5_scaled_boundaries':
                with patch.object(AtlasTrader,'_volatility_safety_state',lambda self,*,context_snapshot,regime:volatility_policy(context_snapshot,regime,calibration)):
                    stats=evaluate()
            else:stats=evaluate()
            stats['review']=review(stats);results[lane]=stats;save_signed(output,lane+'_checkpoint',stats)
        report={'state':'completed_volatility_isolation','results':results,'coverage':coverage,'calibration':calibration,
            'protocol_sha256':digest(output/'protocol.json'),'candidates_sha256':digest(output/'candidates.json'),
            'live_policy_changed':False,'broker_eligible':False,'orders_sent':0,'full_live_parity':False,
            'note':'Previously inspected retrospective validation; frozen costs and R100000 virtual capital. No automatic activation.'}
        save_signed(output,'report',report);progress(state=report['state'])
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))


if __name__=='__main__':main()
