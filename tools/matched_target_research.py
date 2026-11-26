"""Cost-aware paired targets; isolated diagnostic, no live registration."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json
import math
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


def paired_target(stop,target,spec,slip):
    if not all(math.isfinite(x) and x>0 for x in (stop,target)) or not math.isfinite(slip) or slip<0:
        raise ValueError('finite_positive_distances_required')
    cash_loss=spec.point/spec.tick_size*spec.tick_value_loss
    cash_profit=spec.point/spec.tick_size*spec.tick_value_profit
    # Match replay risk budgeting, including two adverse slippage legs and fees.
    risk=stop*cash_loss+2*slip*cash_loss+spec.roundtrip_fee_per_lot
    needed=(2*risk+spec.roundtrip_fee_per_lot)/cash_profit+slip
    quantum=spec.tick_size/spec.point
    return math.ceil(max(target,needed)/quantum)*quantum


def run():
    source=ROOT/'storage/retest_capital_20261126T081720Z';setups=ROOT/'storage/complete_retest_setup_20261126T081014Z'
    old=signed(source,'protocol');baseline=signed(source,'report')
    assert baseline['protocol_sha256']==digest(source/'protocol.json')
    output=ROOT/'storage'/('matched_target_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));output.mkdir()
    protocol={'baseline_report_sha256':digest(source/'report.json'),'settings':old['settings'],'spec':old['spec'],
              'limits':old['limits'],'periods':old['periods'],'setup_hashes':old['setup_hashes'],
              'hypothesis':'Keep stops and existing management; targets must cover >=2 times stop-plus-modeled-friction risk, net of fees and exit slippage.',
              'spread':'Embedded in bid/ask quotes; never charged a second time.',
              'selection':'One fixed pairing rule, no tuning or search. Retrospective diagnostic on previously inspected periods.',
              'source_hashes':{str(p.relative_to(ROOT)):digest(p) for folder in ('atlas_ai','tools') for p in (ROOT/folder).rglob('*.py')},
              'orders_sent':0,'broker_eligible':False,'live_policy_changed':False}
    save_signed(output,'protocol',protocol)
    locations={'earlier':ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5','recent':ROOT/'storage/today_learning_replay_20261123_v2'}
    spec=BrokerSpec(**old['spec']);results={};original=AtlasTrader._strategy_to_setup_family
    def family(self,name):return 'continuation' if name==old['setup_name'] else original(self,name)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for name,(a,b) in old['periods'].items():
            path=locations[name]/'M5.csv';assert digest(path)==old['inputs'][name]['M5']
            assert digest(setups/(name+'_setups.json'))==old['setup_hashes'][name]
            frozen=signed(setups,name+'_setups')['rows'];contexts={r['available_at']:r['higher_context'] for r in frozen}
            frame=prepare_frame(pd.read_csv(path));frame['time']=pd.to_datetime(frame.time,utc=True);results[name]={}
            for lane,mult,slip in [('base',1,3),('stress',2,6)]:
                atomic_json(output/'progress.json',{'period':name,'lane':lane})
                rows=deepcopy(frozen)
                for row in rows:
                    for signal in row['signals']:
                        signal['take_profit_points']=paired_target(signal['stop_loss_points'],signal['take_profit_points'],spec,slip)
                save_signed(output,name+'_'+lane+'_setups',{'rows':rows})
                execution=frame.copy();execution['spread']=frame.spread.shift(1)*mult
                with tempfile.TemporaryDirectory() as temp,patch.object(AtlasTrader,'_strategy_to_setup_family',family),overlay(contexts,{}):
                    cfg=settings_for(old,temp)
                    stats=replay(execution,rows,cfg,spec,ExitVariant('configured',cfg.backtest_break_even_lock_r,slip),
                                 KnowledgeStore(temp),old['limits'],start=pd.Timestamp(a).to_pydatetime(),end=pd.Timestamp(b).to_pydatetime())
                save_signed(output,name+'_'+lane,stats)
                summary=summarize(stats,a,b)
                for key in ('return_fraction','max_drawdown'):summary.pop(key,None)
                if summary['active_entry_days']<2:summary['mean_net_r_day_block_bootstrap_95_interval']=None
                results[name][lane]={'baseline':{k:v for k,v in baseline['results'][name]['lanes'][lane].items()
                                               if k not in {'return_fraction','max_drawdown'}},'paired_targets':summary}
    passed=all(v['paired_targets']['trades']>=30 and (v['paired_targets']['mean_net_r'] or 0)>0
               and (v['paired_targets']['profit_factor'] or 0)>=1.1 and v['paired_targets']['max_drawdown_r']<=6
               for p in results.values() for v in p.values())
    report={'state':'completed_research_only','protocol_sha256':digest(output/'protocol.json'),'results':results,
            'qualified':passed,'orders_sent':0,'broker_eligible':False,'live_policy_changed':False,
            'limitations':baseline['limitations']+['Intended net 2R applies only if the target fills; early protective, stale and session exits can realize less.',
                'Cash conversion, costs and stop-first M5 replay are modeled; live gate parity is incomplete.']}
    save_signed(output,'report',report)
    (ROOT/'docs/MATCHED_TARGET_RESEARCH_20261126.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    atomic_json(output/'progress.json',{'state':'completed'});print(json.dumps(report),flush=True)


if __name__=='__main__':run()
