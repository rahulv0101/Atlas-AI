"""Publish receipt-verified entry/horizon research; never activate a strategy."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from atlas_ai.atomic_files import atomic_json
from tools.learn_candidate_ranker import digest, signed, save_signed


def verify(directory):
    protocol, report = signed(directory, 'protocol'), signed(directory, 'report')
    for value in (protocol, report):
        if (value.get('broker_eligible') is not False or value.get('orders_sent') != 0
                or value.get('auto_promotion') is not False or value.get('live_policy_changed') is not False):
            raise ValueError('research_only_result_required')
    protocol_hash = digest(directory/'protocol.json')
    if (report.get('state') != 'completed_research_only' or report.get('selected_for_broker') is not None
            or report.get('protocol_sha256') != protocol_hash):
        raise ValueError('completed_matching_result_required')
    source = signed(directory, 'source_receipt')
    if source['protocol_sha256'] != protocol_hash:
        raise ValueError('source_protocol_changed')
    for name, expected in source['hashes'].items():
        frozen = (directory/'frozen_source'/name).resolve()
        frozen.relative_to((directory/'frozen_source').resolve())
        if digest(frozen) != expected:
            raise ValueError('frozen_source_changed')
    if set(report['periods']) != {'primary', 'separate'}:
        raise ValueError('both_periods_required')
    for period, variants in report['periods'].items():
        if set(variants) != {'control', 'entry_only', 'target_only', 'combined'}:
            raise ValueError('all_preregistered_lanes_required')
        raw = signed(directory, period+'_raw_receipt')
        prediction = signed(directory, period+'_prediction_receipt')
        candidates = signed(directory, period+'_candidates')
        for receipt in (raw, prediction):
            if receipt['protocol_sha256'] != protocol_hash or receipt.get('predictions_completed_before_labels') is not True:
                raise ValueError('prediction_protocol_changed')
        if (raw['sha256'] != digest(directory/(period+'_raw.jsonl'))
                or prediction['observations_sha256'] != digest(directory/(period+'_observations.jsonl'))
                or prediction['candidates_sha256'] != digest(directory/(period+'_candidates.json'))):
            raise ValueError('prediction_artifact_changed')
        for variant, result in variants.items():
            if result['eligible_candidates'] != len(candidates['rows'][variant]):
                raise ValueError('candidate_count_changed')
    return protocol, report


def publish(directory, storage):
    directory, storage = Path(directory).resolve(), Path(storage).resolve()
    directory.relative_to(storage)
    protocol, report = verify(directory)
    view = directory/'operator_view'
    view.mkdir(exist_ok=False)
    pointer = storage/'smc_entry_comparison_active.json'
    if pointer.exists():
        (view/'previous_operator_pointer.json').write_bytes(pointer.read_bytes())
    save_signed(view, 'protocol', {'schema': 'atlas_entry_horizon_operator_view_v1',
        'source_protocol_sha256': digest(directory/'protocol.json'),
        'source_report_sha256': digest(directory/'report.json'), 'broker_eligible': False,
        'orders_sent': 0, 'auto_promotion': False, 'purpose': 'Read-only comparison; no observer or broker activation.'})
    models = {}
    for period, variants in report['periods'].items():
        for variant, result in variants.items():
            models[period+'_'+variant] = {'eligible_candidates': result['eligible_candidates'],
                'counts': result['counts'], 'stages': {label: {
                    'trades': stats['trades'], 'wins': stats['wins'], 'net_cash': stats['net_cash'],
                    'mean_r': stats['mean_net_r'], 'profit_factor': stats['profit_factor'],
                    'max_drawdown_r': stats['max_drawdown_r'], 'review_passed': stats['review']['passed']}
                    for label, stats in result['stages'].items()}}
    save_signed(view, 'report', {'schema': 'atlas_entry_horizon_operator_result_v1', 'models': models,
        'protocol_sha256': digest(view/'protocol.json'), 'broker_eligible': False, 'orders_sent': 0,
        'selection': {'selected_for_forward_paper': None, 'development_qualified': [],
            'selected_for_broker': None, 'broker_eligible': False, 'automatic_broker_activation': False},
        'note': protocol['interpretation'], 'combined_review_passed': report['combined_review_passed']})
    atomic_json(pointer, {'run_dir': str(view)})
    return view


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    publish(args.run_dir, ROOT/'storage')
    print('Verified comparison published to read-only status; no model activated.')
