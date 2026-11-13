# Research integrated with Atlas's operator system

The existing acceptance supervisor coordinates the original frozen paper observer, natural broker lifecycle observer, cost reporting, publication evidence, seven-day activity review and the separate frozen learning experiment. The running trader retains its configured strategies and all risk/execution gates. A failed or inactive learner is never promoted automatically.

## One operator view

`atlas_ai/research_status.py` reads the existing evidence artifacts and produces a compact, read-only `research_progress` view. It verifies learning metadata checksums, restricts experiment paths to Atlas storage, bounds file sizes and reports unavailable/partial/invalid evidence explicitly. It does not run research, contact MT5, write learning state or load model coefficients into the trader.

The same view is available from:

- `GET /api/research-progress` for direct inspection.
- Dashboard compact/full status and runtime responses.
- The **Learning & Verification** dashboard card.
- Typed and voice Ask Atlas through Brain v2's intent → domain → evidence → plan → synthesis → relevance path.

Ask “How is the learning experiment doing?”, “How does the learning model work?” or “How is the activity review?”. Voice uses the same facts with a shorter answer. Research inquiries remain informational: they are excluded from trading-decision journaling and strategy-preference review. Follow-up memory may preserve the conversation, but cannot change the model, policies or execution authority.

## Evidence boundaries

The original paper stages and the learner's stages remain separate. So do diagnostic fills and natural fills. The view always marks profitability unproven and carries no broker authority. Metadata checksums are not full causal replay or proof of an edge.

Acceptance/activity reports older than three minutes are marked stale. The learning worker runs at ten-minute intervals, so its report becomes stale after fifteen minutes. Missing or future/unverified timestamps cannot appear current. Stale counts are displayed as last-known evidence; missing lifecycle evidence is labelled unavailable rather than an implied current result.

The initial learned model trained on 1,978 examples across 17 dates and selected no historical candidate above its fixed expected-return threshold. Historical review therefore failed. Integration does not turn that result into a qualifying strategy. The model remains frozen for independent new paper evidence; the seven-day activity deadline and original experiment are unchanged.

## Validation

Integration checks exercise the real dashboard renderer with Node, Flask status/runtime endpoints, the shared artifact reader, Brain v2, and typed/voice Ask Atlas. They cover stale/missing/corrupt evidence, separate paper counts, authority boundaries and informational-query isolation. Live API checks confirm the compact dashboard and Ask Atlas expose the same training counts and qualification result. Policy comparison across UI activation showed no strategy/risk/execution setting changes; session clock and refresh timestamps continued updating normally.

Validation completed: 83 focused integration checks and 2,007 full regression tests passed. An additional startup/integration run on 13 November passed 23 checks, including informational-query isolation. Reports: `docs/diagnostics/research_integration_20261112.xml`, `docs/diagnostics/full_integration_20261112.xml`, and `docs/diagnostics/local_startup_20261113.xml`. These diagnostics are local artifacts, not profitability evidence.
