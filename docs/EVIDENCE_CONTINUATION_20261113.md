# Evidence collection repair and reboot verification

On 13 November the original experiment had 10/30 first-stage paper outcomes, no validation cases, no verified natural cycle and no measured natural fills. The frozen learner had zero selected forward paper trades. These results remain unproven; no thresholds, strategies, risk limits, execution controls or frozen outcomes were changed to obtain trades.

## Natural observer storage handoff

The frozen natural observer resolved its default relative storage against the frozen source directory. Its lock and published status therefore differed from the supervisor's authoritative active-storage path. The supervisor failed to see the running observer, attempted duplicate launches and exhausted its restart budget; the frozen observer's duplicate lock blocked those launches.

The supervisor now supplies an absolute `STORAGE_DIR` from its validated plan to frozen workers. The known observer was replaced once to repair the handoff, resuming the same journal and account-scoped checkpoint. Source snapshots, baseline, managed-position evidence and restart counters were retained. The repaired observer holds the authoritative lock and publishes fresh broker-health/lifecycle status into active Atlas storage. Historical coverage limitations remain; this repair does not reconstruct missed observations or prove an earlier lifecycle.

One archived analysis-eligible publication was also inspected. Its actual action was blocked by timing discipline. Analysis eligibility is not execution approval. The decision-analysis metadata now explicitly exposes analysis eligibility, retains the compatibility field, and leaves authoritative gate approval unknown rather than inferring it from a high score. Timing results are shown separately. This changes reporting, not the actual eligibility rule or execution pipeline. Existing frozen recordings are unchanged.

## Real reboot evidence

The Windows Startup-folder shortcut now supplies `--at-logon`. The local launcher records separate sign-in and manual receipts with the current boot identity and a fresh startup health result. It never treats an older success file as health evidence for a new invocation. A preserved installation baseline prevents a same-boot manual test from being called a reboot test.

Inspect with `tools/verify_atlas_startup.py`, the Learning & Verification card, or Ask Atlas's “startup verification” question. Until an approved restart and Windows sign-in actually occur, verification remains pending. Restarting Windows interrupts open work and Atlas, so the restart requires explicit timing approval. No reboot was issued while that approval was pending.

A completed paper experiment, measured natural execution costs and an autonomous lifecycle still require real new outcomes. Their original deadlines and no-forced-trade boundaries remain active.

Validation: 106 focused tests passed (`docs/diagnostics/evidence_continuation_20261113.xml`). Archive integrity verified 302 recorded publications at the check. The restarted supervisor reports both original collectors running, and the frozen learner remains running separately. Reporting-code changes load with the next component restart; the running trader was not hot-swapped. The reboot verifier currently reports `pending_reboot`.
