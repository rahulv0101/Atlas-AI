"""Full frozen candidate-stream ATR geometry comparison; no broker authority."""
import argparse
from dataclasses import asdict
from pathlib import Path
import json
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.models import TradeSignal
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.distance_units import corrected_atr_signal
from atlas_ai.testing.policy_replay import cache_candidates,replay
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from tools.research_entry_horizon import load_frames
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.deployed_m5_parity import MISSING,completeness


def corrected_rows(rows,frame,point):
    volatility=atr(frame)
    return [{**row,'signals':[asdict(corrected_atr_signal(TradeSignal(**s),float(volatility.iloc[row['index']]),point)) for s in row['signals']]} for row in rows]


def run(period,output):
    root=Path(__file__).resolve().parents[1]
    source=root/'storage/deployed_m5_parity_20261117T205724Z'
    prior=signed(source,'protocol');control=signed(source,'report')
    if control['protocol_sha256']!=digest(source/'protocol.json') or control['candidate_receipt_sha256']!=digest(source/'candidates.json'):
        raise ValueError('reference_changed')
    if prior['settings']['timeframe']!='M5':raise ValueError('M5_required')
    for name,expected in prior['source_hashes'].items():
        if name.replace('\\','/').startswith('atlas_ai/') and digest(root/name)!=expected:raise ValueError('shared_policy_changed')
    data=root/('storage/smc_entry_rerun_20261116/smc_event_retest_v5' if period=='primary' else 'storage/m5_stop_research_20261114')
    hashes=prior['historical_inputs'] if period=='primary' else signed(data,'inputs')['hashes']
    frames=load_frames(data,hashes)
    output.resolve().relative_to((root/'storage').resolve());output.mkdir(exist_ok=False)
    sources={str(p.relative_to(root)):digest(p) for p in [Path(__file__).resolve(),root/'atlas_ai/strategies/distance_units.py',root/'atlas_ai/testing/policy_replay.py',root/'atlas_ai/trader.py']}
    for name in sources:
        target=output/'frozen_source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((root/name).read_bytes())
    protocol={'period':period,'settings':prior['settings'],'spec':prior['broker_spec'],'limits':prior['limits'],
        'input_hashes':hashes,'source_hashes':sources,'virtual_capital':prior['settings']['backtest_initial_balance'],
        'comparison':'unchanged_vs_existing_ATR_price_to_points_adapter; no_parameter_search',
        'interpretation':'Primary motivated repair; April disjoint but already inspected, not blind validation. Frozen past broker conversion, costs and limits.',
        'reference_report_sha256':digest(source/'report.json'),**completeness(MISSING),
        'orders_sent':0,'broker_eligible':False,'live_policy_changed':False}
    save_signed(output,'protocol',protocol)
    def progress(**kw):atomic_json(output/'progress.json',kw)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny),tempfile.TemporaryDirectory() as temp:
        cfg=settings_for(protocol,temp);store=KnowledgeStore(temp)
        if period=='primary':rows=signed(source,'candidates')['rows']
        else:
            rows,_,_=cache_candidates(frames['M5'],cfg,store,progress,native_frames=frames)
            rows=[r for r in rows if pd.Timestamp('2026-04-01T00:00Z')<=pd.Timestamp(r['available_at'])<pd.Timestamp('2026-05-01T00:00Z')]
        transformed=corrected_rows(rows,frames['M5'],protocol['spec']['point'])
        save_signed(output,'candidates',{'original':rows,'corrected':transformed})
        execution=frames['M5'].copy();execution['spread']=execution.spread.shift(1)
        result={}
        if period=='primary':result['unchanged']=control['diagnostic']
        for name,cache in [('unchanged',rows),('corrected',transformed)]:
            if name in result:continue
            progress(stage='portfolio_replay',variant=name,candidate_bars=len(cache))
            def audit(row):
                if row['index']%500==0:progress(stage='portfolio_replay',variant=name,bar=row['index'])
            result[name]=replay(execution,cache,cfg,BrokerSpec(**protocol['spec']),ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),
                KnowledgeStore(temp),protocol['limits'],audit=audit,
                end=pd.Timestamp('2026-05-01T00:00Z').to_pydatetime() if period=='separate' else None)
            save_signed(output,name+'_checkpoint',result[name])
        report={'state':'completed_partial_parity_comparison','results':result,'candidate_bars':len(rows),
            'protocol_sha256':digest(output/'protocol.json'),'candidates_sha256':digest(output/'candidates.json'),
            **completeness(MISSING),'orders_sent':0,'broker_eligible':False,'live_policy_changed':False}
        save_signed(output,'report',report);progress(state=report['state'])
    print(str(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--period',choices=['primary','separate'],required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.period,args.output)
