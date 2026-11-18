"""Fixed-sample ATR correction capacity check. Not a replacement backtest."""
from pathlib import Path
from dataclasses import asdict
import json
import tempfile
import pandas as pd
from atlas_ai.models import TradeSignal
from atlas_ai.strategies.indicators import atr
from atlas_ai.strategies.distance_units import corrected_atr_signal
from atlas_ai.testing.smc_confirmation import affordable
from atlas_ai.testing.historical_broker import BrokerSpec
from tools.learn_candidate_ranker import signed,save_signed,digest,settings_for


def main():
    root=Path(__file__).resolve().parents[1]
    study=root/'storage/deployed_m5_parity_20261117T205724Z'
    protocol,report=signed(study,'protocol'),signed(study,'report')
    if report['protocol_sha256']!=digest(study/'protocol.json') or report['candidate_receipt_sha256']!=digest(study/'candidates.json'):
        raise ValueError('source_changed')
    source=root/'storage/smc_entry_rerun_20261116/smc_event_retest_v5/M5.csv'
    if digest(source)!=protocol['historical_inputs']['M5']:raise ValueError('candles_changed')
    frame=pd.read_csv(source);volatility=atr(frame)
    rows={row['index']:row for row in signed(study,'candidates')['rows']}
    spec=BrokerSpec(**protocol['broker_spec']);checks=[]
    with tempfile.TemporaryDirectory() as temp:
        cfg=settings_for(protocol,temp)
        for trade in report['diagnostic']['trade_list']:
            i=trade['entry_bar']-1
            signal=TradeSignal(**next(s for s in rows[i]['signals'] if s['strategy']==trade['strategy']))
            corrected=corrected_atr_signal(signal,float(volatility.iloc[i]),spec.point)
            allowed,reason,evidence=affordable(asdict(corrected),trade['entry_price'],spec,cfg,protocol['limits'],spread_points=float(frame.spread.iloc[i]))
            checks.append({'at':trade['entry_at'],'strategy':signal.strategy,'side':signal.side,
                'original_stop_points':signal.stop_loss_points,'corrected_stop_points':corrected.stop_loss_points,
                'corrected_target_points':corrected.take_profit_points,'affordable':allowed,'reason':reason,'evidence':evidence})
    output=root/'storage/corrected_m5_capacity_20261118';output.mkdir(exist_ok=False)
    result={'source_report_sha256':digest(study/'report.json'),'checks':checks,
        'original_trade_sample':len(checks),'affordable_corrected_sample':sum(c['affordable'] for c in checks),
        'virtual_balance':cfg.backtest_initial_balance,'risk_fraction_unchanged':cfg.max_risk_per_trade,
        'lot_cap_unchanged':protocol['limits']['lot_cap'],'orders_sent':0,'policy_changed':False,
        'scope':'Affordability at the original 47 entries only. No new candidates or outcomes simulated; cannot establish profitability or frequency.'}
    save_signed(output,'report',result)
    (root/'docs/CORRECTED_M5_CAPACITY_20261118.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))


if __name__=='__main__':main()
