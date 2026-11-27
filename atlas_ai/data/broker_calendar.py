"""Date- and instrument-scoped published broker close exceptions.

This can restrict the normal session window, never open a market or grant entry.
Reopening remains subject to normal sessions and independently fresh quotes/bars.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

SOURCE = 'https://www.hfm.com/int/ar/trading-instruments/trading-hours'
VERIFIED_AT = '2026-11-26'
PUBLICATION_TIMEZONE = timezone(timedelta(hours=2))
HFM_XAUUSD_EARLY_CLOSE = {'2026-11-26': '21:30', '2026-11-27': '21:45'}


def market_hours(broker, symbol, now):
    if now.tzinfo is None:
        raise ValueError('aware_market_calendar_time_required')
    result = {'applicable': False, 'broker': broker, 'symbol': symbol}
    if broker != 'HFM' or symbol != 'XAUUSD':
        return result
    local = now.astimezone(PUBLICATION_TIMEZONE)
    value = HFM_XAUUSD_EARLY_CLOSE.get(local.date().isoformat())
    if value is None:
        return result
    hour, minute = map(int, value.split(':'))
    close = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return {**result, 'applicable': True, 'calendar_status': 'published_broker_early_close',
            'market_closed': now >= close, 'close_utc': close.astimezone(timezone.utc).isoformat(),
            'close_south_africa': close.isoformat(), 'minutes_to_broker_close': max(0, int((close-now).total_seconds()//60)),
            'source': SOURCE, 'verified_at': VERIFIED_AT,
            'reopening_time_verified': False,
            'note': 'Published GMT+2 close exception only; normal sessions and fresh data are still required.'}


def restrict_session(base, hours, *, close_buffer_minutes):
    if not hours.get('applicable'):
        return base
    close = datetime.fromisoformat(hours['close_utc'])
    window = base.session_window_local
    if window and '->' in window:
        start, end = window.split('->', 1)
        end_dt = datetime.fromisoformat(end)
        if close < end_dt:
            window = start + '->' + close.astimezone(end_dt.tzinfo).isoformat()
    if hours['market_closed']:
        return replace(base, allowed=False, reason='broker_market_closed', session_active=False,
                       minutes_to_close=0, session_window_local=window,
                       calendar_status=hours['calendar_status'])
    if not base.session_active or base.minutes_to_close < 0:
        return base
    if hours['minutes_to_broker_close'] >= base.minutes_to_close:
        return base
    minutes = min(base.minutes_to_close, hours['minutes_to_broker_close'])
    if minutes <= close_buffer_minutes:
        return replace(base, allowed=False, reason='broker_close_no_new_trades', minutes_to_close=minutes,
                       session_window_local=window, calendar_status=hours['calendar_status'])
    return replace(base, minutes_to_close=minutes, session_window_local=window,
                   calendar_status=hours['calendar_status'])
