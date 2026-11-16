# Fixed M5 calibration and entry proposal

The operator requested M5 volatility calibration, entry-filter investigation, stop/sizing checks, a matched baseline comparison, separate validation and demo observation. This study grants **no broker authority** and does not change live strategy, risk or execution settings.

## Fixed rules

The calibration window is October 1–15, 2026 UTC. The separate chronological validation window is October 15–November 14 UTC. This history was previously available and partly inspected; it is retrospective evidence, not a blind or fresh forward test. The repaired Monday D1 freshness implementation is used in both lanes. Prior frozen studies remain unchanged.

The single candidate uses the median ratio of M5 to M1 mean absolute close movement, calculated from paired, fully completed 295-minute windows. Gaps and market closures are excluded. At least 1,000 pairs across ten dates are required. Ratios outside the declared [1,5] bounds fail calibration. The ratio scales the existing 0.045% elevated and 0.07% extreme price-volatility boundaries; VIX extreme/panic vetoes remain. No trade outcomes select these thresholds.

The candidate additionally requires the last completed M5 candle to close in the proposed direction and beyond the preceding close. Stop and target distances use the existing reviewed ATR-to-broker-points adapter with its existing coefficients and floors. There is one combined candidate; this does not establish a causal contribution from each component separately. No multiplier search, replacement dataset selection based on profit, or retuning after outcomes is allowed.

Daily/H4/H1/M15 directional confluence, normal timing and conviction checks, nominal R10,000 capital, 0.5% risk, broker minimum volume, lot cap, margin, session controls, daily/weekly loss limits and protection simulation remain. Wider protection cannot increase the risk budget or invent a sub-minimum lot.

## Comparison and audit

Each lane runs independently through the shared policy replay and allocator. The baseline uses the unchanged volatility guard and distances. The candidate uses the fixed research policy in an isolated process. Decisions are saved and checksummed before exit labels. Both periods require at least 30 candidate trades over two dates, positive mean net R, profit factor at least 1.1 (or all wins), and maximum drawdown at most 6R. A meaningful baseline comparison additionally requires 30 baseline trades and candidate mean R no worse than baseline in both periods. Zero trades cannot qualify.

The rejection audit records actual sequential rejection reasons. When a signal had already been selected, a separate stop-first simulation labels its hypothetical path at minimum lot. These paths overlap, ignore the veto being investigated and are not executable portfolio returns. A positive path is not proof of a worthwhile missed opportunity. Preselection rejections receive no invented signal/outcome. Minimum-lot affordability in this audit uses the nominal initial balance, not the actual account balance.

Native inputs, protocol, source, calibrated parameters, predictions, selection and reports are checksummed. All source used by the observer is frozen. Input-only reuse is integrity checked and cannot reuse outcomes. Interrupted setup attempts are retained and are not selection evidence.

## Demo observation and integration

After the historical run completes, the existing acceptance supervisor can launch a separate read-only observer for both lanes, even if the candidate remains unqualified. This observer is diagnostic; collecting data is not promotion. It does not replace any existing frozen experiment.

Only new, timely predictions count. The collector starts at the next M5 boundary after its first observation, records processing delay, discards forecasts more than 120 seconds late, and freezes predictions before modelling outcomes from completed M5 bars. Revised closed-bar history, corrupt receipts, changed account/settings/environment and incompatible source stop collection for review. It does not recompute results when no new M5 bar closes. The observation deadline is fixed at 21 days from protocol freeze, subject to the existing supervisor's earlier deadline. There are two sequential 30-case stages per lane, each requiring multiple dates and the same review criteria.

These are simulated closed-bar paths using a next-opening quote proxy, lagged spread, frozen current-reference fees/currency/margin and assumed adverse slippage. They do not establish executable entry prices, historical screenshots/macro/news decisions, tick-level management, actual broker protection, natural fills or a natural automated broker lifecycle. Manual trades do not count as this observer's evidence. No automatic live activation is possible even if historical and forward screens pass.

The timely records are strategy signal sets. Portfolio selection and exits are replayed as sufficient closed bars arrive. This does not demonstrate that a live execution manager selected and filled those entries in real time.

The dashboard and shared typed/voice answer show the study separately. Research thresholds are explicitly labelled as research-only, while the live guard remains unchanged. Persistent experiment history records findings rather than silently training the live trader.

## Completed historical results and operational check

The authoritative run is `storage/m5_calibration_20261116_v3`; [portable results](M5_CALIBRATION_RESULTS_20261116.json) retain its checksums and aggregate rejection audit. Two setup attempts are preserved: one was interrupted before outcome labels to strengthen observer integrity, and one rejected equivalent tuple/list settings during input reuse. The third run reuses only integrity-verified raw inputs with identical dates and formula; no outcome-driven retuning or replacement dataset was performed.

| Period | Repaired baseline | Fixed proposal |
|---|---|---|
| Development | 3 trades, 0 wins, -R52.47 | 0 trades |
| Separate validation | 10 trades, 2 wins, -R93.42 | 0 trades |

Neither lane qualified. All seven validation proposal evaluations surviving earlier checks failed risk-bounded minimum-lot sizing. The nominal budget remained R50 per trade; risk was not increased. The changed cash result versus the earlier R94.06 loss uses a newly frozen tick-value/currency/margin reference and must not be presented as a strategy improvement.

The paired calibration had 2,160 windows over ten dates, producing scale **2.1946802415**, elevated **0.0987606109%** and extreme **0.1536276169%** research limits. In the 4,707 matching validation windows, 18.08% exceeded the original 0.07% cutoff; none exceeded the proposed extreme cutoff. The same absence of proposed price-extreme events occurred in development. Thus the data do not establish the proposed guard's protective behaviour during genuine price extremes. Mechanical VIX/price-veto tests are not empirical stress validation. Historical and closed-bar demo contexts lack full external macro/VIX evidence; actual live policy is unchanged.

The baseline's sequential validation rejections included 3,797 higher-timeframe conflicts, 907 timing failures and only two late-stage volatility vetoes. In the independent overlapping path audit, 3,023/3,797 confluence-rejected paths and 707/907 timing-rejected paths were non-positive after modelled costs. Both volatility-rejected paths were non-positive. Some rejected paths were positive, but these are neither an executable portfolio nor proof that removing a filter improves selection. This audit does not justify blanket loosening.

The supervisor started the frozen, read-only demo observer after historical completion. It has a fixed deadline, no broker authority and no automatic activation. Both 30-case stages remain prospective and unproven. Its source, input/prediction receipts and staleness are inspectable in the dashboard and the shared typed/voice answer.

The first new forecast was captured 21.8 seconds after its M5 close, before modelling later-bar outcomes. The observer's checkpoint and unmodified closed-history prefix were subsequently read successfully, and the supervisor reported the existing collector rather than spawning a duplicate. This verifies collection startup, not strategy profitability.

**100 focused regression checks passed.** They cover matched-window/no-future-data calibration, VIX panic vetoes, fixed validation boundaries, ATR point units, directional confirmation, unchanged default replay results with tracing, rejection signal isolation, frozen-input reuse, prospective forecast-before-outcome publication, history revisions, supervisor non-spawning safeguards, status integrity, stale dashboard text and shared typed/voice relevance. All six native input hashes, predictions, calibrated parameters, protocol and 280 frozen source files were verified. The trading backend was not restarted for this research change.
