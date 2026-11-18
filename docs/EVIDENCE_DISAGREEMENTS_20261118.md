# Selected signal, analysis direction and visual location

The selected strategy signal and the analysis engine's preferred market
direction are distinct outputs. A BUY analysis is not approval of a selected
SELL candidate. The UI now displays WAIT for a directional conflict, lists both
directions, and distinguishes that advisory conflict from a recorded execution
block. It never invents a gate rejection when runtime evidence is absent.

Candle location uses recent OHLC range position and trend. Visual location
uses a screen vertical-position heuristic. A viewport mid-range label is not
a calibrated measurement of a structural pullback or retest. The evidence
diagnostic now records both methods, their labels and whether they disagree.
Even matching labels do not certify that the screenshot and candles map to
the same bars or prices. Pixel/bar mapping remains unverified.

Existing runtime timing observations supply the UI's disagreement explanation.
The additional Python evidence metadata becomes available when that module is
next loaded; no active backend was restarted for this reporting change.

This change repairs reporting and exposes evidence uncertainty. It does not
repair or validate the visual location classifier, flip a selected strategy,
remove a visual veto, alter confidence or grant execution authority. Gate
policies and live behavior remain unchanged. A calibrated chart/bar mapping
and independently tested visual location model remain outstanding work.
