# Settled forecast outcome evaluation

The separate research evaluator now runs against the retained signed v3 forecast
journal and settled-candle checkpoint. It never attaches to MT5 or sends orders.
Its own signed protocol freezes its source hash, input protocol, registration time,
12-M5-bar horizon, three-point adverse slippage per side, spread model and
stop-first handling when OHLC touches both levels. Source/checkpoint/journal
changes during a read defer publication. Incomplete candle sequences are explicit.

Entry is modeled at the recorded scheduled future M5 bid open. Buys pay entry
spread; sells use each exit bar's recorded spread to model ask. Stops gap adversely;
targets do not gain favorable gap fills. Outcomes are net price R after the stated
spread/slippage model. Additional cost is zero: commissions/swaps are not calibrated,
so reports explicitly exclude qualification. Bar spread cannot reproduce intrabar
ask extremes or actual broker fills. Bars are settled observations, not tick paths.

All directional raw candidates are evaluated separately and can overlap. This is
candidate research, not a portfolio or full live-gate replay. No independent-trade
count, 30-trade qualification stage, risk-sized money profit or natural broker proof
is inferred. Earlier forecasts are diagnostic; only forecasts published after
protocol registration receive the prospective label. Protocol was registered
before those future observations, not after their outcomes became known.

The startup hook resumes the configured evaluator only within storage, with the
same collector, unchanged source and future source deadline. Review-blocked state
is not reset. A process lock prevents duplicate evaluation. The shared research
answer path exposes pending, prospective and diagnostic counts without claiming
broker execution. No Windows reboot was performed to test the new hook.

Operational report at launch: four pending candidates, zero resolved; this is a
snapshot, not a claim that no later outcome exists. The collector and evaluator
continue independently of the chat. Automatic visible MT5 cycling remains a
separate unfinished integration; outcome collection does not require it.
