"""Replay the identical frozen setup stream with current demo starting capital."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.config.settings import load_settings
from atlas_ai.data.market_data import MarketDataFeed
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.h1_m5_retest_timing import overlay
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.policy_replay import replay
from atlas_ai.atomic_files import atomic_json
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny
from tools.cost_aware_strategy_audit import prepare_frame
from tools.trading_edge_audit import summarize

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'storage/complete_retest_setup_20261126T081014Z'


def capture_capital():
    cfg=load_settings()
    with patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        try:
            MarketDataFeed(cfg)._ensure_initialized()
            a=mt5.account_info()
            if not a or a.login!=cfg.hfm_login or a.server!=cfg.hfm_server or a.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
                raise ValueError('matching_configured_demo_required')
            if a.currency!='ZAR' or not math.isfinite(a.balance) or a.balance<=0:
                raise ValueError('positive_ZAR_demo_capital_required_for_frozen_cash_units')
            return {'balance':float(a.balance),'currency':a.currency,
                    'captured_at':datetime.now(timezone.utc).isoformat(),'demo':True}
        finally:mt5.shutdown()


def run():
    before=signed(SOURCE,'protocol');baseline=signed(SOURCE,'report')
    if baseline['protocol_sha256']!=digest(SOURCE/'protocol.json'):raise ValueError('baseline_protocol_changed')
    for name,expected in before['source_hashes'].items():
        if digest(ROOT/name)!=expected:raise ValueError('source_changed:'+name)
    capital=capture_capital()
    output=ROOT/'storage'/('retest_capital_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));output.mkdir()
    protocol=deepcopy(before)
    protocol.update(capital_snapshot=capital,change='Only virtual starting balance changes; no deposit booked as profit.',
                    baseline_report_sha256=digest(SOURCE/'report.json'),
                    setup_hashes={n:digest(SOURCE/(n+'_setups.json')) for n in before['periods']},
                    runner_sha256=digest(Path(__file__)))
    protocol['settings']['backtest_initial_balance']=capital['balance']
    save_signed(output,'protocol',protocol)
    locations={'earlier':ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',
               'recent':ROOT/'storage/today_learning_replay_20261123_v2'}
    results={};original=AtlasTrader._strategy_to_setup_family
    def family(self,name):return 'continuation' if name==before['setup_name'] else original(self,name)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for name,(a,b) in before['periods'].items():
            path=locations[name]/'M5.csv'
            if digest(path)!=before['inputs'][name]['M5']:raise ValueError('candles_changed')
            setups=signed(SOURCE,name+'_setups');rows=setups['rows']
            if digest(SOURCE/(name+'_setups.json'))!=protocol['setup_hashes'][name]:raise ValueError('setups_changed')
            frame=prepare_frame(pd.read_csv(path));frame['time']=pd.to_datetime(frame.time,utc=True)
            contexts={r['available_at']:r['higher_context'] for r in rows}
            results[name]={'setup_count':len(rows),'lanes':{}}
            for lane,mult,slip in [('base',1,3),('stress',2,6)]:
                atomic_json(output/'progress.json',{'period':name,'lane':lane})
                execution=frame.copy();execution['spread']=execution.spread.shift(1)*mult
                with tempfile.TemporaryDirectory() as temp,patch.object(AtlasTrader,'_strategy_to_setup_family',family),overlay(contexts,{}):
                    cfg=settings_for(protocol,temp)
                    stats=replay(execution,deepcopy(rows),cfg,BrokerSpec(**before['spec']),
                                 ExitVariant('configured',cfg.backtest_break_even_lock_r,slip),KnowledgeStore(temp),before['limits'],
                                 start=pd.Timestamp(a).to_pydatetime(),end=pd.Timestamp(b).to_pydatetime())
                save_signed(output,name+'_'+lane,stats)
                results[name]['lanes'][lane]=summarize(stats,a,b)
    report={'state':'completed_research_only','protocol_sha256':digest(output/'protocol.json'),'results':results,
            'qualified':all(v['trades']>=30 and (v['mean_net_r'] or 0)>0 and (v['profit_factor'] or 0)>=1.1 and v['max_drawdown_r']<=6
                            for p in results.values() for v in p['lanes'].values()),
            'capital_basis':'Matching configured demo balance captured now, used as hypothetical capital at each historical period start. No cash flow simulated.',
            'only_changed_parameter':'backtest_initial_balance','full_live_policy_parity':False,'orders_sent':0,
            'live_policy_changed':False,'broker_eligible':False,'limitations':baseline['limitations']+
                ['Current capital is a hypothetical historical starting balance, not the historical balance.',
                 'The unchanged 0.01-lot pilot cap may prevent larger capital from increasing position size.']}
    save_signed(output,'report',report)
    portable=deepcopy(report)
    for period in portable['results'].values():
        for lane in period['lanes'].values():lane.pop('return_fraction',None);lane.pop('max_drawdown',None)
    (ROOT/'docs/RETEST_CAPITAL_RERUN_20261126.json').write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    atomic_json(output/'progress.json',{'state':'completed'})
    print(json.dumps({'virtual_starting_balance':capital['balance'],'report':portable}),flush=True)


if __name__=='__main__':run()
