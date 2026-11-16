# Strategy qualification and environment audit

The new strategies have not demonstrated sufficient executable, positive-cost
evidence. No strategy was activated or relabelled as qualified by this audit.

## What failed

The earlier SMC v5 comparison (`storage/smc_entry_comparison_20261113`) recorded:

| Research model | Complete candidate observations | Minimum-volume risk/margin rejections | Simulated trades |
|---|---:|---:|---|
| Event retest (OB/FVG) | 13 | 12 | One development loss; zero validation/holdout trades |
| Sweep and reclaim | 67 | 66 | Zero development/validation trades; one holdout win |

These counts belong to the earlier frozen implementation and settings. They
are not evidence for a newly repaired code version. One winning holdout trade
does not qualify a model that failed its development requirements.

The fixed structural M5 proposal from November 16 generated seven candidates.
Its receipt-bound replay reproduced every original result field unchanged:

- Six were rejected by entry-timeframe momentum: three weak and three mixed.
- Four of those six were also classified as mid-range by the shared chart gate.
- One passed timing but required R97.14 of minimum-lot stop risk, against the
  nominal historical R50 risk budget, before additional modeled friction.
- Both research periods had zero trades and failed qualification.

These overlapping timing counts must not be added together as independent
candidates. Internal `m1_momentum` reason identifiers are legacy compatibility
names: the trace explicitly records M5, and the calculation uses M5 candles.

The structural detector and shared timing gate measure different things. A
confirmed break/retest is not necessarily strong momentum under the shared
eight-return and candle-body test. Nor does a retest automatically imply a
fresh location in the shared twenty-bar range classifier. This is a research
compatibility issue to investigate, not proof that either rule should be bypassed.

## Work needed to earn qualification

A separately versioned confirmation-after-retest hypothesis is a reasonable
next experiment: wait for actual closed-M5 momentum confirmation while the
original structural invalidation remains intact, expire stale setups and keep
the episode's full protection. Freeze its maximum confirmation delay and rules
before evaluating outcomes. Do not simply relabel weak momentum as strong or
replace the shared location evidence with a strategy's assertion.

That new hypothesis has **not been implemented, tested or activated by this
audit**. It must be evaluated independently, with fees, slippage and minimum-lot
risk retained. Prior inspected periods are exploratory, not a new blind test.
The existing structural review requires both periods to have at least thirty
trades across two dates, positive mean net R, PF >= 1.1 (or all wins), and
drawdown <= 6R. Passing still needs independent forward evidence and explicit
activation. There is no assured path to passing.

## Environment findings

- Local `.env`: 78 keys; no malformed entries, duplicate keys, old-account
  paths or invalid values in the audited positive numeric settings.
- M5 entries and Daily/H4/H1/M15 confluence are configured.
- The MT5 terminal executable exists; `.venv` references the current account's
  installed Python, not the old `C:\Users\User` installation.
- `.env` has an empty Gemini key entry. The current shell inherits a nonempty
  key matching the Windows user environment. Atlas intentionally gives process
  environment variables precedence over `.env` defaults.
- Current backend status reports Gemini enabled and Gemini trade influence
  disabled, consistent with advisory-only operation. API authentication was not
  tested here. Current status also reports M5 and no cycle error.
- Real-live execution remains disabled. No credentials were printed, copied,
  changed or committed. No backend restart was needed.

The template now explains key precedence and that `EXECUTE_TRADES` alone cannot
grant real-money execution. Local trading parameters were not changed.

## Repeatable check

Run from the project root:

```powershell
.venv\Scripts\python.exe -m tools.audit_strategy_environment `
  --structural storage/m5_structural_retest_20261116 `
  --baseline storage/m5_calibration_20261116_v3 `
  --output storage/strategy_environment_audit_20261116.json
```

The tool reports key presence and names of conflicting settings without values.
It validates frozen receipts and policy hashes, denies broker initialization
and order dispatch during replay, and rejects any reproduction that differs
from the recorded portfolio result. The report remains in ignored storage.
