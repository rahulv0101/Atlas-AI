# Verified automated demo broker lifecycle ? 10 November 2026

The operator explicitly selected a labelled automated demo lifecycle test with all risk limits retained. The test completed successfully on the exact configured demo account at **08:27:10?08:27:12 SAST**.

- One XAUUSD buy entry of 0.01 lot was sent through ExecutionGate and the native adapter. Broker entry order: 142359066; entry deal: 111824340.
- The broker open-position readback confirmed stop loss 4121.39 and take profit 4125.29. Estimated stop risk before entry was R24.55, below the existing R603.56 per-trade budget.
- One position-specific close was sent. Exit order: 142359067; exit deal: 111824341.
- Broker history confirmed balanced 0.01 entry/exit volume. Independent account inventory confirmed zero open positions and zero pending orders.
- Recorded net test result: **-R5.89**. The script completed in 1.188 seconds, within the 30-second target. No duplicate entry or close was sent.
- Entry provenance was `AAI_Dmanual_Smabr`; the exit is tied to the same broker position. The test is excluded from natural strategy evidence. Durable autonomous decision count remains zero.

This verifies the broker mechanics path: gated entry, installed protective levels, position-specific close and broker confirmation. It does **not** establish profitable strategy selection or a naturally selected autonomous trade. The separate natural lifecycle observer remains active.

Existing risk fraction 0.5%, daily/weekly drawdown limits 3%/6%, advisory-only Gemini, demo account restrictions and strategy entry thresholds were retained. No global execution-policy or research-promotion setting was changed.

Validation: 75 diagnostic/native-close/execution-audit regression cases passed before execution. The default tool mode is preview; sending an order requires explicit --execute. Both preflight and the broker run were saved separately. The existing older manual test helper was not used.

Evidence:
- `docs/diagnostics/demo_lifecycle_diagnostic_tests_20261110.xml`
- `docs/diagnostics/demo_lifecycle_live_preflight_20261110.json`
- `docs/diagnostics/demo_lifecycle_broker_run_20261110.json`
- `docs/diagnostics/demo_lifecycle_independent_verification_20261110.json`
- `storage/broker_diagnostic_verification.json`

The verified diagnostic summary is also available in runtime flags under `broker_mechanics_verification`. Natural strategy proof remains a separate field and has not been marked verified.
