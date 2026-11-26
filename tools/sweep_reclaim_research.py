"""One fixed H1-directed M5 sweep/reclaim design; offline only."""
from collections import Counter
from contextlib import contextmanager
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
from atlas_ai.data.top_down import closed_bars,POLICY
from atlas_ai.data.timeframe_bias import bias_from_closes
from atlas_ai.strategies.indicators import atr
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.h1_m5_retest_timing import overlay as retest_overlay
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import replay,policy_trader
from tools.matched_target_research import paired_target
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.cost_aware_strategy_audit import prepare_frame
from tools.trading_edge_audit import summarize
ROOT=Path(__file__).resolve().parents[1]
NAME='research_h1_m5_sweep_reclaim'
RULES={'level_lookback':20,'sweep_min_ATR':.05,'sweep_wick_fraction':.5,
       'confirmation_body_fraction':.5,'confirmation':'Separate next closed M5 candle closes beyond sweep candle opposite extreme.',
       'direction':'Closed H1 10/30-close bias must agree.',
       'stop':'1.5 closed-M5 ATR; unchanged from control','target':'Cost-aware >=2R; identical rule in control',
       'holding_and_gates':'Existing exit management, session, pilot and risk policies unchanged.'}


def pattern(window,side,now):
    if side not in {'buy','sell'}:return None
    try:
        f=closed_bars(window,'M5',now).tail(60).reset_index(drop=True)
        times=pd.to_datetime(f.time,utc=True)
        if times.iloc[-1]+pd.Timedelta(minutes=5)!=pd.Timestamp(now) or not times.tail(22).diff().dropna().eq(pd.Timedelta(minutes=5)).all():return None
        for k in ('open','high','low','close'):
            if not f[k].map(lambda v:math.isfinite(float(v)) and float(v)>0).all():return None
        if ((f.high<f[['open','close','low']].max(axis=1)) | (f.low>f[['open','close','high']].min(axis=1))).any():return None
        prior,sweep,confirm=f.iloc[-22:-2],f.iloc[-2],f.iloc[-1]
        volatility=float(atr(f).iloc[-3]);span=float(sweep.high-sweep.low);bodyspan=float(confirm.high-confirm.low)
        if volatility<=0 or span<=0 or bodyspan<=0:return None
        if side=='buy':
            level=float(prior.low.min());wick=float(min(sweep.open,sweep.close)-sweep.low)
            passed=(sweep.low<level-.05*volatility and sweep.close>level and wick>=.5*span
                    and confirm.close>confirm.open and confirm.close> sweep.high
                    and confirm.close-confirm.open>=.5*bodyspan)
        else:
            level=float(prior.high.max());wick=float(sweep.high-max(sweep.open,sweep.close))
            passed=(sweep.high>level+.05*volatility and sweep.close<level and wick>=.5*span
                    and confirm.close<confirm.open and confirm.close<sweep.low
                    and confirm.open-confirm.close>=.5*bodyspan)
        if not passed:return None
        return {'side':side,'level':level,'sweep_at':times.iloc[-2].isoformat(),
                'confirmation_at':times.iloc[-1].isoformat(),'available_at':pd.Timestamp(now).isoformat(),
                'ATR':float(atr(f).iloc[-1]),'authority':'research_only'}
    except (ValueError,TypeError,KeyError,IndexError):return None


def generate(frame,h1,cfg,start,end,progress):
    rows=[];counts=Counter();key=None;context={};trader=policy_trader(cfg,None)
    for i in range(250,len(frame)-1):
        now=pd.Timestamp(frame.time.iloc[i])+pd.Timedelta(minutes=5)
        if not start<=now<end:continue
        if frame.time.iloc[i+1]!=now:counts['next_bar_gap']+=1;continue
        if key!=now.floor('h'):
            key=now.floor('h')
            try:
                history=closed_bars(h1,'H1',now);side=bias_from_closes(history.close)
                context={'policy':POLICY,'entry_timeframe':'M5','closed_candles_only':True,
                         'details':{'H1':side},'evidence':{'H1':{'status':'available'}}}
            except ValueError:context={}
        side=context.get('details',{}).get('H1','unknown')
        if side not in {'buy','sell'}:counts['no_H1_direction']+=1;continue
        evidence=pattern(frame.iloc[i-59:i+1],side,now)
        if evidence:
            stop=1.5*evidence['ATR']/cfg.backtest_point_size
            rows.append({'index':i,'available_at':now.isoformat(),
                'signals':[{'strategy':NAME,'side':side,'confidence':.7,'stop_loss_points':stop,'take_profit_points':2*stop}],
                'regime':trader._market_regime(list(frame.close.iloc[i-59:i+1])),
                'higher_tf_bias':side,'higher_context':{**context,'evaluated_at':now.isoformat()},'sweep_evidence':evidence})
        if i%500==0:progress(stage='sweep_scan',bar=i,bars=len(frame),setups=len(rows))
    return rows,dict(counts)


@contextmanager
def sweep_overlay(rows):
    evidence={(r['available_at'],r['signals'][0]['side']):r['sweep_evidence'] for r in rows}
    original=AtlasTrader._derive_runtime_chart_features
    def derive(self,*,df,chosen,regime):
        base=original(self,df=df,chosen=chosen,regime=regime)
        now=pd.Timestamp(df.time.iloc[-1]);now=now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
        proof=evidence.get(((now+pd.Timedelta(minutes=5)).isoformat(),chosen.side))
        if chosen.strategy!=NAME or proof is None:return base
        return {**base,'location_state':'structure_reclaim','momentum_state':'turning','structural_timing_evidence':proof}
    with patch.object(AtlasTrader,'_derive_runtime_chart_features',derive):yield


