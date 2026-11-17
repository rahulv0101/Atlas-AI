"""Verify a completed partial-parity replay and export a portable operator report."""
import argparse
import json
from pathlib import Path
from tools.learn_candidate_ranker import signed, digest


def summarize(directory):
    protocol=signed(directory,'protocol'); report=signed(directory,'report')
    if report.get('state')!='completed_partial_parity_diagnostic':
        raise ValueError('completed_report_required')
    if report['protocol_sha256']!=digest(directory/'protocol.json') or report['candidate_receipt_sha256']!=digest(directory/'candidates.json'):
        raise ValueError('receipt_mismatch')
    candidates=signed(directory,'candidates')
    for value in [protocol,report]:
        if value.get('broker_eligible') is not False or value.get('orders_sent')!=0:
            raise ValueError('research_only_required')
        if value.get('full_live_parity') is not False or value.get('frequency_claim_allowed') is not False or value.get('expected_live_trades_per_day') is not None:
            raise ValueError('partial_parity_must_not_claim_live_frequency')
    result={k:report[k] for k in ['state','full_live_parity','missing_live_evidence','expected_live_trades_per_day','frequency_claim_allowed','orders_sent','broker_eligible']}
    result.update(settings_timeframe=protocol['settings']['timeframe'],strategies=candidates['strategies'],
        candidate_bars=len(candidates['rows']),virtual_initial_balance=protocol['settings']['backtest_initial_balance'],
        broker_spec_basis=protocol['broker_spec_basis'],local_evidence=str(directory),
        receipts={name:digest(directory/(name+'.json')) for name in ['protocol','candidates','report']})
    root=Path(__file__).resolve().parents[1]
    result['current_source_matches_startup_hashes']={name:digest(root/name)==expected for name,expected in protocol.get('source_hashes',{}).items()}
    for label in ['diagnostic','strict_missing_evidence_screen']:
        stats=report[label]
        if stats['trades']+sum(stats['rejections'].values())!=len(candidates['rows']):
            raise ValueError('candidate_accounting_mismatch')
        result[label]={k:stats[k] for k in ['trades','wins','net_cash','profit_factor','mean_net_r','max_drawdown_r','rejections']}
    result['interpretation']='Diagnostic simulations are not broker trades. Strict evidence refusals are unknown outcomes, not losses. Missing gates prevent a live-rate forecast or model activation.'
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=summarize(args.run_dir.resolve())
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['candidate_bars','diagnostic','strict_missing_evidence_screen']}))
