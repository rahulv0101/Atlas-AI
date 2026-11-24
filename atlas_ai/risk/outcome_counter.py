"""Deterministic UTC-day loss streak from complete broker-position outcomes."""
from datetime import datetime,timezone
import math


def outcome_label(net):
    net=float(net)
    if not math.isfinite(net):raise ValueError('nonfinite_closed_outcome')
    return 'loss' if net<0 else 'win' if net>0 else 'draw'


def daily_loss_streak(positions,now):
    if now.tzinfo is None:raise ValueError('aware_accounting_clock_required')
    day=now.astimezone(timezone.utc).date();rows=[];seen=set()
    for row in positions:
        if row.get('state')!='closed' or row.get('manual_test'):continue
        at=datetime.fromisoformat(row['closed_at'].replace('Z','+00:00'))
        if at.tzinfo is None:raise ValueError('aware_close_time_required')
        at=at.astimezone(timezone.utc)
        if at.date()!=day or at>now.astimezone(timezone.utc):continue
        identity=str(row['position_id'])
        if identity in seen:raise ValueError('duplicate_closed_position')
        seen.add(identity)
        rows.append((at,int(row.get('closed_fill_ticket') or row['position_id']),row))
    rows.sort(key=lambda item:item[:2]);streak=0
    for _,_,row in rows:
        label=outcome_label(row['net_profit'])
        if label=='loss':streak+=1
        elif label=='win':streak=0
    return {'verified':True,'day_utc':day.isoformat(),'consecutive_losses':streak,
        'closed_positions_today':len(rows),'position_ids':[row['position_id'] for _,_,row in rows],
        'source':'balanced_broker_flat_Atlas_owned_positions','draw_resets_streak':False}
