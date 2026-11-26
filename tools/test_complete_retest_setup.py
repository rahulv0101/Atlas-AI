"""One frozen H1/M5 setup, offline research only. No live registration."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.config.settings import load_settings
from atlas_ai.data.top_down import POLICY, closed_bars
from atlas_ai.data.timeframe_bias import bias_from_closes
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.strategies.indicators import atr
from atlas_ai.testing.h1_m5_retest_timing import RULES, verify, overlay
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from atlas_ai.testing.policy_replay import replay, policy_trader
from atlas_ai.trader import AtlasTrader
from atlas_ai.atomic_files import atomic_json
from tools.learn_candidate_ranker import signed, save_signed, digest, deny
from tools.guarded_research_audit import safe_settings
from tools.cost_aware_strategy_audit import prepare_frame
from tools.trading_edge_audit import summarize

ROOT=Path(__file__).resolve().parents[1]
NAME='research_h1_m5_first_retest'


def generate(frame,h1,cfg,start,end,progress):
    rows=[];counts=Counter();context={};key=None;trader=policy_trader(cfg,None)
    for i in range(250,len(frame)-1):
        now=pd.Timestamp(frame.time.iloc[i])+pd.Timedelta(minutes=5)
        if not start<=now<end:continue
        if pd.Timestamp(frame.time.iloc[i+1])!=now:counts['missing_next_bar']+=1;continue
        if key!=now.floor('h'):
            key=now.floor('h')
            try:
                history=closed_bars(h1,'H1',now)
                side=bias_from_closes(history.close)
                context={'policy':POLICY,'entry_timeframe':'M5','closed_candles_only':True,
                         'evaluated_at':now.isoformat(),'details':{'H1':side},
                         'evidence':{'H1':{'status':'available','last_closed_bar_utc':history.time.iloc[-1].isoformat()}}}
            except ValueError:context={};side='unknown'
        side=context.get('details',{}).get('H1','unknown')
        if side not in {'buy','sell'}:counts['no_directional_H1']+=1;continue
        context={**context,'evaluated_at':now.isoformat()}
        window=frame.iloc[max(0,i-59):i+1]
        evidence=verify(window,context,side,now)
        counts[evidence['reason']]+=1
        if evidence['passed']:
            distance=1.5*float(atr(window).iloc[-1])/cfg.backtest_point_size
            rows.append({'index':i,'available_at':now.isoformat(),
                         'signals':[{'strategy':NAME,'side':side,'confidence':.7,
                                     'stop_loss_points':distance,'take_profit_points':2*distance}],
                         'regime':trader._market_regime(list(window.close.tail(60))),
                         'higher_tf_bias':side,'higher_context':deepcopy(context),'setup_evidence':evidence})
        if i%500==0:progress(stage='setup_scan',bar=i,bars=len(frame),setups=len(rows))
    return rows,dict(counts)


def run():
    cfg=load_settings()
    assert cfg.timeframe=='M5' and cfg.top_down_confluence_enabled
    source=ROOT/'storage/today_learning_replay_20261123_v2'
    recent=signed(source,'protocol');recent_inputs=signed(source,'inputs')
    receipt=signed(ROOT/'storage/m5_ema_stop_only_20261124_v2','prediction_receipt')
    sets={'earlier':(ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',
                     receipt['data_hashes']['discovery'],'2026-10-15T08:10Z','2026-11-14T08:10Z'),
          'recent':(source,recent_inputs,'2026-11-16T00:00Z',recent['end_utc'])}
    output=ROOT/'storage'/('complete_retest_setup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir()
    automation=json.loads((Path(cfg.storage_dir)/'automation_state.json').read_text());automation=automation.get('payload',automation)
    s,p=automation['session_control'],automation['tiny_live_pilot']
    limits={'day_trades':min(s['daily_trade_limit'],p['max_trades_per_day']),
            'loss_streak':min(s['consecutive_loss_limit'],p['max_consecutive_losses']),
            'daily_loss_percent':p['daily_loss_cap'],'lot_cap':p['size_cap'],'setup_family':p['allowed_setup_family']}
    protocol={'rules':RULES,'setup_name':NAME,'stop':'1.5 closed-M5 ATR, frozen distance at confirmation',
              'target':'2R','entry':'Next M5 open after confirmation; no forming-candle inputs.',
              'settings':safe_settings(cfg),'spec':recent['spec'],'limits':limits,
              'periods':{k:[a,b] for k,(_,_,a,b) in sets.items()},
              'inputs':{k:h for k,(_,h,_,_) in sets.items()},
              'research_adapters':['Custom strategy classified as continuation for the isolated replay only.',
                 'Verified structural retest supplies fresh_retest / turning to shared timing analysis.'],
              'criteria':'Each period >=30 trades, positive net expectancy, PF>=1.1, drawdown<=6R in base and cost stress.',
              'costs':'Base: lagged recorded spread and 3 adverse points per side. Stress: double spread and 6 points per side. Prior broker-unit/fee snapshot.',
              'source_hashes':{str(path.relative_to(ROOT)):digest(path) for folder in ('atlas_ai','tools') for path in (ROOT/folder).rglob('*.py')},
              'no_parameter_search':True,'orders_sent':0,'broker_eligible':False,'live_policy_changed':False}
    save_signed(output,'protocol',protocol)
    def progress(**row):atomic_json(output/'progress.json',row)
    results={};original=AtlasTrader._strategy_to_setup_family
    def family(self,name):return 'continuation' if name==NAME else original(self,name)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for name,(directory,hashes,a,b) in sets.items():
            frames={}
            for tf in ('M5','H1'):
                path=directory/(tf+'.csv')
                if digest(path)!=hashes[tf]:raise ValueError('input_changed:'+tf)
                frames[tf]=prepare_frame(pd.read_csv(path));frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
            start,end=pd.Timestamp(a),pd.Timestamp(b)
            rows,counts=generate(frames['M5'],frames['H1'],cfg,start,end,progress)
            save_signed(output,name+'_setups',{'rows':rows,'counts':counts})
            contexts={r['available_at']:r['higher_context'] for r in rows};results[name]={'setup_count':len(rows),'scan_counts':counts,'lanes':{}}
            for lane,mult,slip in [('base',1,3),('stress',2,6)]:
                progress(stage='replay',period=name,lane=lane,setups=len(rows))
                execution=frames['M5'].copy();execution['spread']=execution.spread.shift(1)*mult
                with tempfile.TemporaryDirectory() as temp,patch.object(AtlasTrader,'_strategy_to_setup_family',family),overlay(contexts,{}):
                    isolated=replace(cfg,execute_trades=False,storage_dir=temp,gemini_api_key='',openai_api_key='')
                    stats=replay(execution,deepcopy(rows),isolated,BrokerSpec(**protocol['spec']),
                                 ExitVariant('configured',cfg.backtest_break_even_lock_r,slip),KnowledgeStore(temp),limits,
                                 start=start.to_pydatetime(),end=end.to_pydatetime())
                save_signed(output,name+'_'+lane,stats)
                results[name]['lanes'][lane]=summarize(stats,start,end)
            save_signed(output,'checkpoint',results)
    qualified=all(v['trades']>=30 and v['mean_net_r']>0 and (v['profit_factor'] or 0)>=1.1 and v['max_drawdown_r']<=6
                  for period in results.values() for v in period['lanes'].values())
    report={'state':'completed_research_only','protocol_sha256':digest(output/'protocol.json'),'results':results,
            'qualified':qualified,'full_live_policy_parity':False,'orders_sent':0,'live_policy_changed':False,'broker_eligible':False,
            'limitations':['Reused retrospective archives, not untouched validation or forward evidence.',
                'One synthetic setup, with explicit research-only timing and family adapters; no built-in strategy results are relabelled.',
                'Unavailable macro, visual, adaptive state, approvals and ExecutionGate prevent full live-system parity.',
                'M5 OHLC stop-first execution; frozen ATR distance applied at next-open fill, not exact absolute structural invalidation.',
                'Prior broker conversion/margin/fees are approximations; costs are not calibrated natural fills.']}
    save_signed(output,'report',report)
    (ROOT/'docs/COMPLETE_RETEST_SETUP_20261126.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    progress(stage='completed');print(json.dumps(report),flush=True)


if __name__=='__main__':run()
