"""Describe evidence clocks and measures without overriding any entry gate."""
from datetime import datetime, timedelta, timezone


def aware_time(value):
    try:
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError,TypeError):return None


def candle_evidence(status, now=None):
    status=status if isinstance(status,dict) else {}
    clock=status.get("market_data_clock") or {}
    clock=clock if isinstance(clock,dict) else {}
    bar=aware_time(clock.get("latest_bar_utc")) if clock.get("timestamp_basis")=="UTC" else None
    timeframe=str((status or {}).get("timeframe", ""))
    snapshot = status.get("decision_snapshot") or {}
    pinned = bool(status.get("decision_id") and snapshot.get("decision_id") == status.get("decision_id"))
    candle = (snapshot.get("candles") or {}).get(timeframe, {}) if pinned else {}
    # Feed freshness includes the forming native row. It is not the candle used
    # by a scan whose indicators were calculated from a closed-candle snapshot.
    if snapshot:
        bar = aware_time(candle.get("last_open_utc"))
    minutes={"M1":1,"M5":5,"M15":15,"M30":30,"H1":60,"H4":240}.get(timeframe.upper())
    evaluated=now or (aware_time(snapshot.get("as_of_utc")) if pinned else None) or aware_time(clock.get("ended_at")) or aware_time((status or {}).get("updated_at")) or datetime.now(timezone.utc)
    end = aware_time(candle.get("last_close_utc")) or (bar+timedelta(minutes=minutes) if bar and minutes else None)
    closed=(end <= evaluated) if end else None
    return {"bar_utc":bar.isoformat() if bar else None,"bar_closed_at_evaluation":closed,
        "evaluated_at":evaluated.isoformat(),
        "timeframe":timeframe,"timestamp_basis":"UTC" if bar else "unverified",
        "momentum_method":"eight_candle_changes_and_latest_body_ratio",
        "evidence_basis": "decision_closed_candle_snapshot" if candle else "legacy_feed_clock_unpinned"}


def build_evidence_alignment(status, visual, indicator_momentum=None):
    status=status if isinstance(status,dict) else {}
    visual=visual if isinstance(visual,dict) else {}
    chart=status.get("chart_features") or {}
    chart=chart if isinstance(chart,dict) else {}
    pixels_features=visual.get("visual_features") or {}
    pixels_features=pixels_features if isinstance(pixels_features,dict) else {}
    candle=candle_evidence(status)
    indicator=str(indicator_momentum or chart.get("momentum_state") or "unknown")
    pixels=str(pixels_features.get("visual_momentum") or "unknown")
    source=(visual or {}).get("candle_evidence") or {}
    source=source if isinstance(source,dict) else {}
    current_bar=aware_time(candle["bar_utc"]);source_bar=aware_time(source.get("bar_utc"))
    feature_match=(current_bar==source_bar) if current_bar and source_bar else None
    relation="missing" if "unknown" in (indicator,pixels) else "agree" if indicator==pixels else "different"
    forming=candle["bar_closed_at_evaluation"] is False
    indicator_location=str(chart.get('location_state') or 'unknown')
    viewport_location=str(pixels_features.get('visual_location') or 'unknown')
    location_relation=('missing' if 'unknown' in (indicator_location,viewport_location)
                       else 'agree' if indicator_location==viewport_location else 'different')
    summary=f"{candle['timeframe'] or 'Candle'} momentum: {indicator}; chart viewport movement: {pixels}."
    if forming:summary+=" The indicator used a forming candle."
    summary+=" These are different measures; screenshot bar alignment is unverified."
    return {"indicator":{**candle,"momentum":indicator},
        "visual":{"momentum":pixels,"method":"viewport_pixel_displacement",
            "captured_at":(visual or {}).get("captured_at"),"feature_bar_utc":source.get("bar_utc")},
        "feature_bar_matches_current":feature_match,"screen_bar_matches_current":None,
        "momentum_relation":relation,"summary":summary,"advisory_only":True,
        "location_comparison":{"candle_location":indicator_location,"viewport_location":viewport_location,
            "relation":location_relation,"candle_method":"recent_OHLC_range_position_with_trend",
            "viewport_method":"screen_vertical_position_heuristic",
            "same_bar_mapping_verified":False,
            "note":"A viewport mid-range label is not a verified rejection of a candle pullback or structural retest."},
        "policy_note":"Agreement of labels is not proof of aligned bars; this comparison cannot approve entries or change timing rules."}
