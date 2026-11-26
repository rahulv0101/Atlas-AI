"""Align stale file defaults with already-active stricter demo controls."""
import argparse
import json
from pathlib import Path
import re
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]


def aligned_bytes(raw,session,status):
    if (status.get('timeframe')!='M5' or status.get('higher_timeframe',{}).get('confirm_tf')!='H1'
            or status.get('higher_timeframe',{}).get('policy')!='top_down_h1_direction_m5_entry_v3'):
        raise ValueError('active_H1_M5_policy_required')
    values=dotenv_values(stream=__import__('io').StringIO(raw.decode('utf-8-sig')),interpolate=False)
    if values.get('TIMEFRAME')!='M5' or str(values.get('TOP_DOWN_CONFLUENCE_ENABLED','')).lower()!='true':
        raise ValueError('top_down_configuration_required')
    desired={'MAX_TRADES_PER_DAY':str(int(session['daily_trade_limit'])),
             'MAX_CONSECUTIVE_LOSSES':str(int(session['consecutive_loss_limit'])),
             'HIGHER_TIMEFRAME_CONFIRM':'H1'}
    for key in ('MAX_TRADES_PER_DAY','MAX_CONSECUTIVE_LOSSES'):
        if not 0<int(desired[key])<=int(values[key]):raise ValueError('cannot_increase_or_disable_limit')
    result=raw
    for key,value in desired.items():
        pattern=rb'(?m)^([ \t]*(?:export[ \t]+)?'+key.encode()+rb'[ \t]*=[ \t]*)([^#\r\n]*)(#[^\r\n]*)?(?=\r*$)'
        def replace(match):return match.group(1)+value.encode()+(b' '+match.group(3) if match.group(3) else b'')
        result,count=re.subn(pattern,replace,result)
        if count!=1:raise ValueError('unique_existing_setting_required:'+key)
    after=dotenv_values(stream=__import__('io').StringIO(result.decode('utf-8-sig')),interpolate=False)
    assert all(after.get(k)==v for k,v in values.items() if k not in desired)
    assert all(after[k]==v for k,v in desired.items())
    return result,{key:{'before':values[key],'after':value} for key,value in desired.items() if values[key]!=value}


def run(apply=False):
    env=ROOT/'.env';raw=env.read_bytes()
    state=json.loads((ROOT/'storage/automation_state.json').read_text());state=state.get('payload',state)
    status=json.loads((ROOT/'storage/status.json').read_text())
    aligned,changes=aligned_bytes(raw,state['session_control'],status)
    if apply:
        if env.read_bytes()!=raw:raise ValueError('env_changed_during_review')
        env.write_bytes(aligned)
        try:
            if env.read_bytes()!=aligned:raise ValueError('env_write_not_verified')
            aligned_bytes(aligned,state['session_control'],status)
        except Exception:
            if env.read_bytes()==aligned:env.write_bytes(raw)
            raise
    report={'state':'applied' if apply else 'review_only','changes':changes,
        'effect':'File defaults aligned to existing H1 direction and stricter runtime session limits. Effective live controls were not raised.',
        'other_parsed_values_unchanged':True,'credentials_exposed':False,'runtime_controls_changed':False,
        'volatility_guard_changed':False,'pilot_lot_cap_changed':False,'orders_sent':0,
        'current_blocker':status.get('primary_blocker'),
        'not_a_profitability_fix':True}
    (ROOT/'docs/RESTRICTION_ALIGNMENT_20261126.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    run(args.apply)
