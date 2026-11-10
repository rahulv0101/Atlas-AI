# Dashboard clarity update - 9 November 2026

Atlas opens in a focused Overview with trade readiness, a plain-language waiting
reason, the R1,000 demo objective and verified performance evidence. Account risk,
price chart and safety checks remain visible. Detailed analysis is available in
Diagnostics. Trading settings are grouped in a labelled disclosure.

Ask Atlas now has a labelled input, suggested questions that fill and focus the
input without submitting, and direct links from the overview. Keyboard focus is
visible. The layout adapts to desktop, tablet and phone widths.

Timing explanations use structured missing conditions. The compact status API
now includes those fields; previously they were only available in full status.
The header and entry-status tile use the same API readiness classification.
Raw decision text remains under Technical details. Long reasons wrap correctly.
Trading strategy, risk limits, order routing and Gemini authority are unchanged.

Validation:
- 96 UI/API tests passed, with zero failures or errors (tests.xml).
- JavaScript syntax and scoped Git whitespace checks passed.
- Isolated Chrome verified Overview/Diagnostics switching, settings disclosure,
  suggested-question focus without submission and compact timing data.
- No browser page errors; no horizontal overflow at 1440, 768 or 390 pixels.
- Desktop and mobile screenshots were visually reviewed.
- Browser verification intercepted all POST requests, including the existing
  automatic operator-panel queries; it did not execute commands or orders.
- Normal desktop launcher completed SUCCESS / backend_healthy_desktop_ready.

Artifacts are in docs/diagnostics/ui_20261109/: tests.xml, browser_checks.json,
overview_desktop.png and overview_mobile.png.

## Refresh reliability follow-up

The freshness display was incorrectly cached when the decision payload stayed
unchanged. Freshness and readiness now participate in display invalidation.
A separate connection indicator shows the last successful UI check; connection
errors are explicit. Refresh now performs a read-only poll, and returning to the
window triggers an immediate poll rather than waiting for the next interval.

Live diagnosis found responding API endpoints and a responding Windows desktop
window. An isolated browser completed three successful scheduled status polls.
This establishes a misleading display condition, not a proven native hang.
Five renderer tests passed. Isolated browser checks verified freshness changing
from 1s to 21s for an unchanged decision, manual refresh, simulated connection
loss and recovery, with zero page errors (refresh_checks.json). All browser
POST requests were intercepted. Only the frontend was stopped before requesting
the normal desktop launcher; no trading-policy settings were changed.

## Actual desktop verification

Accessibility inspection of the running WebView showed its check time lagging
behind the API. It caught up after foreground activation. Main status polling
had skipped hidden documents. That skip is removed; auxiliary operator-panel
polling retains its existing behaviour. A one-second UI heartbeat reports elapsed
time since the last successful status check and explicitly marks delayed polls.
It does not claim that every decision or candle changes each second.

Nine focused tests passed, including delayed polls and connection failures.
A browser check confirmed heartbeat progression and status polling with a hidden
document (background_refresh_checks.json). The desktop wrapper alone was
replaced; the trading backend and durable API were kept running. The actual
Windows accessibility tree then showed the new elapsed-time heartbeat.

## Branding animation

Restored the animated sweep under the Atlas AI title and the scope reticle
animations, which the overview styling had disabled. Browser verification
confirmed the sweep transform changes over time. Reduced-motion preferences
still disable branding motion. The desktop wrapper was reopened for the CSS
update; the backend was left running.

## Setup search visibility

Setup search is visible in Overview again, showing the tracked candidates and
entry-review status. HOLD explanations now distinguish raw directional
candidates that did not pass selection from cycles with no directional
candidate. Twelve renderer/heartbeat tests passed, including buy and sell
candidates under HOLD. Browser checks confirmed populated setup search and no
horizontal overflow at desktop, tablet and phone widths. Strategy, selection,
timing, risk and execution policies were not changed. The retained event audit
is in docs/diagnostics/setup_activity_20261109.json; it is not a profitability
or missed-opportunity assessment.
