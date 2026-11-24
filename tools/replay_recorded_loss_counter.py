"""Causal counter-only replay on recorded broker fills; not a price simulation."""
from datetime import datetime,timedelta,timezone
from collections import defaultdict
from atlas_ai.learning.closed_position_ledger import rebuild_positions
from atlas_ai.learning.evidence_provenance import is_manual_broker_test
from atlas_ai.risk.outcome_counter import daily_loss_streak


def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)


def replay_counter(protocol,recorded_entries):
    fills={};by_position=defaultdict(list)
    for deal in protocol['actual_deals']:
        key=str(deal['ticket']);position=str(deal['position_id'])
        fills[key]={'ticket':int(key),'position_id':position,'entry_type':deal['entry'],'deal_type':deal['type'],
            'time_utc':deal['time_utc'],'volume':deal['volume'],'profit':deal['profit'],
            'commission':deal['commission'],'swap':deal['swap'],'fee':deal['fee'],
            'strategy':'unknown','manual_test':is_manual_broker_test({'comment':deal.get('comment','')}),
            'attribution':'broker_comment_only'}
        by_position[position].append(deal)
    positions=rebuild_positions(fills,set())
    requests={str(row['status']['execution']['broker_order_id']):row for row in recorded_entries}
    events=[]
    for position,row in positions.items():
        if row['manual_test']:continue
        if row['state']!='closed':raise ValueError('complete_recorded_position_required')
        entry=[d for d in by_position[position] if d['entry']==0]
        orders={str(d['order']) for d in entry}
        if len(orders)!=1:raise ValueError('scale_in_counterfactual_not_supported')
        order=next(iter(orders))
        if order not in requests:raise ValueError('recorded_autonomous_entry_link_required')
        at=min(stamp(d['time_utc']) for d in entry)
        if at.replace(hour=0,minute=0,second=0,microsecond=0)<stamp(protocol['start_utc']):
            raise ValueError('full_UTC_risk_day_history_required')
        events.append((at,row,requests[order]))
    events.sort(key=lambda x:(x[0],int(x[1]['position_id'])))
    limit=min(int(protocol['settings']['max_consecutive_losses']),int(protocol['limits']['loss_streak']))
    admitted=[];decisions=[]
    for at,row,request in events:
        # Broker entry time is authoritative. The execution log may be written
        # AFTER a very fast stop-out and must not leak that loss into admission.
        before=daily_loss_streak(admitted,at-timedelta(microseconds=1))
        allowed=before['consecutive_losses']<limit
        if allowed:admitted.append(row)
        decisions.append({'broker_entry_utc':at.isoformat(),'execution_log_utc':request['at'],
            'strategy':request['status']['chosen']['strategy'],'loss_streak_before_entry':before['consecutive_losses'],
            'effective_loss_streak_limit':limit,'counter_would_admit':allowed,
            'recorded_net_if_same_fills':row['net_profit'],
            'stop_points':request['status']['chosen']['stop_loss_points']})
    end=daily_loss_streak(admitted,stamp(protocol['end_utc'])-timedelta(microseconds=1))
    return {'scope':'Counter-only causal replay, holding the recorded signals/fills fixed; not a complete strategy or tick-path replay.',
        'decisions':decisions,'end_loss_streak':end['consecutive_losses'],
        'counter_would_block_further_entry':end['consecutive_losses']>=limit,
        'recorded_net_for_admitted_positions':round(sum(row['net_profit'] for row in admitted),2),
        'actual_first_two_losses_prevented_by_counter':sum(not d['counter_would_admit'] for d in decisions[:2]),
        'orders_sent':0,'live_state_changed':False}
