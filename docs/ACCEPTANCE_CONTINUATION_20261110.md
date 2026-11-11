# Feasible observation window for strategy and lifecycle acceptance

Fixed an observation-planning defect: the frozen paper model permits at most six trades per UTC trading day, while its first and validation stages each require thirty completed cases. Sixty cases require at least ten trading days even at the maximum rate. A seven-calendar-day watch window cannot complete both stages. Slower signal frequency, daily loss stops and unaligned setups can require substantially longer; extending time does not guarantee qualification.

The existing strategy, source freeze, account scope, cost assumptions, thirty-case stages, minimum-day rules, profit-factor requirement, drawdown bound and no-promotion boundary are unchanged. Both current collectors remain running. A new bounded read-only supervisor retains their evidence and can resume compatible frozen collectors when an individual seven-day invocation ends or a collector exits.

## Observation plan

The saved plan is `storage/acceptance_plan.json`; progress is `storage/acceptance_plan.status.json`. Its absolute deadline is December 10, 2026 at approximately **21:51 SAST**, thirty calendar days after the original paper freeze. This is an observation deadline, not a predicted pass date. Each paper invocation remains bounded to at most 168 hours and each natural observer invocation to at most 10,080 minutes. Checkpoints, the original journal, the original freeze time and the same fixed first/subsequent thirty cases are retained across invocations.

The supervisor:

- Reuses already locked/running collectors rather than starting duplicates.
- Starts only read-only `watch`/`--resume` commands from the preserved source snapshot. It cannot approve or submit a trade, change parameters, start the backend or activate an experimental strategy.
- Requires the configured account scope, broker timezone, dependency versions, immutable manifests, complete source snapshot and compatible natural-lifecycle checkpoint to match.
- Validates paper artifact checksums before restarting a stopped paper collector; corrupt or incomplete evidence requires review rather than an empty restart.
- Limits new collector starts to three per role per hour and stops renewing at the overall deadline or when the relevant evidence window is complete.
- Waits for an explicitly running backend before starting stopped collectors, and refuses new collector starts while the persisted operator sleep flag is active. Existing collector shutdown behavior is unchanged.

The current-user sign-in launcher added on November 11 resumes the saved supervisor after reboot and sign-in. It does not run before sign-in or start the trading backend. It retains the original deadline and checks the plan and frozen evidence before launching; an already running supervisor is reused. Manual resume remains available:

```powershell
.venv\Scripts\python.exe tools/supervise_acceptance.py watch --plan storage/acceptance_plan.json
```

Install or remove the reversible current-user Startup shortcut with:

```powershell
.venv\Scripts\python.exe tools/acceptance_startup.py install
.venv\Scripts\python.exe tools/acceptance_startup.py remove
```

No administrator privileges, scheduled trading task or backend wake are involved. Launcher results are recorded in `storage/acceptance_supervision/startup.status.json`; existing supervisor logs remain in that directory. An expired plan is a no-op and a corrupted plan fails closed. The shortcut remains installed until removed.

The supervisor also refreshes `storage/acceptance_execution_costs.json` each minute from the existing dispatch journals. Progress includes report freshness, natural/diagnostic sample counts and invalid-row counts. Report failures are visible without stopping independent collectors. This measures new fills when they occur; it never manufactures fills, declares calibration ready from a fixed arbitrary sample size, or substitutes measured costs into the frozen experiment.

A process lock rejects duplicate supervisors. The existing backend watchdog/startup workflow is unchanged. A source, account, clock or integrity failure stops supervision for review. No automatic reset of failed strategy evidence is allowed.

## Verified current progress

At the live check, the paper run had completed **one case in its first thirty-case stage**, with a modeled result of approximately **-0.244R**; validation remained at zero. One case neither establishes nor rules out an edge. A read-only signal-funnel check confirmed four completed M15 bars after the original freeze and one directional, H1-aligned candidate. The first case therefore establishes that the prospective signal/evaluation path is collecting; it does not establish profitability.

The natural broker observer still has zero verified strategy-selected cycles. The prior labelled demo diagnostic remains excluded. The backend is responding and its latest decision was the existing session-cutoff/flat safeguard. No broker order was sent during this repair.

Paper qualification and natural broker execution are separate evidence streams. The supervisor reports the broker cycle's attributed strategy and never treats an unrelated natural trade as proof of the new paper model. Same-version strategy linkage and any activation require concrete operator review. Even when both evidence streams contain results, `broker_eligible` remains false in supervision.

## Validation and deployment

Forty-three supervision, checkpoint, prospective-data and runtime-reliability tests passed. Cases cover the minimum ten-trading-day bound, continuation with unchanged manifests, bounded weekly commands, checkpoint resume, duplicate avoidance, stopped-backend/sleep behavior, deadline and restart budgets, corrupted source/data rejection, manual/diagnostic exclusion and prevention of automatic cross-strategy promotion.

The first live supervision check verified source/checkpoint compatibility, found the existing backend and both collectors, and reused both without a restart. The long-running supervisor then published fresh progress with zero orders and no errors. The backend, original paper run and natural observer stayed online. The deadline was extended only in the operational continuation plan; no frozen hypothesis or pass criterion was edited.

The two requested acceptance outcomes remain pending actual evidence: enough subsequent cases must pass both stages, and an eligible strategy must independently complete a natural protected broker lifecycle. Neither outcome can be manufactured by advancing timestamps, reusing inspected historical outcomes as future data or forcing an entry.
