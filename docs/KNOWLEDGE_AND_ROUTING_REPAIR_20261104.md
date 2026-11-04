# Knowledge, answer routing, and integration repair — 4 November 2026

## Completed

- Created a local rollback baseline: commit `68d86ce`, covering the repaired source,
  tests, structured knowledge, and operating contracts. No remote push was made.
- Consolidated the duplicate JSON sources into root `knowledge`. Preserved every
  existing Brain v2 scalar value and retained non-conflicting additions from root
  knowledge. There were no scalar conflicts. The former packaged risk-policy payload
  is exactly equal to the canonical payload; no risk-policy values were changed.
- Removed the duplicate `atlas_ai/knowledge` files. The package build now distributes
  the same root knowledge directory as a data namespace. Generated control queues,
  approvals, review state, and market snapshots are excluded from distribution.
- Updated macro readers, writers, and UI refresh to the canonical path. The existing
  local macro snapshot was moved byte-for-byte; freshness and interpretation logic
  were preserved.
- Fixed knowledge caching: file replacements/updates invalidate cached content, and
  returned nested objects cannot mutate the cache. Explicit alternate roots remain
  isolated instead of falling back into the main project's knowledge.
- Made NLU example loading independent of the working directory and refresh its
  cache when the dataset changes.
- Added shared Brain v2 validation for specialist informational answers. Typed and
  voice requests still enter `AskAtlasService.answer`. Specialist formatters retain
  their existing response schemas, but their drafts now pass through the shared
  intent/domain, evidence, plan, and relevance modules before being returned or
  remembered. Invalid drafts regenerate through the main answer engine, and failed
  drafts never enter conversational memory.
- Removed repeated structured-analysis branches. Explicit command responses remain
  isolated from informational validation and do not gain new execution authority.
- Kept structured voice analysis equivalent to typed analysis while shortening its
  prose. Learning answers and recommendation follow-ups have regression coverage.
- Found and repaired another migrated-machine issue: the Realtek microphone named
  in the local config does not exist here. The config now uses the default device;
  speech input can fall back from an unavailable configured device and reports a
  clear error when no usable input exists. This does not start audio capture.
- Kept machine-local wake config, control-queue state, and macro snapshots out of
  Git while preserving their local files.

## Validation

| Check | Result |
| --- | --- |
| Full suite | 1,379 passed; no errors, failures, or skips; 243.89 seconds |
| Final integration checks | 78 passed; 7.55 seconds |
| Python syntax | 343 files scanned; no errors |
| Dependency consistency | `pip check` passed |
| Core source preservation | 37 trader/risk/execution/strategy files unchanged from baseline |
| Risk policy | Canonical payload equals the previous Brain v2 payload |
| Macro snapshot | Canonical file equals the previous snapshot byte-for-byte |
| Installed wheel | Builds; single knowledge directory; no duplicate packaged knowledge |
| Installed-wheel UI | Dashboard, JavaScript, CSS, and health endpoint return HTTP 200 |
| Installed-wheel answering | Capability answer passes relevance validation |
| Desktop runtime | WinForms / Edge Chromium backend initializes successfully without a window |
| Audio hardware | Default device index 1 resolves at 16 kHz without capturing audio |

The installed-wheel smoke test ran outside the source checkout, using temporary
storage. Real MT5 initialization, login, and order submission were replaced with
functions that fail immediately if called; none was called. Broker-adapter behavior
was exercised with simulated broker responses, not real orders.

Three microphone regression cases and the final source-independent startup fixture
were added/updated after full-suite collection. They are covered by the 78-test final
integration run. The two run counts are not a count of distinct tests.

The temporary verification workspace is:

`C:\Users\rv010\AppData\Local\Temp\atlas-consolidation-359f578364ac426fbc2e16143088a767`

It contains `full-tests.xml`, `final-integration-tests.xml`, test logs, and the wheel
smoke artifacts. Machine-readable evidence is in
`docs/diagnostics/knowledge_routing_verification_20261104.json`; the knowledge migration
record is `docs/diagnostics/knowledge_consolidation_20261104.json`.

## Operational boundary

Atlas remains stopped, consistent with the operator's October 23 shutdown instruction.
No scheduled task was enabled, broker login attempted, order submitted, microphone
audio captured, or interactive desktop opened. The local `.env`, saved trading state,
and journals were preserved. No strategy, timing, sizing, risk, or execution policy
was relaxed.

The known source and integration issues listed in the previous audit are addressed
within this offline scope. Actual broker authentication/fills and an interactive
voice/desktop session still require an explicit live-start request; simulated
validation cannot establish those outcomes or prove the absence of every future bug.
