# Demo-representative corrected-distance comparison

This experiment freezes R100,000 virtual initial capital: the largest power
of ten not above both balance and equity in the signed matching-demo capacity
snapshot. It is an explicit conservative research scenario, not a deposit
recommendation or a change to the broker account.

Both unchanged and corrected geometry use that same capital, the existing
0.5% risk fraction, 0.01-lot cap, frozen conversion/cost assumptions, pilot
limits and shared policy replay. The R10,000 control is not reused: both lanes
are replayed. No other parameter is searched or selected from outcomes.

Independent run directories are:

- `storage/demo_representative_m5_primary_20261118`
- `storage/demo_representative_m5_april_20261118`

Each run freezes its source/protocol and candidate stream, writes a signed
checkpoint after each lane and a signed combined report when complete. A
progress file alone is not a completed result. The long-running processes
can finish writing these artifacts without another assistant turn.

These are previously inspected historical periods, not blind or prospective
validation. Commissions, historical broker/approval/learning state and full
live parity remain unverified. No model, paper observer or broker authority
is activated by this job. Live settings are unchanged. Automatic visible
chart switching and natural strategy-selected broker lifecycle verification
remain separate outstanding tasks.

Reproduce with `tools.replay_corrected_m5`, the existing period/output options,
and `--capital-profile storage/demo_capacity_20261118T120951Z`. The local
capacity receipt is private; only its hash and rounded virtual scenario are
included in the research protocol. Thirteen focused tests cover conversion,
future-candle exclusion, unchanged candidate identity and bounded capital choice.
