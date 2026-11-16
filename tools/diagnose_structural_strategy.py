"""Receipt-bound explanation of a fixed strategy result; no policy or parameter changes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.models import TradeSignal
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant, simulate
from atlas_ai.trader import AtlasTrader
from tools.learn_candidate_ranker import signed, save_signed, digest, settings_for, deny


def payoff_summary(trades):
    wins = [t['net_cash'] for t in trades if t['net_cash'] > 0]
    losses = [-t['net_cash'] for t in trades if t['net_cash'] <= 0]
    win_total, loss_total = sum(wins), sum(losses)
    mean_win = win_total/len(wins) if wins else None
    mean_loss = loss_total/len(losses) if losses else None
    return {'trades': len(trades), 'wins': len(wins), 'losses': len(losses),
            'win_rate': len(wins)/len(trades) if trades else None,
            'gross_winning_cash': win_total, 'gross_losing_cash': loss_total,
            'net_cash_sum_separate_stage_runs': win_total-loss_total,
            'profit_factor_pooled_fixed_sample': win_total/loss_total if loss_total else None,
            'mean_win_cash': mean_win, 'mean_loss_cash': mean_loss,
            'break_even_win_rate_at_observed_payoffs': mean_loss/(mean_win+mean_loss) if mean_win and mean_loss else None,
            'note': 'Descriptive pooled fixed sample; stages reset independently. Not one continuous portfolio or a stable forecast.'}


def path_excursions(frame, trade, spec):
    """Pre-exit bars only: never claim an exit-bar high preceded its stop."""
    start, stop = trade['entry_bar'], trade['exit_bar']
    sign = 1 if trade['side'] == 'buy' else -1
    distance = trade['initial_risk_cash'] / abs(spec.cash(-1., trade['volume']))
    pre = frame.iloc[start:stop]
    if pre.empty:
        return {'completed_preexit_bars': 0, 'completed_preexit_mfe_r': None,
                'completed_preexit_mae_r': None, 'exit_bar_order_unknown': True}
    offset = pre.spread*spec.point if sign == -1 else 0.
    favorable = pre.high+offset if sign == 1 else pre.low+offset
    adverse = pre.low+offset if sign == 1 else pre.high+offset
    mfe = max(0., float((sign*(favorable-trade['entry_price'])/distance).max()))
    mae = max(0., float((-sign*(adverse-trade['entry_price'])/distance).max()))
    return {'completed_preexit_bars': len(pre), 'completed_preexit_mfe_r': mfe,
            'completed_preexit_mae_r': mae, 'exit_bar_order_unknown': True}


def run(study, pattern_source, baseline, output):
    report, protocol = signed(study, 'report'), signed(study, 'protocol')
    receipt = signed(study, 'prediction_receipt')
    patterns = signed(pattern_source, 'protocol')
    if (report['state'] != 'completed_research_only'
            or report['protocol_sha256'] != digest(study/'protocol.json')
            or report['prediction_receipt_sha256'] != digest(study/'prediction_receipt.json')
            or receipt['observations_sha256'] != digest(study/'observations.jsonl')
            or receipt['candidate_cache_sha256'] != digest(study/'candidate_cache.json')
            or protocol['source_protocol_sha256'] != digest(pattern_source/'protocol.json')
            or patterns['source_protocol_sha256'] != digest(baseline/'protocol.json')):
        raise ValueError('fixed_evidence_chain_changed')
    for name, expected in signed(study, 'source_receipt')['hashes'].items():
        if digest(study/'frozen_source'/name) != expected:
            raise ValueError('frozen_source_changed')
        if name.startswith('atlas_ai/') and digest(ROOT/name) != expected:
            raise ValueError('diagnostic_policy_version_mismatch')
    data = baseline/'smc_event_retest_v5'
    if digest(data/'M5.csv') != signed(data, 'inputs')['M5']:
        raise ValueError('candles_changed')
    frame = pd.read_csv(data/'M5.csv')
    execution = frame.copy()
    execution['spread'] = frame.spread.shift(1)
    cache = signed(study, 'candidate_cache')
    inputs = {(name, row['index']): row for name, rows in cache['rows'].items() for row in rows}
    spec = BrokerSpec(**protocol['spec'])
    trades = []
    with patch.object(mt5, 'initialize', deny), patch.object(mt5, 'order_send', deny), tempfile.TemporaryDirectory(prefix='atlas_fixed_loss_trace_') as temp:
        cfg = settings_for(protocol, temp)
        trader = AtlasTrader.__new__(AtlasTrader)
        trader.settings = cfg
        for name, model in report['models'].items():
            for stage, stats in model['stages'].items():
                for trade in stats['trade_list']:
                    i = trade['entry_bar']-1
                    row = inputs[(name, i)]
                    raw = row['signals'][0]
                    signal = TradeSignal(**raw)
                    reproduced = simulate(execution, trade['entry_bar'], signal, trade['volume'], spec, cfg,
                        ExitVariant('configured', cfg.backtest_break_even_lock_r, 3.))
                    for key in ['entry_price', 'exit_price', 'initial_risk_cash', 'net_cash', 'net_r']:
                        if not math.isclose(reproduced[key], trade[key], abs_tol=1e-7):
                            raise ValueError('recorded_trade_not_reproduced:'+key)
                    if reproduced['exit_bar'] != trade['exit_bar'] or reproduced['exit_reason'] != trade['exit_reason']:
                        raise ValueError('recorded_trade_path_changed')
                    window = frame.iloc[max(0, i-1199):i+1]
                    chart = trader._derive_runtime_chart_features(df=window, chosen=signal, regime=row['regime'])
                    source = {'stage': stage, 'strategy': name,
                              **{k:trade[k] for k in ['entry_at','side','exit_reason','net_cash','net_r','initial_risk_cash','confidence','session','ambiguous_stop_first']},
                              'bars_to_exit_including_exit_bar': trade['exit_bar']-trade['entry_bar']+1,
                              'initial_target_R': raw['take_profit_points']/raw['stop_loss_points'],
                              'M5_generic_trend': chart['trend_state'], 'M5_generic_momentum': chart['momentum_state'],
                              'M5_generic_location': chart['location_state'], 'regime': row['regime'],
                              'M5_trend_aligned': chart['trend_state'] == ('uptrend' if trade['side']=='buy' else 'downtrend'),
                              **path_excursions(execution, trade, spec)}
                    source['full_risk_stop'] = trade['net_r'] <= -.99 and trade['exit_reason']=='stop_loss'
                    trades.append(source)
    result = {'schema': 'atlas_fixed_strategy_diagnosis_v1', 'state': 'completed_read_only_diagnosis',
        'checked_at': datetime.now(timezone.utc).isoformat(), 'source_report_sha256': digest(study/'report.json'),
        'diagnostic_source_sha256': digest(Path(__file__)),
        'protocol_sha256': digest(study/'protocol.json'), 'payoffs': payoff_summary(trades),
        'exit_reasons': dict(Counter(t['exit_reason'] for t in trades)),
        'losing_exit_reasons': dict(Counter(t['exit_reason'] for t in trades if t['net_cash'] <= 0)),
        'full_risk_stop_count': sum(t['full_risk_stop'] for t in trades),
        'M5_alignment_outcomes': {str(aligned): {'trades': sum(t['M5_trend_aligned']==aligned for t in trades),
            'wins': sum(t['M5_trend_aligned']==aligned and t['net_cash']>0 for t in trades)} for aligned in [True, False]},
        'trades': trades, 'strategy_or_risk_policy_changed': False, 'orders_sent': 0,
        'limitations': ['Ten simulated trades across independently reset stages; associations are not causal proof.',
            'OHLC paths do not establish tick ordering, broker fills or exact intrabar exit times.',
            'No post-hoc filter or management setting was selected or activated.']}
    output.resolve().relative_to(ROOT/'storage')
    output.mkdir(parents=True, exist_ok=False)
    save_signed(output, 'report', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--pattern-source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    r = run(a.study.resolve(), a.pattern_source.resolve(), a.baseline.resolve(), a.output.resolve())
    print(json.dumps({k:v for k,v in r.items() if k not in {'trades'}}, indent=2))
