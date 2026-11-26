"""Persistent research review, never strategy activation or broker authority."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

POLICY = {'min_historical_trades': 30, 'stage_trades': 30, 'min_total_shadow_trades': 100,
          'min_profit_factor': 1.1, 'max_drawdown_r': 6., 'deadline_days': 28,
          'stress_friction_multiplier': 2.}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def metrics(rows, *, stress=False):
    values = []
    for row in rows:
        net, gross = float(row['net_r']), float(row['gross_r'])
        if not all(math.isfinite(x) for x in (net, gross)) or net > gross + 1e-9:
            raise ValueError('invalid_trial_return_or_cost')
        values.append(gross-POLICY['stress_friction_multiplier']*(gross-net) if stress else net)
    positive = sum(x for x in values if x > 0)
    negative = -sum(x for x in values if x < 0)
    total = peak = drawdown = 0.
    for value in values:
        total += value
        peak = max(peak, total)
        drawdown = max(drawdown, peak-total)
    return {'trades': len(values), 'mean_r': total/len(values) if values else None,
            'net_r': total, 'profit_factor': positive/negative if negative else None,
            'has_losses': negative > 0, 'max_drawdown_r': drawdown}


def passed(value, minimum):
    return (value['trades'] >= minimum and (value['mean_r'] or 0) > 0
            and (not value['has_losses'] or value['profit_factor'] >= POLICY['min_profit_factor'])
            and value['max_drawdown_r'] <= POLICY['max_drawdown_r'])


def freeze_trial(batch, now):
    # Selection uses training only. Separate holdout is a pass/fail gate, never a ranking input.
    eligible = [c for c in batch['candidates'] if c.get('training_rows') is not None
                and passed(metrics(c['training_rows']), POLICY['min_historical_trades'])]
    eligible.sort(key=lambda c: (-metrics(c['training_rows'])['mean_r'], c['frozen_gene_sha256']))
    if not eligible:
        return None
    candidate = deepcopy(eligible[0])
    candidate.update(forward=[], next_forward_at=now.isoformat(), forward_summary={})
    identity = {'policy': deepcopy(POLICY), 'frozen_at': now.isoformat(),
                'proposal': {'problem': 'Observed gains are fragile to modeled trading costs.',
                             'hypothesis': 'One bounded chart-rule candidate can remain positive on separate dates and doubled modeled friction.',
                             'scope': 'Existing validated DNA templates only; no generated code, live policy edits or retraining.'},
                'deadline': (now+timedelta(days=POLICY['deadline_days'])).isoformat(),
                'gene_sha256': candidate['frozen_gene_sha256'], 'protocol': deepcopy(batch['protocol']),
                'dataset_sha256': batch['dataset_sha256'],
                'training_sha256': digest(candidate['training_rows']),
                'holdout_sha256': digest(candidate['holdout_rows'])}
    return {'schema': 'atlas_governed_trial_v1', 'identity': identity, 'identity_sha256': digest(identity),
            'protocol': deepcopy(batch['protocol']), 'candidates': [candidate],
            'asof': batch['asof'], 'created_at': now.isoformat(), 'forward_integrity': 'verified_frozen_protocol'}


def review(trial, now):
    result = {'schema': 'atlas_governed_trial_review_v1', 'checked_at': now.isoformat(),
              'broker_eligible': False, 'auto_promotion': False, 'orders_sent': 0,
              'activation': 'blocked_pending_independent_validation_and_existing_promotion_gates',
              'rollback_scope': 'Quarantine this research trial; never alter existing trading positions or policy.'}
    if trial is None:
        return {**result, 'state': 'no_training_candidate', 'reason': 'No fresh candidate passed frozen training criteria.'}
    identity = trial['identity']
    candidate = trial['candidates'][0]
    if (digest(identity) != trial['identity_sha256'] or identity['policy'] != POLICY
            or digest(candidate['training_rows']) != identity['training_sha256']
            or digest(candidate['holdout_rows']) != identity['holdout_sha256']
            or trial['protocol'] != identity['protocol']
            or digest(candidate['chromosome']['genes']) != identity['gene_sha256']
            or candidate['frozen_gene_sha256'] != identity['gene_sha256']):
        return {**result, 'state': 'quarantined', 'reason': 'Frozen trial evidence or policy changed.'}
    if trial.get('forward_integrity') != 'verified_frozen_protocol' or candidate.get('forward_gap'):
        return {**result, 'state': 'quarantined', 'reason': 'Source integrity or forward coverage failed.'}
    rows = candidate['forward']
    training, heldout = candidate['training_rows'], candidate['holdout_rows']
    if (not training or not heldout or
            max(datetime.fromisoformat(r['exit_at']) for r in training) >=
            min(datetime.fromisoformat(r['signal_at']) for r in heldout) or
            max(datetime.fromisoformat(r['exit_at']) for r in heldout) > datetime.fromisoformat(identity['frozen_at'])):
        return {**result, 'state': 'quarantined', 'reason': 'Historical stages overlap or extend beyond the freeze.'}
    previous_exit = None
    for row in rows:
        signal, entry, exit_at = [datetime.fromisoformat(row[k].replace('Z', '+00:00'))
                                  for k in ('signal_at', 'entry_at', 'exit_at')]
        if (signal < datetime.fromisoformat(identity['frozen_at']) or not signal < entry <= exit_at <= min(now, datetime.fromisoformat(identity['deadline']))
                or previous_exit is not None and signal <= previous_exit):
            return {**result, 'state': 'quarantined', 'reason': 'Forward chronology overlaps or predates the freeze.'}
        previous_exit = exit_at
    size = POLICY['stage_trades']
    historical = {}
    for name in ('training', 'holdout'):
        historical[name] = {lane: metrics(candidate[name+'_rows'], stress=lane == 'stress')
                            for lane in ('base', 'stress')}
    stages = {name: {lane: metrics(part, stress=lane == 'stress') for lane in ('base', 'stress')}
              for name, part in [('first', rows[:size]), ('validation', rows[size:2*size])]}
    monitoring = metrics(rows)
    stress_monitoring = metrics(rows, stress=True)
    historical_ok = all(passed(v, POLICY['min_historical_trades']) for s in historical.values() for v in s.values())
    stages_ok = all(passed(v, size) for s in stages.values() for v in s.values())
    result.update(trial_id=trial['identity_sha256'][:20], frozen_at=identity['frozen_at'], deadline=identity['deadline'],
                  historical=historical, stages=stages, monitoring=monitoring, stress_monitoring=stress_monitoring,
                  min_total_shadow_trades=POLICY['min_total_shadow_trades'],
                  cost_scope='Doubled modeled friction sensitivity, not measured broker-unit cost or full live-gate parity.')
    if max(monitoring['max_drawdown_r'], stress_monitoring['max_drawdown_r']) > POLICY['max_drawdown_r']:
        return {**result, 'state': 'quarantined', 'reason': 'Forward research drawdown exceeded the frozen limit.'}
    if not historical_ok:
        return {**result, 'state': 'rejected_historical', 'reason': 'Separate historical base or cost-stress screen failed.'}
    if stages_ok and len(rows) >= POLICY['min_total_shadow_trades'] and all(
        passed(value, POLICY['min_total_shadow_trades']) for value in (monitoring, stress_monitoring)
    ):
        return {**result, 'state': 'independent_validation_required',
                'reason': 'Shadow screens passed; broker-unit costs, live-gate parity and existing promotion review remain required.'}
    if now >= datetime.fromisoformat(identity['deadline']):
        return {**result, 'state': 'insufficient_activity' if len(rows) < POLICY['min_total_shadow_trades'] else 'rejected_forward',
                'reason': 'Frozen observation window ended; no forced trades or automatic threshold changes.'}
    if any(not passed(v, size) for s in stages.values() for v in s.values() if v['trades'] >= size):
        return {**result, 'state': 'rejected_forward', 'reason': 'A completed forward stage failed.'}
    return {**result, 'state': 'collecting_forward', 'reason': 'Collecting unchanged frozen rules on future closed candles.'}
