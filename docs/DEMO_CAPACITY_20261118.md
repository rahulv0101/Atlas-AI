# Actual demo capacity: read-only check

On 18 November 2026, the configured connected XAUUSD demo account was checked
without account switching, login, order submission or setting changes. The
quote used was approximately one second old after broker-clock conversion.

**All 47 historical corrected-stop samples fit the current minimum-lot risk
budget and available-margin checks**, using the existing 0.5% risk fraction
and 0.01-lot cap. Risk calculations used the more conservative of balance and
equity, current broker profit conversion, the broker minimum lot and six points
of modeled round-trip slippage. Margin was calculated at the current quote.

The R10,000 historical research scenario's affordability failures must not be
generalized to the current demo account. The live account has different capacity.
Exact account figures and per-case headroom remain in local signed reports;
the portable summary exports no account identifier or balance.

This does not demonstrate a profitable corrected strategy. Historical stop
distances were assessed at current quotes/conversion, not through a new
historical portfolio simulation. Commissions, swap, gap slippage and remaining
day/week loss budgets were not verified. New candidate stops can differ from
these samples. Capacity is not approval to trade or permission to loosen limits.

The next strategy experiment must declare its capital scenario explicitly and
keep it separate from actual-account capacity. The earlier corrected backtest
remains valid for its R10,000 scenario; its zero entries are not a claim of zero
live opportunity. No strategy was activated by this check.

Reproduce with `python -m tools.demo_capacity_check` inside the project virtual
environment. The tool refuses a different account, non-demo account, different
symbol, stale quote or unsupported minimum lot. Login and order submission are
denied. Six focused tests cover unavailable risk and risk/margin rejection.
