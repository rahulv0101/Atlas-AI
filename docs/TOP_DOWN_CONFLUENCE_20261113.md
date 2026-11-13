# D1 → H4 → H1 → M15 confluence, M5 entries

The operator explicitly requested this policy on 13 November 2026. It is enabled locally with `TIMEFRAME=M5` and `TOP_DOWN_CONFLUENCE_ENABLED=true`. A public-setting change receipt is retained at `storage/policy_changes/top_down_20261113.json`. API keys and the local `.env` remain outside Git.

## Explicit decision rule

1. Read D1, then H4, H1 and M15 from the broker, in that order.
2. Exclude forming and future candles. Require at least 30 completed closes and fresh, ordered, nonduplicate data for every timeframe.
3. Determine each timeframe's direction using the existing 10-close versus 30-close average bias rule. D1 establishes the direction; H4, H1 and M15 must all agree. Flat, mixed, missing, invalid or stale evidence prevents confluence.
4. Generate entries from completed **M5** candles. The existing gold liquidity-sweep detector is included on M5 in this explicit mode; the enabled-strategy allowlist still applies.
5. A directional M5 candidate must match all four higher timeframes. Existing signal selection, timing, conviction, session, loss, size, broker and execution gates still apply. Confluence is a requirement, not permission to bypass other gates.

Daily closure uses the configured broker timezone's calendar day, including DST changes. Other bar durations use their configured timeframe intervals. Staleness is bounded to two timeframe intervals after the latest closed candle; closed markets can therefore make a timeframe unavailable until fresh bars arrive. Failure to fetch one timeframe is reported rather than replaced with a shorter timeframe.

## Compatibility boundaries

The feature defaults to disabled for older configurations. Existing M1 context behavior remains unchanged when disabled. Unknown timeframe names now fail explicitly in the secondary feed rather than silently fetching M5 data. The feature refuses startup with an entry timeframe other than M5.

The existing built-in gold strategies are available on M5 only when this policy is explicitly enabled. Their formulas were not retuned. Legacy evolved and demo chromosome pools are excluded from this mode because their M1 evidence does not validate M5 operation. The adaptive EMA side-switch override is also excluded: it must not replace an already checked direction. This does not enable disabled range strategies, expand allowed setup families, change lot limits or grant real-money trading authority.

Single-frame backtests and the shared historical policy cache explicitly reject this policy. They do not have the separate historical D1/H4/H1/M15 data required to establish confluence. Legacy historical training cannot promote a replacement strategy in this mode. A dedicated multi-timeframe historical replay and fresh forward evidence are still needed to evaluate performance; the policy change itself does not establish an edge.

The original frozen paper, learner and penalty-comparison experiments remain separate and unchanged. They retain their original timeframes and rules. In particular, the M1 penalty comparison excludes current M5 publications; its evidence cannot validate the new policy. Existing natural-lifecycle observation remains observational and does not force an entry.

## Visibility and operational verification

`status.higher_timeframe` exposes the policy ID, entry timeframe, per-timeframe biases, last completed bar timestamps, recent 20-candle high/low references, availability reasons and aggregate alignment. These high/low references are observational levels, not proof of actual resting liquidity. The dashboard has a Higher Timeframe Confluence card. Timing explanations label the actual entry timeframe; legacy structured reason keys remain compatible.

This is directional confluence using price averages plus an existing candle sweep detector. It is not a newly implemented complete order-block/FVG/BOS/CHOCH Smart Money Concepts strategy.

**152 focused checks passed**, including every required timeframe's ability to veto, missing/stale/invalid data, forming-candle exclusion, broker daily DST boundaries, M5 inventory, exclusion of M1 learned pools, old M1/M15 compatibility, rejection of unsupported backtests, execution audit checks and existing research supervision.

After activation and restart, the backend published M5 status with D1/H4/H1/M15 all pointing sell. Closed M5 data and all four broker timeframes were available. The UI server and desktop startup callback were healthy. The first recorded cycle was blocked by the existing extreme-volatility protection. That protection was not relaxed. No trade was forced, and a natural entry/protection/exit lifecycle has not been demonstrated by this change.

The chart and live backend restart from the normal Atlas shortcut using the local configuration; no running Codex session is required. The default-off example configuration documents how to opt in explicitly on another installation.
