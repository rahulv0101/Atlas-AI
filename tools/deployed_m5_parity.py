"""Offline deployed-M5 diagnostic. Missing live evidence forbids parity claims."""
import json
from pathlib import Path
from dataclasses import replace
from datetime import datetime, timezone
import tempfile
from unittest.mock import patch
import MetaTrader5 as mt5
from atlas_ai.config.settings import load_settings
from atlas_ai.memory.knowledge_store import KnowledgeStore
from atlas_ai.testing.policy_replay import cache_candidates, replay
from atlas_ai.testing.historical_broker import BrokerSpec, ExitVariant
from tools.guarded_research_audit import safe_settings
from tools.research_entry_horizon import load_frames
from tools.learn_candidate_ranker import signed, save_signed, digest, deny

MISSING = ['predecision_allocator_and_contextual_ranking_state', 'drift_throttle_and_learning_state',
    'online_learning_and_loss_pattern_guards', 'EMA_side_switch_and_fresh_cross_guard',
    'side_balance_cluster_smart_context_and_meta_model', 'gold_knowledge_and_directional_structure_guards',
    'visual_and_macro_point_in_time_evidence', 'broker_quotes_fills_and_account_occupancy',
    'approval_operator_presence_and_ExecutionGate_state']


def completeness(missing):
    return {'full_live_parity':not missing, 'missing_live_evidence':list(missing),
        'expected_live_trades_per_day':None,
        'frequency_claim_allowed':not missing}


def main():
    root=Path(__file__).resolve().parents[1]
    settings=load_settings()
    if settings.timeframe!='M5' or not settings.top_down_confluence_enabled:
        raise ValueError('deployed_M5_top_down_configuration_required')
    reference=root/'storage/smc_structural_v8_capacity_20261116_v2'
    ref=signed(reference,'protocol')
    source=root/'storage/smc_entry_rerun_20261116/smc_event_retest_v5'
    frames=load_frames(source,signed(source,'inputs'))
    output=root/'storage'/('deployed_m5_parity_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False)
    save_signed(output,'protocol',{'settings':safe_settings(settings),'historical_inputs':signed(source,'inputs'),
        'broker_spec':ref['spec'],'limits':ref['limits'], 'broker_spec_basis':'frozen_previous_demo_snapshot_not_current_broker_verification',
        'scope':'Current configured M5 base inventory; reused archived history. Not a complete recreation of step().',
        'source_hashes':{str(p.relative_to(root)):digest(p) for p in [Path(__file__).resolve(),root/'atlas_ai/testing/policy_replay.py',root/'atlas_ai/trader.py']},
        **completeness(MISSING),'orders_sent':0,'broker_eligible':False})
    def progress(**kw):
        from atlas_ai.atomic_files import atomic_json
        atomic_json(output/'progress.json',kw)
    with patch.object(mt5,'initialize',deny),patch.object(mt5,'order_send',deny),tempfile.TemporaryDirectory() as temp:
        cfg=replace(settings,execute_trades=False,storage_dir=temp,gemini_api_key='',openai_api_key='')
        store=KnowledgeStore(temp)
        candidates,counts,names=cache_candidates(frames['M5'],cfg,store,progress,native_frames=frames)
        save_signed(output,'candidates',{'rows':candidates,'counts':counts,'strategies':names})
        execution=frames['M5'].copy();execution['spread']=execution.spread.shift(1)
        rejection=[]
        diagnostic=replay(execution,candidates,cfg,BrokerSpec(**ref['spec']),ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),store,ref['limits'],audit=rejection.append)
        strict=replay(execution,candidates,cfg,BrokerSpec(**ref['spec']),ExitVariant('configured',cfg.backtest_break_even_lock_r,3.),store,ref['limits'],strict=True)
        save_signed(output,'report',{'state':'completed_partial_parity_diagnostic','diagnostic':diagnostic,
            'strict_missing_evidence_screen':strict,'rejections':rejection,**completeness(MISSING),
            'orders_sent':0,'broker_eligible':False,'protocol_sha256':digest(output/'protocol.json'),
            'candidate_receipt_sha256':digest(output/'candidates.json')})
        progress(state='completed_partial_parity_diagnostic')
    print(str(output))


if __name__=='__main__':main()
