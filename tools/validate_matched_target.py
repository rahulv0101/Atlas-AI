"""Receipt-checked validation admission; never activates or executes a strategy."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json
import pandas as pd
from atlas_ai.atomic_files import atomic_json
from tools.learn_candidate_ranker import signed,save_signed,digest

ROOT=Path(__file__).resolve().parents[1]


def existing_registration(storage,candidate_id):
    storage=Path(storage).resolve();pointer=storage/'matched_target_validation_active.json'
    if not pointer.exists():return None
    directory=Path(json.loads(pointer.read_text())['run_dir']).resolve()
    directory.relative_to(storage)
    plan=signed(directory,'plan')
    if plan['candidate_id']!=candidate_id:raise ValueError('new_candidate_requires_separate_registration_review')
    return plan


def historical_gate(results):
    failures=[]
    for period,lanes in results.items():
        for lane,pair in lanes.items():
            baseline,candidate=pair['baseline'],pair['paired_targets']
            reasons=[]
            if candidate['trades']<30:reasons.append('fewer_than_30_trades')
            if candidate['mean_net_r'] is None or candidate['mean_net_r']<=0:reasons.append('nonpositive_expectancy')
            if not ((candidate['profit_factor'] or 0)>=1.1 or candidate['wins']==candidate['trades']>0):reasons.append('profit_factor_below_1_1')
            if candidate['max_drawdown_r']>6:reasons.append('drawdown_above_6R')
            if (candidate['mean_net_r'] is None or baseline['mean_net_r'] is None
                    or candidate['mean_net_r']<=baseline['mean_net_r']):reasons.append('no_expectancy_improvement_over_baseline')
            if reasons:failures.append({'period':period,'cost_lane':lane,'reasons':reasons})
    if not results or any(set(lanes)!={'base','stress'} for lanes in results.values()):
        failures.append({'reasons':['missing_cost_lanes']})
    if len(results)<2:failures.append({'reasons':['missing_separate_historical_period']})
    return {'passed':not failures,'failures':failures}


def run():
    source=ROOT/'storage/matched_target_20261126T093441Z'
    candidate=signed(source,'report');protocol=signed(source,'protocol')
    baseline_source=ROOT/'storage/retest_capital_20261126T081720Z'
    baseline=signed(baseline_source,'report');old=signed(baseline_source,'protocol')
    assert candidate['protocol_sha256']==digest(source/'protocol.json')
    assert protocol['baseline_report_sha256']==digest(baseline_source/'report.json')
    assert baseline['protocol_sha256']==digest(baseline_source/'protocol.json')
    assert all(protocol[k]==old[k] for k in ('settings','spec','limits','periods','setup_hashes'))
    for name,expected in old['source_hashes'].items():
        if name.replace('\\','/').startswith('atlas_ai/'):
            assert protocol['source_hashes'].get(name)==expected,'historical_trading_source_changed'
    periods=sorted((pd.Timestamp(a),pd.Timestamp(b)) for a,b in protocol['periods'].values())
    assert all(a<b for a,b in periods) and all(periods[i][1]<=periods[i+1][0] for i in range(len(periods)-1))
    original=ROOT/'storage/complete_retest_setup_20261126T081014Z'
    for name,lanes in candidate['results'].items():
        assert digest(original/(name+'_setups.json'))==old['setup_hashes'][name]
        frozen=signed(original,name+'_setups')['rows']
        for lane,pair in lanes.items():
            assert pair['baseline']=={k:v for k,v in baseline['results'][name]['lanes'][lane].items() if k not in {'return_fraction','max_drawdown'}}
            changed=signed(source,name+'_'+lane+'_setups')['rows'];assert len(changed)==len(frozen)
            for a,b in zip(frozen,changed):
                a=deepcopy(a);b=deepcopy(b)
                for x,y in zip(a['signals'],b['signals']):
                    assert y.pop('take_profit_points')>=x.pop('take_profit_points')
                assert a==b,'changes_beyond_target_pairing'
    gate=historical_gate(candidate['results'])
    existing=existing_registration(ROOT/'storage',digest(source/'protocol.json'))
    if existing is not None:
        print(json.dumps(existing),flush=True)
        return
    now=datetime.now(timezone.utc)
    output=ROOT/'storage'/('matched_target_validation_'+now.strftime('%Y%m%dT%H%M%SZ'));output.mkdir()
    plan={'schema':'atlas_paired_target_validation_v1','registered_at':now.isoformat(),
          'candidate_id':digest(source/'protocol.json'),'candidate_report_sha256':digest(source/'report.json'),
          'baseline_report_sha256':digest(baseline_source/'report.json'),
          'baseline_unchanged':True,'historical_periods_disjoint':True,
          'historical_scope':'Separate date blocks, previously inspected; not blind or fresh demo evidence.',
          'cost_model':{'base':'Recorded lagged spread + 3 adverse points per side + frozen broker fees',
                        'stress':'Double spread + 6 adverse points per side + frozen broker fees',
                        'natural_fill_calibration_verified':False},
          'historical_gate':gate,
          'fresh_demo_requirement':{'candidate_id_must_match':digest(source/'protocol.json'),
              'must_begin_after_registration':now.isoformat(),'minimum_first_stage':30,'minimum_validation_stage':30,
              'rules':'Same frozen baseline and candidate on identical fresh data; positive net expectancy, PF>=1.1 and drawdown<=6R in both stages, including cost stress.',
              'broker_proof':'Separate matching natural guarded entry, observed protection and balanced exit; exclude manual/forced diagnostics.',
              'forbidden_substitutes':['Historical replay outcomes','Trades from another strategy or version','Manual and forced trades','Previously collected unrelated paper outcomes']},
          'fresh_demo_observation':{'state':'not_started_historical_rejected' if not gate['passed'] else 'awaiting_registered_observer',
                                    'first_stage_cases':0,'validation_stage_cases':0,'verified_candidate_broker_cycles':0},
          'activation_blockers':['Historical qualification failed' if not gate['passed'] else 'Independent historical review pending',
              'Fresh candidate-specific demo validation incomplete','Measured cost reconciliation incomplete',
              'Reviewed M5 integration and existing promotion approval required'],
          'activation_allowed':False,'broker_eligible':False,'orders_sent':0,'live_policy_changed':False}
    save_signed(output,'plan',plan)
    atomic_json(ROOT/'storage/matched_target_validation_active.json',{'run_dir':str(output)})
    (ROOT/'docs/MATCHED_TARGET_VALIDATION_20261126.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(plan),flush=True)


if __name__=='__main__':run()
