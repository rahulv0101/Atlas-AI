"""Read-only broker fee evidence for isolated strategy research."""
from datetime import datetime,timedelta,timezone
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import MetaTrader5 as mt5
from atlas_ai.atomic_files import atomic_json
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import utc_query_time


def build_profile(deals, symbol_info, currency, now):
    if deals is None:raise ValueError("broker_fee_history_unavailable")
    rows=[d for d in deals if d.symbol==symbol_info.name and d.type in (mt5.DEAL_TYPE_BUY,mt5.DEAL_TYPE_SELL) and d.volume>0]
    if any(not all(math.isfinite(float(v)) for v in (d.volume,d.commission,d.fee)) for d in rows):
        raise ValueError("nonfinite_fee_evidence")
    if not all(math.isfinite(float(v)) and float(v)>0 for v in (symbol_info.point,symbol_info.trade_tick_value,symbol_info.trade_tick_size)):
        raise ValueError("valid_point_value_required")
    fees=sum(abs(float(d.commission))+abs(float(d.fee)) for d in rows)
    volume=sum(float(d.volume) for d in rows)
    roundtrip=2*fees/volume if volume else None
    point_value=symbol_info.trade_tick_value/symbol_info.trade_tick_size*symbol_info.point
    return {"asof":now.isoformat(),"currency":currency,"point":symbol_info.point,"tick_size":symbol_info.trade_tick_size,
        "stops_level_points":symbol_info.trade_stops_level,"freeze_level_points":symbol_info.trade_freeze_level,
        "point_value_per_lot_current":point_value,"fee_samples":len(rows),"sum_deal_volume":volume,
        "roundtrip_fee_per_lot_observed":roundtrip,
        "roundtrip_fee_points_estimate":roundtrip/point_value if roundtrip is not None else None,
        "fee_source":"Absolute broker commission and fee charges per deal volume, scaled to round trip; manual deals allowed for fee evidence only. Current currency conversion is approximate; not strategy performance or guaranteed future costs."}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();s=load_settings()
    if not mt5.initialize(path=s.hfm_terminal_path):raise RuntimeError("broker_unavailable")
    a=mt5.account_info()
    if a is None or a.login!=s.hfm_login or a.server!=s.hfm_server or a.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise ValueError("matching_demo_account_required")
    now=datetime.now(timezone.utc);info=mt5.symbol_info(s.symbol)
    if info is None:raise ValueError("symbol_unavailable")
    deals=mt5.history_deals_get(utc_query_time(now-timedelta(days=30),s),utc_query_time(now,s))
    result=build_profile(deals,info,a.currency,now)
    args.output.parent.mkdir(parents=True,exist_ok=True);atomic_json(args.output,result)
    print(json.dumps({"output":str(args.output),"fee_samples":result["fee_samples"],"roundtrip_fee_points_estimate":result["roundtrip_fee_points_estimate"]}))


if __name__=="__main__":main()
