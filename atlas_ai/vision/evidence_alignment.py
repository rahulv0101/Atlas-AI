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
    minutes={"M1":1,"M5":5,"M15":15,"M30":30,"H1":60,"H4":240}.get(timeframe.upper())
    evaluated=now or aware_time(clock.get("ended_at")) or aware_time((status or {}).get("updated_at")) or datetime.now(timezone.utc)
    closed=(bar+timedelta(minutes=minutes) <= evaluated) if bar and minutes else None
    return {"bar_utc":bar.isoformat() if bar else None,"bar_closed_at_evaluation":closed,
        "evaluated_at":evaluated.isoformat(),
        "timeframe":timeframe,"timestamp_basis":"UTC" if bar else "unverified",
        "momentum_method":"eight_candle_changes_and_latest_body_ratio"}


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
    summary=f"{candle['timeframe'] or 'Candle'} momentum: {indicator}; chart viewport movement: {pixels}."
    if forming:summary+=" The indicator used a forming candle."
    summary+=" These are different measures; screenshot bar alignment is unverified."
    return {"indicator":{**candle,"momentum":indicator},
        "visual":{"momentum":pixels,"method":"viewport_pixel_displacement",
            "captured_at":(visual or {}).get("captured_at"),"feature_bar_utc":source.get("bar_utc")},
        "feature_bar_matches_current":feature_match,"screen_bar_matches_current":None,
        "momentum_relation":relation,"summary":summary,"advisory_only":True,
        "policy_note":"Agreement of labels is not proof of aligned bars; this comparison cannot approve entries or change timing rules."}
