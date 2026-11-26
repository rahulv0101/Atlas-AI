"""One fixed H1 confirmation filter, isolated from the deployed strategy."""
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
from atlas_ai.data.top_down import closed_bars
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.trader import AtlasTrader
from atlas_ai.testing.h1_m5_retest_timing import overlay
from atlas_ai.testing.historical_broker import BrokerSpec,ExitVariant
from atlas_ai.testing.policy_replay import replay
from tools.test_complete_retest_setup import generate
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for,deny
from tools.cost_aware_strategy_audit import prepare_frame
from tools.trading_edge_audit import summarize
ROOT=Path(__file__).resolve().parents[1]


def confirms(h1,side,now):
    try:
        if side not in {'buy','sell'}:return False
        last=closed_bars(h1,'H1',now).iloc[-1]
        o,h,l,c=[float(last[k]) for k in ('open','high','low','close')]
        if not all(math.isfinite(v) and v>0 for v in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:return False
        return h>l and (1 if side=='buy' else -1)*(c-o)>=.5*(h-l)
    except (ValueError,TypeError,KeyError,IndexError):return False


def run():
    oldsource=ROOT/'storage/retest_capital_20261126T081720Z';old=signed(oldsource,'protocol')
    control=signed(oldsource,'report');assert control['protocol_sha256']==digest(oldsource/'protocol.json')
    receipt=signed(ROOT/'storage/m5_ema_stop_only_20261124_v2','prediction_receipt')
    sets={'earlier':(ROOT/'storage/smc_entry_rerun_20261116/smc_event_retest_v5',old['inputs']['earlier'],*old['periods']['earlier']),
          'recent':(ROOT/'storage/today_learning_replay_20261123_v2',old['inputs']['recent'],*old['periods']['recent']),
          'additional_april':(ROOT/'storage/m5_stop_research_20261114',receipt['data_hashes']['separate_validation'],
                              '2026-04-01T00:00Z','2026-05-01T00:00Z')}
    output=ROOT/'storage'/('h1_entry_quality_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));output.mkdir()
    protocol={'settings':old['settings'],'spec':old['spec'],'limits':old['limits'],
              'hypothesis':'Latest closed H1 candle must agree with trade side and have body >=50% of its range.',
              'unchanged':'H1 moving-average direction, M5 first retest and closed confirmation, 1.5ATR stop, 2R target, all exit/risk/session policies and costs.',
              'periods':{k:[a,b] for k,(_,_,a,b) in sets.items()},'inputs':{k:h for k,(_,h,_,_) in sets.items()},
              'source_hashes':{str(p.relative_to(ROOT)):digest(p) for folder in ('atlas_ai','tools') for p in (ROOT/folder).rglob('*.py')},
              'no_parameter_search':True,'broker_eligible':False,'orders_sent':0,
              'criteria':'Both cost lanes in every period: >=30 trades, positive net expectancy, PF>=1.1, drawdown<=6R; improve mean net R versus unchanged baseline.',
              'data_scope':'Previously inspected archives; additional April block was not used to choose the 50% rule. No blind/forward claim.'}
    save_signed(output,'protocol',protocol)
    results={};original=AtlasTrader._strategy_to_setup_family
    def family(self,name):return 'continuation' if name==old['setup_name'] else original(self,name)
    def progress(**row):atomic_json(output/'progress.json',row)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'login',deny),patch.object(mt5,'order_send',deny):
        for name,(directory,hashes,a,b) in sets.items():
            frames={}
            for tf in ('M5','H1'):
                path=directory/(tf+'.csv');assert digest(path)==hashes[tf]
                frames[tf]=prepare_frame(pd.read_csv(path));frames[tf]['time']=pd.to_datetime(frames[tf].time,utc=True)
            if name=='additional_april':
                with tempfile.TemporaryDirectory() as temp:
                    frozen,counts=generate(frames['M5'],frames['H1'],settings_for(old,temp),pd.Timestamp(a),pd.Timestamp(b),progress)
            else:
                source=ROOT/'storage/complete_retest_setup_20261126T081014Z'
                assert digest(source/(name+'_setups.json'))==old['setup_hashes'][name]
                frozen=signed(source,name+'_setups')['rows']
            selected=[r for r in frozen if confirms(frames['H1'],r['signals'][0]['side'],pd.Timestamp(r['available_at']))]
            save_signed(output,name+'_setups',{'baseline':frozen,'h1_confirmation':selected})
            contexts={r['available_at']:r['higher_context'] for r in frozen}
            results[name]={'baseline_setups':len(frozen),'filtered_setups':len(selected),'lanes':{}}
            for cost,mult,slip in [('base',1,3),('stress',2,6)]:
                results[name]['lanes'][cost]={}
                for lane,rows in [('baseline',frozen),('h1_confirmation',selected)]:
                    progress(period=name,cost=cost,lane=lane)
                    execution=frames['M5'].copy();execution['spread']=execution.spread.shift(1)*mult
                    with tempfile.TemporaryDirectory() as temp,patch.object(AtlasTrader,'_strategy_to_setup_family',family),overlay(contexts,{}):
                        cfg=settings_for(old,temp)
                        stats=replay(execution,deepcopy(rows),cfg,BrokerSpec(**old['spec']),
                            ExitVariant('configured',cfg.backtest_break_even_lock_r,slip),KnowledgeStore(temp),old['limits'],
                            start=pd.Timestamp(a).to_pydatetime(),end=pd.Timestamp(b).to_pydatetime())
                    save_signed(output,name+'_'+cost+'_'+lane,stats)
                    summary=summarize(stats,a,b)
                    for key in ('return_fraction','max_drawdown'):summary.pop(key,None)
                    if summary['active_entry_days']<2:summary['mean_net_r_day_block_bootstrap_95_interval']=None
                    results[name]['lanes'][cost][lane]=summary
            save_signed(output,'checkpoint',results)
    failures=[]
    for period,p in results.items():
        for cost,pair in p['lanes'].items():
            v,base=pair['h1_confirmation'],pair['baseline'];reasons=[]
            if v['trades']<30:reasons.append('insufficient_trades')
            if (v['mean_net_r'] or 0)<=0:reasons.append('nonpositive_expectancy')
            if not ((v['profit_factor'] or 0)>=1.1 or v['wins']==v['trades']>0):reasons.append('profit_factor')
            if v['max_drawdown_r']>6:reasons.append('drawdown')
            if v['mean_net_r'] is None or base['mean_net_r'] is None or v['mean_net_r']<=base['mean_net_r']:reasons.append('no_expectancy_improvement')
            if reasons:failures.append({'period':period,'cost':cost,'reasons':reasons})
    report={'state':'completed_research_only','protocol_sha256':digest(output/'protocol.json'),'results':results,
            'historical_qualified':not failures,'failures':failures,'orders_sent':0,'broker_eligible':False,'live_policy_changed':False,
            'full_live_policy_parity':False,'fresh_demo_cases':0,
            'limitations':control['limitations']+['A directional H1 candle filter is one research hypothesis, not a validated permanent learning update.',
                'All periods are retrospective. No diagnostic result authorizes broker activation.']}
    save_signed(output,'report',report)
    (ROOT/'docs/H1_ENTRY_QUALITY_RESEARCH_20261126.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    progress(state='completed');print(json.dumps(report),flush=True)


if __name__=='__main__':run()
