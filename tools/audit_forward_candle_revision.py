"""Read-only comparison of retained forward candles with a short MT5 snapshot."""
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
import json
import pandas as pd
import MetaTrader5 as mt5
from atlas_ai.config.settings import load_settings
from atlas_ai.data.broker_clock import normalize_rates
from atlas_ai.testing.candle_revision import revision_audit
from tools.learn_candidate_ranker import signed,digest,save_signed,deny


def main():
    root=Path(__file__).resolve().parents[1];study=root/'storage/m5_calibration_20261116_v3'
    state=signed(study,'forward_checkpoint');source=study/'forward_closed_M5.csv'
    if digest(source)!=state['closed_sha256']:raise ValueError('retained_history_corrupt')
    previous=pd.read_csv(source,float_precision='round_trip');s=load_settings()
    with patch.object(mt5,'order_send',deny),patch.object(mt5,'login',deny):
        if not mt5.initialize(path=s.hfm_terminal_path):raise RuntimeError('terminal_attach_failed')
        account=mt5.account_info()
        if account is None or account.login!=s.hfm_login or account.server!=s.hfm_server or account.trade_mode!=mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise ValueError('matching_demo_required')
        raw=mt5.copy_rates_from_pos(s.symbol,mt5.TIMEFRAME_M5,0,1500)
        if raw is None or len(raw)==0:raise ValueError('short_snapshot_unavailable')
        current=normalize_rates(raw,s)
        now=pd.Timestamp.now(tz='UTC')
        current=current[pd.to_datetime(current.time,utc=True)+pd.Timedelta(minutes=5)<=now].reset_index(drop=True)
    result=revision_audit(previous,current)
    result.update(checked_at=datetime.now(timezone.utc).isoformat(),source_sha256=digest(source),
        historical_start_utc=str(previous.time.iloc[0]),historical_end_utc=str(previous.time.iloc[-1]),
        original_failure_cause_proven=False,orders_sent=0,old_checkpoint_modified=False,
        limitation='Current overlapping history cannot reconstruct the exact feed at the original failure.')
    output=root/'storage'/('candle_revision_audit_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(exist_ok=False);save_signed(output,'report',result)
    print(json.dumps(result))


if __name__=='__main__':main()
