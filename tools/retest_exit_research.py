"""One predeclared exit-management hypothesis; no live policy edits."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
import json
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.h1_m5_retest_timing import overlay
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import replay
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.cost_aware_strategy_audit import prepare_frame
from tools.trading_edge_audit import summarize

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'storage/retest_capital_20261126T081720Z'
SETUPS=ROOT/'storage/complete_retest_setup_20261126T081014Z'


def hypothesis(settings):
    # With the unchanged 2R target, reaching 2R exits the trade first.
    # This defers only break-even/trailing; initial protection and time exits remain.
    return replace(settings,backtest_break_even_r_trigger=2.,backtest_trailing_r_trigger=2.)


def run():
    previous=signed(SOURCE,'protocol');old_report=signed(SOURCE,'report')
    assert old_report['protocol_sha256']==digest(SOURCE/'protocol.json')
    periods={'october':('earlier','2026-10-15T08:10Z','2026-11-01T00:00Z'),
             'november_early':('earlier','2026-11-01T00:00Z','2026-11-14T08:10Z'),
             'november_recent':('recent','2026-11-16T00:00Z','2026-11-23T16:25Z')}
    output=ROOT/'storage'/('retest_exit_research_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));output.mkdir()
    protocol={'baseline_protocol_sha256':digest(SOURCE/'protocol.json'),
              'hypothesis':'Defer break-even and trailing until the unchanged 2R target; retain initial 1.5ATR stop, stale exit, session cutoff, sizing and risk gates.',
              'settings':previous['settings'],'spec':previous['spec'],'limits':previous['limits'],
              'periods':periods,'setup_hashes':previous['setup_hashes'],
              'selection':'Exactly one fixed alternative, no sweep or optimization. October is reused discovery; November blocks are disjoint, previously inspected validation.',
              'criteria':'Improve mean net R against freshly rerun baseline in every block under base/stress costs, positive expectancy, PF>=1.1 and drawdown<=6R; >=30 trades per block before qualification.',
              'source_hashes':{str(p.relative_to(ROOT)):digest(p) for folder in ('atlas_ai','tools') for p in (ROOT/folder).rglob('*.py')},
              'live_policy_changed':False,'orders_sent':0,'broker_eligible':False}
    save_signed(output,'protocol',protocol)
    locations={'earlier':ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',
               'recent':ROOT/'storage/today_learning_replay_20261123_v2'}
    results={};original=AtlasTrader._strategy_to_setup_family
    def family(self,name):return 'continuation' if name==previous['setup_name'] else original(self,name)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for period,(dataset,a,b) in periods.items():
            path=locations[dataset]/'M5.csv'
            assert digest(path)==previous['inputs'][dataset]['M5']
            assert digest(SETUPS/(dataset+'_setups.json'))==previous['setup_hashes'][dataset]
            frame=prepare_frame(pd.read_csv(path));frame['time']=pd.to_datetime(frame.time,utc=True)
            rows=signed(SETUPS,dataset+'_setups')['rows'];contexts={r['available_at']:r['higher_context'] for r in rows}
            results[period]={}
            for cost,mult,slip in [('base',1,3),('stress',2,6)]:
                results[period][cost]={}
                for lane in ('baseline','deferred_protection'):
                    atomic_json(output/'progress.json',{'period':period,'cost':cost,'lane':lane})
                    execution=frame.copy();execution['spread']=frame.spread.shift(1)*mult
                    with tempfile.TemporaryDirectory() as temp,patch.object(AtlasTrader,'_strategy_to_setup_family',family),overlay(contexts,{}):
                        cfg=settings_for(previous,temp)
                        if lane!='baseline':cfg=hypothesis(cfg)
                        stats=replay(execution,deepcopy(rows),cfg,BrokerSpec(**previous['spec']),
                            ExitVariant('configured',cfg.backtest_break_even_lock_r,slip),KnowledgeStore(temp),previous['limits'],
                            start=pd.Timestamp(a).to_pydatetime(),end=pd.Timestamp(b).to_pydatetime())
                    save_signed(output,period+'_'+cost+'_'+lane,stats)
                    summary=summarize(stats,a,b)
                    for key in ('return_fraction','max_drawdown'):summary.pop(key,None)
                    if summary['active_entry_days']<2:summary['mean_net_r_day_block_bootstrap_95_interval']=None
                    # Trade presence and profitable days are separate measures.
                    daily={day.date().isoformat():0. for day in pd.date_range(pd.Timestamp(a).normalize(),pd.Timestamp(b).normalize(),freq='B')
                           if day<pd.Timestamp(b)}
                    for t in stats['trade_list']:
                        day=pd.Timestamp(t['exit_at']).date().isoformat();daily[day]=daily.get(day,0)+t['net_cash']
                    summary['daily']={'weekdays':len(daily),'profitable_days':sum(v>0 for v in daily.values()),
                                      'losing_days':sum(v<0 for v in daily.values()),'flat_days':sum(v==0 for v in daily.values())}
                    results[period][cost][lane]=summary
            save_signed(output,'checkpoint',results)
    improved=all((v['deferred_protection']['mean_net_r'] or -100)>(v['baseline']['mean_net_r'] or -100)
                 for p in results.values() for v in p.values())
    qualified=improved and all(v['deferred_protection']['trades']>=30 and (v['deferred_protection']['mean_net_r'] or 0)>0
                   and (v['deferred_protection']['profit_factor'] or 0)>=1.1 and v['deferred_protection']['max_drawdown_r']<=6
                   for p in results.values() for v in p.values())
    report={'state':'completed_research_only','protocol_sha256':digest(output/'protocol.json'),'results':results,
            'improved_in_every_block_and_cost_lane':improved,'qualified':qualified,'live_policy_changed':False,
            'orders_sent':0,'broker_eligible':False,'full_live_policy_parity':False,
            'limitations':old_report['limitations']+['Exit counterfactual replays portfolio occupancy; it does not just relabel old fills.',
               'Daily figures are modeled realized P/L, not a daily-profit guarantee. Flat days include no-exit days.',
               'Previously inspected archives; a positive result cannot substitute for prospective evidence.']}
    save_signed(output,'report',report)
    (ROOT/'docs/RETEST_EXIT_RESEARCH_20261126.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    atomic_json(output/'progress.json',{'state':'completed'});print(json.dumps(report),flush=True)


if __name__=='__main__':run()
