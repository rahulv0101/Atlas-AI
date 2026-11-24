"""Account-wide trading P/L separated from typed MT5 funding operations."""
from datetime import timedelta
from decimal import Decimal

FUNDING = {2, 3, 5, 6}  # balance, credit, correction, bonus
CANCELED = {13, 14}  # reversal via balance operation needs explicit reconciliation


def calculate(account, deals, now, timestamp):
    if deals is None: raise ValueError('broker_account_history_unavailable')
    def money(value):
        value = Decimal(str(value))
        if not value.is_finite(): raise ValueError('invalid_account_money')
        return value
    balance, equity, credit = (money(getattr(account, k, 0)) for k in ('balance', 'equity', 'credit'))
    floating = equity-balance-credit
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day-timedelta(days=day.weekday())
    rows = []; seen = set()
    for deal in deals:
        ticket = int(deal.ticket)
        if ticket in seen: raise ValueError('duplicate_broker_deal')
        seen.add(ticket)
        at = timestamp(deal)
        if not week <= at <= now: continue
        kind = int(deal.type)
        if kind in CANCELED: raise ValueError('canceled_deal_requires_reconciliation')
        if kind not in set(range(18)): raise ValueError('unknown_broker_deal_type')
        net = sum((money(getattr(deal, k, 0)) for k in ('profit', 'commission', 'swap', 'fee')), Decimal(0))
        rows.append((at, kind, net))
    result = {'verified': True, 'currency': str(getattr(account, 'currency', 'unknown')),
              'scope': 'all account trades and trading charges; not Atlas-only attribution',
              'basis': 'UTC realized non-funding deals plus current floating equity less account credit',
              'checked_at': now.isoformat(), 'floating_pnl': float(floating)}
    for name, start in (('day', day), ('week', week)):
        selected = [(kind, net) for at, kind, net in rows if at >= start]
        realized = sum((net for kind, net in selected if kind not in FUNDING), Decimal(0))
        funding = sum((net for kind, net in selected if kind in FUNDING and kind != 3), Decimal(0))
        changes = sum((net for kind, net in selected if kind != 3), Decimal(0))
        opening = balance-changes
        denominator = opening if opening > 0 else balance-realized
        pnl = realized+floating
        loss = max(Decimal(0), -pnl/denominator) if denominator > 0 else Decimal(0)
        result[name] = {'start_utc': start.isoformat(), 'realized_pnl': float(realized),
                        'net_funding': float(funding), 'opening_balance': float(opening),
                        'pnl_including_floating': float(pnl), 'loss_fraction': float(loss)}
    return result
