# SMC first-retest revision v3

The operator requested resolving the remaining M5 entry bottleneck. This separately versioned hypothesis, `smc_retest_v3`, keeps v2's D1/H4 direction and H1/M15 pullback context and changes only the retest stage of the shared M5 detector. It remains read-only and paper-only.

## Explicit retest changes

Earlier models expired the entire setup when an intervening candle touched the FVG. This also removed an untouched order-block opportunity. They additionally required the first touch and the rejection signal to occur on the same candle. Those were restrictive strategy rules, not proof that every such rejection was an implementation error.

V3 tracks the first visit to the FVG and order block independently. An unconfirmed or invalidated FVG does not by itself invalidate an untouched order block. Rejection may confirm on the touch candle or within the next **two completed M5 candles**. The existing directional body/range threshold and close beyond the zone midpoint still apply; confirmation need not retouch the zone on the same candle.

The boundaries remain strict:

- A candle wick through the sweep/order-block setup extreme invalidates the entire setup, including before entry.
- Closing through a zone's far boundary invalidates that zone.
- A zone's confirmation window expires after two subsequent closed bars.
- Leaving the zone in the favorable direction and then returning is a second visit, which is rejected.
- A prior valid confirmation consumes the setup; later bars or another zone cannot reissue it.
- A deterministic ID derived from model, side and sweep timestamp prevents the paper observer or historical replay from accepting the same sweep on different confirmation candles.
- The existing sweep age, confirmed pivots, displacement, FVG/order-block formation, quote proximity, protective distances and minimum 2R before costs remain unchanged. Broker minimum volume, sizing, margin, session, frequency and loss constraints remain unchanged.

The optional retest adapter is passed only by v3. V1 and v2 default to their original retest behavior. Static model selection allows only explicitly implemented research IDs; no arbitrary runtime module or conversational instruction can create a strategy.

## Versioned evidence

The run is `storage/smc_validation/retest_v3_20261113`, frozen at **21:38:52 SAST on 13 November 2026**. Its source, method, model ID, safe settings and input hashes are retained in its signed manifest. It reuses the verified 180-day D1/H4/H1/M15/M5 input files. This is another reused-data diagnostic, not a new blind historical validation period. No retest parameters are adjusted during or after the replay.

The v2 worker was retired with zero completed paper cases and no pending simulated position. Its original manifest, source, history and checkpoint remain intact, with a separate retirement receipt. V3 starts a new prospective checkpoint after its own freeze and retains the existing 10 December acceptance deadline. The installed supervisor resumes the frozen v3 worker without a Codex session.

The live observer and dashboard explicitly identify `smc_retest_v3`; the executable trading strategy inventory and its confluence gate are separate. The model is not registered as a broker strategy and cannot bypass ExecutionGate or promote itself.

## Verification

**112 focused tests passed**, including independent zone visits, later-bar confirmation, expiration, second-visit rejection, invalidation by wick and close, prior-confirmation consumption, unchanged original long/short protection, stable setup identity, original model regressions, explicit research-only selection, timeframe handling, supervision and typed/voice knowledge. Synthetic scenarios demonstrate behavior, not profitability.

The full historical replay uses unchanged review criteria, costs and nominal risk checks. Current quote outcomes in the prospective worker remain simulated; no actual fill, protected broker position or natural broker lifecycle is established by this change.

## Completed result

The reused six-month replay again produced **zero complete signals and zero trades** in all three periods. No candidate reached broker-minimum protection, sizing or margin checks; those checks do not explain this run's inactivity. Historical review failed for insufficient evidence. Win rate, average return and profit factor are undefined.

The context stages and early M5 counts were unchanged from v2: 8,588 higher-timeframe direction rejections, 3,551 setup-location rejections, five absent pullback contexts, 4,418 missing sweeps, 572 missing confirmed structures and 1,027 missing displacement/structure shifts. The remaining **17 reported M5-retest windows** did not complete the revised first-visit confirmation rules. These are overlapping windows, not 17 independent opportunities. Gap/session/boundary exclusions remain separately counted in `history.json`.

This distinguishes two conclusions: the restrictive retest semantics were explicitly revised and regression-tested; the combined strategy still has no demonstrated historical trading edge and has not qualified for broker activation. No displacement, sweep, target, risk or review thresholds were weakened after this result. Further strategy research must not represent this unchanged zero-trade outcome as success.

Operationally, the live status and supervised paper worker both identified v3, the UI served the new asset version, and the spoken explanation correctly described independent first visits with bounded confirmation and no broker authority. Forward paper cases remained 0/30 + 0/30 at completion. Earlier experiments, manifests and results remain preserved.
