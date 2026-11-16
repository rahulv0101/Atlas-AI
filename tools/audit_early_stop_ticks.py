"""Read-only quote-path check for recorded early full-risk simulated stops."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import MetaTrader5 as mt5
import pandas as pd
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import utc_query_time
from atlas_ai.learning.observation_checkpoint import account_scope
from atlas_ai.runtime_processes import atlas_mode_processes
from atlas_ai.testing.historical_broker import BrokerSpec
from atlas_ai.testing.tick_reconstruction import normalize_ticks, candle_coverage, first_barrier
from tools.learn_candidate_ranker import signed, save_signed, digest, deny


def require_idle_terminal():
    active = atlas_mode_processes('live', project_root=ROOT)
    if active is None or active:
        raise RuntimeError('native_tick_review_requires_idle_Atlas_terminal; live backend must not share blocking history queries')


def peak_before_stop(ticks, side, entry, distance, stop_at):
    boundary = pd.Timestamp(stop_at)
    pre = ticks.loc[ticks.utc < boundary]
    quote = pre.bid if side == 'buy' else pre.ask
    sign = 1 if side == 'buy' else -1
    peak = max(0., float((sign*(quote-entry)/distance).max())) if len(pre) else None
    return {'peak_R_strictly_before_stop_timestamp': peak,
            'same_millisecond_quotes_at_stop': int((ticks.utc == boundary).sum()),
            'note': 'Exit-millisecond ordering and broker modification/fill latency are not established.'}


def run(study, baseline, output):
    require_idle_terminal()
    p, report = signed(study, 'protocol'), signed(study, 'report')
    receipt = signed(study, 'prediction_receipt')
    if (report['protocol_sha256'] != digest(study/'protocol.json')
            or report['prediction_receipt_sha256'] != digest(study/'prediction_receipt.json')
            or receipt['candidate_cache_sha256'] != digest(study/'candidate_cache.json')):
        raise ValueError('source_protocol_changed')
    cfg = load_settings()
    data = baseline/'smc_event_retest_v5'
    manifest = signed(data, 'manifest')
    if account_scope(cfg) != manifest['account_scope']:
        raise ValueError('configured_account_scope_changed')
    if digest(data/'M5.csv') != signed(data, 'inputs')['M5']:
        raise ValueError('candles_changed')
    frame = pd.read_csv(data/'M5.csv')
    times = pd.to_datetime(frame.time, utc=True)
    cache = signed(study, 'candidate_cache')['rows']
    candidates = {(name, row['index']): row['signals'][0] for name, rows in cache.items() for row in rows}
    spec = BrokerSpec(**p['spec'])
    trades = [(name, trade) for name, model in report['models'].items() for stage in model['stages'].values()
              for trade in stage['trade_list'] if trade['exit_reason']=='stop_loss' and trade['net_r'] <= -.99]
    output = output.resolve()
    output.relative_to(ROOT/'storage')
    output.mkdir(parents=True, exist_ok=False)
    save_signed(output, 'protocol', {'frozen_at': datetime.now(timezone.utc).isoformat(),
        'source_report_sha256': digest(study/'report.json'), 'schema': 'atlas_early_stop_quote_review_v1',
        'clock_hypotheses': ['configured_server_wall', 'documented_UTC'],
        'selection': 'Unique clock matching every recorded M5 Bid candle with bounded quote coverage; never selected by profit.',
        'orders_sent': 0, 'broker_eligible': False,
        'limitations': ['Quote paths are not broker fills or protection acknowledgements.',
                        'Only entry through the recorded exit bar is queried; no portfolio or strategy is changed.']})
    cases = []
    with patch.object(mt5, 'order_send', deny):
        connected = mt5.initialize(path=cfg.hfm_terminal_path) if cfg.hfm_terminal_path else mt5.initialize()
        account = mt5.account_info() if connected else None
        if (account is None or account.login != cfg.hfm_login or account.server != cfg.hfm_server
                or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO):
            raise ValueError('matching_demo_terminal_required_no_login_change_attempted')
        for n, (name, trade) in enumerate(trades):
            start = times.iloc[trade['entry_bar']]
            if start != pd.Timestamp(trade['entry_at']):
                raise ValueError('trade_bar_time_changed')
            end = times.iloc[trade['exit_bar']]+pd.Timedelta(minutes=5)
            record = {'entry_at': start.isoformat(), 'side': trade['side'], 'attempts': []}
            usable = []
            for basis in ['configured_server_wall', 'documented_UTC']:
                try:
                    utc = basis == 'documented_UTC'
                    a = start.to_pydatetime() if utc else utc_query_time(start.to_pydatetime(), cfg)
                    b = end.to_pydatetime() if utc else utc_query_time(end.to_pydatetime(), cfg)
                    raw = mt5.copy_ticks_range(cfg.symbol, a, b, mt5.COPY_TICKS_INFO)
                    if raw is None or not len(raw):
                        record['attempts'].append({'basis': basis, 'usable': False, 'reason': 'tick_history_unavailable'})
                        continue
                    rows = normalize_ticks(raw, SimpleNamespace(mt5_server_timezone='UTC' if utc else cfg.mt5_server_timezone))
                    checks, selected = [], []
                    for i in range(trade['entry_bar'], trade['exit_bar']+1):
                        subset, evidence = candle_coverage(rows, frame.iloc[i], times.iloc[i], times.iloc[i]+pd.Timedelta(minutes=5), spec.point)
                        checks.append(evidence)
                        selected.append(subset)
                    good = all(v['usable'] for v in checks)
                    record['attempts'].append({'basis': basis, 'usable': good, 'candle_checks': checks})
                    if good:
                        usable.append((basis, pd.concat(selected, ignore_index=True)))
                except (ValueError, TypeError, RuntimeError, OverflowError) as exc:
                    record['attempts'].append({'basis': basis, 'usable': False, 'reason': type(exc).__name__})
            if len(usable) == 2 and str(cfg.mt5_server_timezone).upper() in {'UTC', 'ETC/UTC'}:
                usable = usable[:1]
            if len(usable) != 1:
                cases.append({**record, 'state': 'unresolved_clock_or_coverage'})
                continue
            basis, ticks = usable[0]
            tick_path = output/f'case_{n}_ticks.csv'
            ticks.to_csv(tick_path, index=False)
            signal = candidates[(name, trade['entry_bar']-1)]
            sign = 1 if trade['side']=='buy' else -1
            distance = trade['initial_risk_cash']/abs(spec.cash(-1., trade['volume']))
            stop = round(trade['entry_price']-sign*distance, spec.digits)
            target = round(trade['entry_price']+sign*signal['take_profit_points']*spec.point, spec.digits)
            ordering = first_barrier(ticks, trade['side'], stop, target)
            observation = None
            if ordering['stop_first_at']:
                observation = peak_before_stop(ticks, trade['side'], trade['entry_price'], distance, ordering['stop_first_at'])
            cases.append({**record, 'state': 'quote_path_reconstructed', 'basis': basis,
                          'fixed_recorded_barriers': ordering, 'favorable_path_before_stop': observation,
                          'break_even_trigger_R': p['settings']['backtest_break_even_r_trigger'],
                          'tick_data_sha256': digest(tick_path), 'broker_fill': False})
    result = {'state': 'completed_read_only_tick_review', 'cases': cases,
              'protocol_sha256': digest(output/'protocol.json'), 'orders_sent': 0, 'broker_eligible': False}
    save_signed(output, 'report', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.study.resolve(), args.baseline.resolve(), args.output.resolve())
    print(json.dumps({'state': result['state'], 'cases': [
        {'at': c['entry_at'], 'state': c['state'], 'ordering': c.get('fixed_recorded_barriers'),
         'prestop_path': c.get('favorable_path_before_stop')} for c in result['cases']]}))
