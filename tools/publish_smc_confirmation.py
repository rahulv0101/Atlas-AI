"""Publish a verified research result to Atlas's existing read-only status view."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from atlas_ai.atomic_files import atomic_json
from tools.learn_candidate_ranker import signed, save_signed, digest


def publish(directory, storage):
    directory, storage = Path(directory).resolve(), Path(storage).resolve()
    directory.relative_to(storage)
    protocol = signed(directory, 'protocol')
    report = signed(directory, 'report')
    receipt = signed(directory, 'prediction_receipt')
    if (report.get('state') != 'completed_research_only' or report.get('broker_eligible') is not False
            or report.get('auto_promotion') is not False or report.get('orders_sent') != 0
            or report.get('selected_for_broker') is not None or protocol.get('broker_eligible') is not False):
        raise ValueError('verified_research_only_result_required')
    if (report['protocol_sha256'] != digest(directory/'protocol.json')
            or receipt['protocol_sha256'] != digest(directory/'protocol.json')
            or report['prediction_receipt_sha256'] != digest(directory/'prediction_receipt.json')
            or receipt['observations_sha256'] != digest(directory/'observations.jsonl')
            or receipt['candidate_cache_sha256'] != digest(directory/'candidate_cache.json')):
        raise ValueError('research_receipt_changed')
    view = directory/'operator_view'
    view.mkdir(exist_ok=False)
    pointer = storage/'smc_entry_comparison_active.json'
    if pointer.exists():
        (view/'previous_operator_pointer.json').write_bytes(pointer.read_bytes())
    save_signed(view, 'protocol', {'schema': 'atlas_confirmation_operator_view_v1',
        'source_protocol_sha256': digest(directory/'protocol.json'), 'source_report_sha256': digest(directory/'report.json'),
        'broker_eligible': False, 'orders_sent': 0, 'auto_promotion': False,
        'purpose': 'Read-only operator view; cannot activate a strategy or a paper observer.'})
    models = {}
    for name, model in report['models'].items():
        models[name] = {'eligible_candidates': model['eligible_candidates'], 'counts': model['counts'],
                        'detector_counts': model.get('detector_counts', {}), 'stages': {}}
        for stage, stats in model['stages'].items():
            models[name]['stages'][stage] = {
                'trades': stats['trades'], 'wins': stats['wins'], 'net_cash': stats['net_cash'],
                'mean_r': stats['mean_net_r'], 'profit_factor': stats['profit_factor'],
                'max_drawdown_r': stats['max_drawdown_r'], 'review_passed': stats['review']['passed']}
    save_signed(view, 'report', {'schema': 'atlas_smc_confirmation_operator_result_v1', 'models': models,
        'protocol_sha256': digest(view/'protocol.json'), 'broker_eligible': False, 'orders_sent': 0,
        'selection': {'selected_for_forward_paper': None, 'development_qualified': [],
                      'selected_for_broker': None, 'broker_eligible': False, 'automatic_broker_activation': False},
        'note': 'A compatibility correction is not proof of an edge. Explicit review and fresh evidence remain required.'})
    atomic_json(pointer, {'run_dir': str(view)})
    return view


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    publish(args.run_dir, ROOT/'storage')
    print('Verified research result published to operator status; no model activated.')
