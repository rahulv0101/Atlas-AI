# ATR conversion capacity check

The existing unit-corrected research adapter was applied to the original 47
entries in the receipt-bound deployed-M5 diagnostic. Closed-candle rolling ATR
was converted from price to broker points using the frozen point size. Side,
confidence, risk fraction, lot cap and existing affordability checks stayed fixed.

**Zero of the 47 corrected entries fits the R10,000 virtual scenario**, using
0.5% maximum per-trade risk and the existing 0.01-lot cap/minimum-volume rules.
The detailed evidence and source receipt are in
`CORRECTED_M5_CAPACITY_20261118.json` and the signed local report at
`storage/corrected_m5_capacity_20261118`.

This is an affordability screen at previously selected entry times, not a new
candidate-generation or portfolio backtest. It cannot prove corrected strategy
profitability, expected frequency, or that the current demo account is too small.
The account's actual capital was not read or changed. No native broker request,
order, stop adjustment, policy activation or live strategy modification occurred.

Do not resolve a minimum-lot rejection by making stops artificially tighter,
increasing risk or requesting more capital. A later full corrected-geometry
study must freeze its capital scenario explicitly, regenerate opportunity
selection where needed and retain all shared gates. The existing conversion
adapter remains research-only until that comparison and separate validation
support a bounded deployment decision. Prior related failed experiments remain
valid negative evidence; this screen does not supersede them.
