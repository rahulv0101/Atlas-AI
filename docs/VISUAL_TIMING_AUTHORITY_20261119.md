# Visual timing authority correction

The operator requested investigation and repair of unverified visual vetoes.
`rebase_visual_observation` validated screenshot age, a window flag, symbol and
timeframe metadata, but did not establish which screenshot candle corresponded
to the current closed market-data bar. `build_evidence_alignment` explicitly
reports screen_bar_matches_current=null and same_bar_mapping_verified=false.
Meanwhile `_timing_discipline_snapshot` added four hard visual conditions when
visual_watch_used_for_decision was set. This contradicted advisory_only=true.

The timing gate now treats viewport location, momentum, direction and blended
confirmation as observations only. They cannot add missing timing requirements,
reduce the timing score or substitute for absent candle location/momentum.
Candle timing, session, loss-history, confluence, risk and execution checks remain.
Timing status retains visual labels and explicitly reports visual_advisory_only,
visual_watch_observed and visual_watch_used=false. Legacy producer metadata does
not grant timing authority. No claim of verified pixel-to-candle alignment is made.

Tests verify that adverse viewport labels cannot veto clean candle timing,
positive viewport labels cannot rescue weak or missing candle evidence, and the
existing M5 confluence and retest rules continue to hold. The test run also exposed
legacy unit fixtures with no timeframe settings; timing observation now uses the
existing legacy M1 fallback for those callers. Configured M5 remains M5.

This is a bounded timing-policy correction, not proof of a profitable strategy
or a reason to force an order. Earlier frozen collector records are not rewritten.
