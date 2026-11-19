"""Preserve the original all-frame hypothesis for read-only SMC experiments.

This is not the live M5 execution gate; it must not follow live policy tuning.
"""
from atlas_ai.data.top_down import POLICY,TIMEFRAMES


def entry_gate(context, side):
    failed=[tf for tf in TIMEFRAMES if context.get('details',{}).get(tf)!=side]
    passed=(side in {'buy','sell'} and context.get('policy') in {POLICY,'top_down_d1_h4_h1_m15_m5_v1'}
            and context.get('entry_timeframe')=='M5' and context.get('closed_candles_only') is True and not failed)
    return {'passed':passed,'policy':'smc_research_all_four_v1','nonconfirming_timeframes':failed,
            'reason':'all_higher_timeframes_confirm' if passed else 'higher_timeframe_confluence_required'}
