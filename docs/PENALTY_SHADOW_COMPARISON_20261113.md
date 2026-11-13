# Frozen matched confidence-penalty comparison

This is a separate paper experiment. It does not change live strategies, risk limits, timing rules, confidence thresholds, the original frozen paper hypothesis or the learned ranker.

## The two arms

- **Baseline:** replay the existing signal-generation pipeline and both existing timing-learning layers on the captured candidate and learning state.
- **Alternative:** set only the captured historical aggregate loss-class counts to zero inside an isolated replay instance. Keep the dictionary's shape, fingerprint lesson adjustment, regime/session filters and other settings unchanged. If the baseline dictionary is empty, both arms retain the existing early-return behavior.

The published chosen candidate is held fixed. There is no alternate strategy reranking, new strategy generation or separate learning history. Both arms receive the same captured context, learning snapshot, protection distances and simulated outcome. The alternative does not modify Atlas's actual learning state.

Each baseline seed must reproduce the archived post-filter seed and chosen seed. Recomputed baseline analysis must reproduce the captured analysis score. Otherwise the case is excluded with a reason. **Final conviction**, not raw signal confidence, is compared with the same captured effective conviction threshold. Recorded timing must pass in both arms for an admission. These are hypothetical analysis-and-timing admissions: remaining live risk, portfolio, session and execution gates are not verified by this test, so an admission is never broker approval.

## Frozen method and fresh evidence

The experiment manifest freezes the method, source snapshot, settings, scoring environment inputs, cost assumptions, start time and existing acceptance deadline before collecting new cases. It only admits publications created and observed after that freeze. Old results are not reused as new evidence. Archive input hashes and saved-state blobs are verified; a mismatching or missing input is not invented.

Sampling takes the first reproducible directional chosen candidate in each four-hour UTC band, with at most six pairs per date. Full execution horizons cannot overlap. The six bands spread sampling across the day; the cases are still a sampled cohort, not exhaustive market coverage or statistically independent trades. The first 30 resolved pairs form the first stage, and the next 30 form validation. Each stage needs at least ten score-changed pairs and five admission differences to provide enough contrast for review. Reaching 60 cases with no meaningful difference between arms cannot be called validation of a penalty change.

Collection ends at the unchanged acceptance deadline: **10 December 2026 at 21:51 SAST**. Completion timing and adequate contrast are not guaranteed. The separate seven-day activity review still ends on **18 November at 20:31 SAST**.

## Matched costs and outcome labels

The entry is the next full UTC minute after the archive observation. Labels wait for the complete configured M1 holding horizon and continuous closed candles; missing prices are deferred or excluded. Both arms use exactly the same nominal minimum-volume outcome from the broker-unit simulator: bid/ask spread from the observed candles, the frozen reference fee estimate and three points of assumed adverse slippage on each leg, with stop-first ambiguity resolution and the existing research exit rules.

The broker specification is copied from the signed existing guarded-research manifest. Its date and checksum are recorded; it is a frozen reference, not a fresh historical currency/margin reconstruction or a calibrated natural-fill model. No broker API is contacted by the observer.

Only a checksum-committed candle snapshot is used. Each resolved execution horizon is retained and checked against later snapshots; revised data, changed source inputs, changed code or a damaged checkpoint blocks review rather than resetting results. The capture is post-publication paired replay, not an atomic pre-decision checkpoint or proof that a shadow prediction was submitted before entry.

## Operation and interpretation

The acceptance supervisor resumes one frozen observer, respects backend availability/operator sleep for launches, enforces restart limits and keeps other evidence streams independent. State is saved atomically and cases are not counted twice after resume. The dashboard's Learning & Verification card and typed/voice Ask Atlas expose the same read-only progress. Ask “How is the penalty comparison doing?”.

Positive or negative differences show what happened in this sampled hypothetical lane. They do not establish live profitability, causality across every gate, statistical significance or permission to activate the alternative. Insufficient cases or contrast remain inconclusive. There is no automatic promotion or live policy update.

Local artifacts live under `storage/penalty_shadow/frozen_20261113_v2`. Inspect its signed `manifest.json`, `status.json` and integrity-protected `checkpoint.json`. The latter retains case-level admissions, scores, outcomes and execution-horizon data. Source records remain in `storage/replay_evidence`.

To update a stopped observer once using its frozen source:

```powershell
.\.venv\Scripts\python.exe storage/penalty_shadow/frozen_20261113_v2/frozen_source/tools/penalty_shadow.py once --run-dir storage/penalty_shadow/frozen_20261113_v2
```

Do not run a second observer while the supervisor's worker holds its lock. Test report: `docs/diagnostics/penalty_shadow_20261113.xml`.

Activation: frozen on **13 November 2026 at 15:36:28 SAST**. The first startup-only run is preserved at `storage/penalty_shadow/frozen_20261113`; it stopped on archive-writer lock contention before resolving any cases. The new frozen version waits on that transient contention without changing its checkpoint. No observations from the retired run count toward the new cohort.

Validation: **83 focused tests passed**, including archive contention, checkpoint integrity, paired scoring, observation supervision and shared research reporting. This is software validation, not proof of profitability.

Operational check at 15:37 SAST: frozen observer running, committed candle source readable, stderr empty, shared dashboard API fresh and typed/voice research intent returning the same counts. Both stages contain zero resolved pairs at activation; no performance conclusion is available. Existing paper, natural-lifecycle and learned-ranker observers remained running.
