from copy import deepcopy
import pandas as pd
from tools.replay_corrected_m5 import corrected_rows


def fixture():
    frame=pd.DataFrame({'time':pd.date_range('2026-04-01',periods=50,freq='5min',tz='UTC'),
        'open':100.,'high':102.,'low':98.,'close':100.})
    rows=[{'index':30,'available_at':frame.time.iloc[31].isoformat(),'signals':[
        {'strategy':'ema_crossover','side':'sell','confidence':.65,'stop_loss_points':100.,'take_profit_points':150.}]}]
    return frame,rows


def test_correction_preserves_candidate_identity_and_original_stream():
    frame,rows=fixture();before=deepcopy(rows)
    corrected=corrected_rows(rows,frame,.01)
    signal=corrected[0]['signals'][0]
    assert rows==before
    assert signal['stop_loss_points']==800. and signal['take_profit_points']==1200.
    assert signal['side']=='sell' and signal['confidence']==.65
    assert corrected[0]['index']==rows[0]['index']


def test_future_price_changes_do_not_change_current_corrected_geometry():
    frame,rows=fixture();expected=corrected_rows(rows,frame,.01)
    frame.loc[31:,'high']=9999.
    assert corrected_rows(rows,frame,.01)==expected
