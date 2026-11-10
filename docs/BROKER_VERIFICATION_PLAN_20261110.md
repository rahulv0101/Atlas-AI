# Broker verification: concrete next action

The current demo account passes native order preflight and has no positions or pending orders. The active strategies are rejecting the latest entry on timing/location/momentum grounds. Generated strategies are under an explicit research-only configuration; there is no enabled automatic promotion from this worker into broker trading. A candidate's paper performance cannot itself complete broker lifecycle verification.

Two different outcomes must remain separate:

1. **Controlled automated broker mechanics test:** one XAUUSD buy of 0.01 lots on the exact configured demo account, 150-point stop and 240-point target, with broker protection readback, a timed position-specific close within 30 seconds, and balanced broker-history confirmation. This is a diagnostic, excluded from strategy performance and natural autonomous acceptance. Preview at 05:56 UTC / 07:56 SAST estimated stop risk R24.55 and margin R134.97, versus the existing per-trade risk budget R603.56. These figures must be recalculated immediately before any execution; they are estimates, not a guaranteed loss ceiling. All existing account, risk, kill/sleep, session, reconciliation and execution gates remain active. No blind retry is allowed after an ambiguous result. No order has been sent by this preview.
2. **Natural strategy-selected broker cycle:** the normal trader must produce an eligible signal and pass its existing checks. Its occurrence cannot be scheduled or guaranteed, and a controlled diagnostic cannot be labelled as this proof.

The operator has been asked which outcome is intended before any diagnostic order or entry-policy change. AGENTS.md requires execution-policy changes to be explicit. No strategy thresholds, risk limits, promotion rules or live-money settings have been changed during this investigation.

Preview evidence: `docs/diagnostics/broker_lifecycle_test_plan_20261110.json`.
