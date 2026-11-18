"""Read-only configured-demo capacity check; no login, orders or settings changes."""
from datetime import datetime,timezone
from pathlib import Path
import json
import math
from unittest.mock import patch
import MetaTrader5 as mt5
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import broker_time_to_utc
from tools.learn_candidate_ranker import signed,save_signed,deny,digest


def capacity(risk,budget,margin,free_margin):
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in [risk,budget,margin,free_margin]) or min(risk,budget,margin)<=0:
        return {'passes':False,'reason':'invalid_or_unavailable_capacity_data'}
    return {'passes':risk<=budget and margin<=free_margin,
        'risk_headroom_before_unmeasured_costs':budget-risk,'margin_headroom':free_margin-margin}


def main():
    root=Path(__file__).resolve().parents[1];s=load_settings()
    recorded=signed(root/'storage/corrected_m5_capacity_20261118','report')
    frozen=signed(root/'storage/deployed_m5_parity_20261117T205724Z','protocol')
    if s.symbol!=frozen['settings']['symbol'] or recorded['source_report_sha256']!=digest(root/'storage/deployed_m5_parity_20261117T205724Z/report.json'):
        raise ValueError('matching_symbol_and_historical_sample_required')
    output=root/'storage'/('demo_capacity_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False)
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'state':'unavailable','orders_sent':0,
        'account_settings_changed':False,'broker_eligible':False,'profitability_proven':False}
    with patch.object(mt5,'order_send',deny),patch.object(mt5,'login',deny):
        if not (mt5.initialize(path=s.hfm_terminal_path) if s.hfm_terminal_path else mt5.initialize()):
            raise RuntimeError('existing_terminal_attach_failed_no_login_attempted')
        a,info,tick=mt5.account_info(),mt5.symbol_info(s.symbol),mt5.symbol_info_tick(s.symbol)
        if a is None or a.login!=s.hfm_login or a.server!=s.hfm_server or a.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('matching_configured_demo_required_no_account_switch')
        if info is None or tick is None or not 0<tick.bid<=tick.ask or not 0<info.volume_min<=min(.01,frozen['limits']['lot_cap']):
            raise RuntimeError('valid_quote_and_minimum_lot_within_existing_cap_required')
        quote_age=(datetime.now(timezone.utc)-broker_time_to_utc(tick.time,s)).total_seconds()
        if not -2<=quote_age<=120:
            raise RuntimeError('fresh_quote_required_no_capacity_claim')
        budget=min(a.balance,a.equity)*s.max_risk_per_trade
        rows=[]
        for case in recorded['checks']:
            buy=case['side']=='buy';entry=(tick.ask if buy else tick.bid)
            stop_distance=case['corrected_stop_points']*frozen['broker_spec']['point']
            order_type=mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL
            profit=mt5.order_calc_profit(order_type,s.symbol,info.volume_min,entry,entry+( -1 if buy else 1)*(stop_distance+6*info.point))
            margin=mt5.order_calc_margin(order_type,s.symbol,info.volume_min,entry)
            risk=abs(profit) if profit is not None else None
            check=capacity(risk,budget,margin,a.margin_free)
            rows.append({'historical_entry_at':case['at'],'strategy':case['strategy'],'side':case['side'],
                'stop_price_distance':stop_distance,'current_min_lot_risk_with_six_point_slippage':risk,
                'current_min_lot_margin':margin,**check})
        result.update(state='matching_configured_demo_capacity_checked',symbol=s.symbol,currency=a.currency,
            balance=a.balance,equity=a.equity,free_margin=a.margin_free,risk_fraction=s.max_risk_per_trade,
            per_trade_risk_budget=budget,minimum_lot=info.volume_min,lot_cap=min(.01,frozen['limits']['lot_cap']),
            sample_entries=len(rows),passes_before_unmeasured_fees=sum(r['passes'] for r in rows),checks=rows,
            quote_time_epoch=tick.time,quote_age_seconds=quote_age,
            limitations=['Current broker conversion/margin applied to historical stop distances, not a historical portfolio replay.',
                'Commission/swap/gap slippage and remaining daily/weekly risk budgets are not verified by this check.',
                'Capacity is not strategy qualification, permission to trade or proof of profitability.'])
    save_signed(output,'report',result)
    portable={k:v for k,v in result.items() if k not in ['balance','equity','free_margin','per_trade_risk_budget','quote_time_epoch','checks']}
    portable['note']='Exact account capacity and per-case headroom are retained only in the local signed report. No account identifier is exported.'
    (root/'docs/DEMO_CAPACITY_20261118.json').write_text(json.dumps(portable,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(portable))


if __name__=='__main__':main()