def run():
    source=ROOT/'storage/retest_capital_20261126T081720Z';old=signed(source,'protocol')
    prior=sorted((ROOT/'storage').glob('h1_entry_quality_*'))[-1]
    prior_report=signed(prior,'report');prior_protocol=signed(prior,'protocol')
    assert prior_report['protocol_sha256']==digest(prior/'protocol.json')
    sets={'earlier':ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',
          'recent':ROOT/'storage/today_learning_replay_20261123_v2','additional_april':ROOT/'storage/m5_stop_research_20261114'}
    output=ROOT/'storage'/('sweep_reclaim_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));output.mkdir()
    protocol={'rules':RULES,'periods':prior_protocol['periods'],'settings':old['settings'],'spec':old['spec'],'limits':old['limits'],
        'inputs':prior_protocol['inputs'],'control':'Unchanged first-retest entry; cost-aware pairing in both lanes.',
        'criteria':'Every period and cost lane >=30 trades, positive mean net R, PF>=1.1 and drawdown<=6R; expectancy improvement over control.',
        'no_parameter_search':True,'source_hashes':{str(p.relative_to(ROOT)):digest(p) for folder in ('atlas_ai','tools') for p in (ROOT/folder).rglob('*.py')},
        'data_scope':'Previously inspected archives. One predeclared design; no blind validation or fresh demo evidence.',
        'orders_sent':0,'broker_eligible':False}
    save_signed(output,'protocol',protocol)
    def progress(**r):atomic_json(output/'progress.json',r)
    results={};spec=BrokerSpec(**old['spec']);original=AtlasTrader._strategy_to_setup_family
    def family(self,name):return 'continuation' if name in {NAME,old['setup_name']} else original(self,name)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for period,directory in sets.items():
            a,b=protocol['periods'][period];frames={}
            for tf in ('M5','H1'):
                path=directory/(tf+'.csv');assert digest(path)==protocol['inputs'][period][tf]
                frames[tf]=prepare_frame(pd.read_csv(path));frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
            with tempfile.TemporaryDirectory() as temp:
                rows,counts=generate(frames['M5'],frames['H1'],settings_for(old,temp),pd.Timestamp(a),pd.Timestamp(b),progress)
            control=signed(prior,period+'_setups')['baseline']
            save_signed(output,period+'_setups',{'control':control,'sweep_reclaim':rows,'counts':counts})
            results[period]={'control_setups':len(control),'sweep_setups':len(rows),'lanes':{}}
            for cost,mult,slip in [('base',1,3),('stress',2,6)]:
                results[period]['lanes'][cost]={}
                for lane,signals in [('control',control),('sweep_reclaim',rows)]:
                    progress(stage='replay',period=period,cost=cost,lane=lane)
                    frozen=deepcopy(signals)
                    for row in frozen:
                        for s in row['signals']:s['take_profit_points']=paired_target(s['stop_loss_points'],s['take_profit_points'],spec,slip)
                    contexts={r['available_at']:r['higher_context'] for r in frozen}
                    execution=frames['M5'].copy();execution['spread']=execution.spread.shift(1)*mult
                    adapter=sweep_overlay(frozen) if lane=='sweep_reclaim' else retest_overlay(contexts,{})
                    with tempfile.TemporaryDirectory() as temp,patch.object(AtlasTrader,'_strategy_to_setup_family',family),adapter:
                        cfg=settings_for(old,temp)
                        stats=replay(execution,frozen,cfg,spec,ExitVariant('configured',cfg.backtest_break_even_lock_r,slip),
                            KnowledgeStore(temp),old['limits'],start=pd.Timestamp(a).to_pydatetime(),end=pd.Timestamp(b).to_pydatetime())
                    save_signed(output,period+'_'+cost+'_'+lane,stats)
                    summary=summarize(stats,a,b)
                    for key in ('return_fraction','max_drawdown'):summary.pop(key,None)
                    if summary['active_entry_days']<2:summary['mean_net_r_day_block_bootstrap_95_interval']=None
                    results[period]['lanes'][cost][lane]=summary
            save_signed(output,'checkpoint',results)
    failures=[]
    for p,v in results.items():
        for cost,lanes in v['lanes'].items():
            c,base=lanes['sweep_reclaim'],lanes['control'];reasons=[]
            if c['trades']<30:reasons.append('insufficient_trades')
            if (c['mean_net_r'] or 0)<=0:reasons.append('nonpositive_expectancy')
            if not ((c['profit_factor'] or 0)>=1.1 or c['wins']==c['trades']>0):reasons.append('profit_factor')
            if c['max_drawdown_r']>6:reasons.append('drawdown')
            if c['mean_net_r'] is None or base['mean_net_r'] is None or c['mean_net_r']<=base['mean_net_r']:reasons.append('no_expectancy_improvement')
            if reasons:failures.append({'period':p,'cost':cost,'reasons':reasons})
    report={'state':'completed_research_only','protocol_sha256':digest(output/'protocol.json'),'results':results,'failures':failures,
        'historical_qualified':not failures,'orders_sent':0,'broker_eligible':False,'live_policy_changed':False,'full_live_policy_parity':False,
        'limitations':['Research feature adapters reflect verified closed-candle evidence; not historical screenshots or macro context.',
            'Previously inspected dates and approximate broker costs; no fresh or blind qualification.',
            'M5 OHLC stop-first fills and frozen ATR distances approximate broker execution. No automatic activation.']}
    save_signed(output,'report',report)
    (ROOT/'docs/SWEEP_RECLAIM_RESEARCH_20261126.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    progress(state='completed');print(json.dumps(report),flush=True)


if __name__=='__main__':run()
