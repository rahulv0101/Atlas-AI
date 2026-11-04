# Atlas project audit — 4 November 2026

Follow-up: local startup and several confirmed bugs were subsequently repaired.
See [the repair and verification report](LOCAL_REPAIR_20261104.md) for the current
environment, changes, and complete test results. Findings below describe the initial audit.

## Assessment

Atlas has substantial working functionality, but this workspace combines a migrated
Windows installation, historical runtime artifacts, overlapping answer routes, and
unfinished maintenance history. These are separate problems; treating every symptom
as a trading-confidence problem would be misleading.

No trading settings, strategies, execution policies, or runtime processes were changed
for this audit. Only this report was added to the original workspace. Tests and probes
ran in a temporary source copy without the original `.env` or runtime storage.

## What the project actually contains

- 180 Python source files under `atlas_ai`, totaling 63,048 lines at inspection.
- 140 `test_*.py` files.
- A gold/XAUUSD trading backend using MT5, rule-based strategies, ranking, filters,
  timing checks, risk controls, and guarded execution.
- A Flask operator interface and optional desktop shell.
- Brain v2 for informational answers, structured knowledge, follow-up memory,
  evidence selection, answer planning, synthesis, and relevance checking.
- Voice transcription and speech output, with the canonical voice question path
  calling the same `AskAtlasService` used by the UI.
- Historical learning, bounded adaptation, strategy evolution, AI decision journals,
  review evidence, research queues, and staged demo-promotion workflows.

The core paths are:

```text
Market data -> AtlasTrader -> strategy signals -> ranking/filter/timing checks
            -> risk sizing -> ExecutionGate -> MT5BrokerAdapter -> broker

Typed question / voice transcript -> AskAtlasService
            -> routing / direct handlers / Brain v2 -> answer -> optional speech

Explicit system command -> command router -> lifecycle operations
```

The AI decision core is advisory by design. Its decision trace explicitly denies
execution, live promotion, risk-policy mutation, and gate bypass. It is not an
independent authority allowed to rewrite the trading system.

## Confirmed findings

### 1. The existing virtual environment cannot start here

`.venv/pyvenv.cfg` references Python 3.11.9 at
`C:\Users\User\AppData\Local\Programs\Python\Python311`.
Running `.venv\Scripts\python.exe --version` fails because that interpreter is absent.
The Python launcher reports Python 3.10 and 3.12 installed under `C:\Users\rv010`.

`atlas_wake_config.json` also names the old user's virtual-environment executable
and Vosk model path. The configuration loader gives the JSON executable precedence
over its environment/default fallback. A copied environment and old absolute paths
must be repaired before the current launcher can be considered usable.

### 2. Atlas is stopped; its saved state is historical

The process inspection found no Python or MT5 processes. Port 8765 had no listener.
No Atlas scheduled tasks were returned by the scheduled-task inspection.

`docs/operator_shutdown_20261023.md` records an explicit instruction to keep Atlas
and its automatic restart launchers stopped until an operator requests restart.
This audit did not restart anything.

The saved backend heartbeat is from 23 October at 07:13:47 SAST; saved trading status
is from 07:17:41 SAST. Its last action is `hold`, with the reason
`No directional trade signal selected.` These are not current market observations.

Persisted runtime flags still contain `execute_trades=true`; the automation payload
records demo execution, a gate enabled, and no pause or sleep flag. Conversely,
the shutdown note says processes were stopped. These artifacts describe different
aspects of the system and cannot substitute for current process/freshness checks.
The CLI word `live` also does not by itself establish a real-money account: saved
execution environment is `demo`.

### 3. There is no Git history to reconstruct changes

Git is installed and `.git` exists, but branch `main` has no commits. Source files
appear as untracked. There is no committed baseline, rollback history, or reliable
source diff showing what changed when. Older documents saying Git is unavailable
are themselves out of date for this machine.

### 4. Brain v2 is modular, but the surrounding answer service has overlapping routes

`atlas_ai/ui/ask_atlas.py` contains 3,961 lines. `answer()` applies NLU routing over
its own handling classification, checks commands and several direct handlers, and
only then reaches Brain v2. The structured-analysis condition appears three times.

Direct handlers bypass the engine's full evidence/planning/relevance pipeline.
`_with_handling()` supplies a trace when absent, with empty evidence and a
`direct_handler` relevance marker. A trace's presence therefore does not prove that
the canonical relevance check ran.

The legacy `brain.py` and `operator_core` implementations also remain present;
the routing contract classifies legacy operator modules as compatibility-only.
Their existence alone does not mean the main UI or voice path uses a separate brain.

### 5. The relevance guard does not enforce rejection after its retry

In `atlas_ai/brain/answer_engine.py`, an unsuccessful check triggers one narrowed
retry. If the second check also fails, the engine still returns the text with
`relevance_passed=False`. `AskAtlasService._answer_via_brain()` does not enforce
that flag before returning the answer.

An isolated probe forced both checks to reject. Observed result:
`checks=2`, `relevance_passed=False`, `returned_text=True`.
This proves an enforcement gap, not that every ordinary answer is irrelevant.
The retry also retains the initial selected-plan/evidence variables for reporting,
so the final trace can fail to describe the fallback attempt accurately.

### 6. Knowledge has two locations with different contents

Root `knowledge` contains 25 JSON files; `atlas_ai/knowledge` contains 12. Ten names
are shared. Six shared files differ:

- `experiment_history.json`
- `glossary.json`
- `lessons_learned.json`
- `market_knowledge.json`
- `operator_teaching_examples.json`
- `risk_policy.json`

`BrainKnowledge` prefers `atlas_ai/knowledge` and falls back to root `knowledge`
only when a file is absent. Other code, including self-improvement and NLU example
loading, uses root `knowledge`. A root-file edit can therefore be invisible to
Brain v2. Its in-memory cache also does not refresh loaded files automatically.
Different explanatory risk-policy files are not proof that executable risk settings
have changed, but they are a source-of-truth problem.

### 7. Historical non-execution has concrete evidence

The retained October 14 investigation, `docs/automated_trade_blockers_20261014.md`,
documents 746 final decision records in its specified deployment window: 661 flat
holds and 85 directional candidates. All 85 stopped before request creation:
67 at timing discipline and 18 at higher-timeframe alignment.

The present timing implementation still excludes plain `breakout` from its fresh
entry/retest location allowlist. When visual-watch evidence is marked as used for
decisions, visual disagreement can also veto timing. The diagnostic notes a possible
mismatch between a strategy's breakout/retest confirmation and the generic location
label consumed by timing. Removing these checks would change entry policy; this
audit did not do so.

This historical window does not establish current behavior or lifetime trade counts.
The stored successful broker result must not be counted as fresh automated-trading
evidence; the earlier investigation identifies a retained manual plumbing test.

### 8. Passing tests require interpretation

The gate selects a test broker automatically when `PYTEST_CURRENT_TEST` is present.
Adapter validation rejects the exact name `InMemoryBrokerAdapter` for live-like
environments, while differently named test subclasses pass that particular check.
These tests verify simulated workflows; they do not establish broker connectivity
or prove that all production adapter variants are correctly classified.

The dependency lists also differ: `requirements.txt` includes `openai` and `pyttsx3`,
while the `[project]` dependencies in `pyproject.toml` omit them. Installation method
can therefore change available optional providers.

## Fresh verification

- All 180 Python source files parsed successfully with the standard-library AST parser.
- Seven offline Ask Atlas probes exercised self-knowledge, capabilities, limitations,
  follow-up `Why?`, status, readiness, and structured buy/sell analysis.
- The three permanent self-model failure questions returned the expected domains and
  relevant answers. Structured buy/sell analysis returned its required payload.
- 278 focused tests passed across 19 test modules and a corrected fixture-copy rerun.
  Coverage included routing, relevance, Brain knowledge/voice/follow-ups/observability,
  structured analysis, execution boundaries, broker hardening, critical safety checks,
  timing policy, AI core/reviews/preferences, and the UI server.
- The first invocation had 277 passes and one failure because this audit's temporary
  copy omitted `docs/ROUTING_CONTRACT.md`. After copying that unchanged file, the
  failing documentation test passed. This was an audit setup omission, not a project bug.
- The old `pytest_output.txt` result of 6 failures / 766 passes is historical. The
  previously failing cases in the selected modules now pass in this isolated setup.
- The complete suite was not run. No MT5 connection, live startup, real order,
  microphone capture, or desktop interaction was attempted.

Temporary verification workspace:
`C:\Users\rv010\AppData\Local\Temp\atlas-audit-5f86a1ba26b14c6ba3f6c11e1ba07b2f`.
It uses a separate Python 3.10 environment with system packages and the additional
test/audio dependencies. JUnit results are `audit-results.xml` and
`audit-contract-rerun.xml` there. It is not a replacement production environment.

## Repair order

1. Capture a reviewed Git baseline before implementation changes.
2. Rebuild a usable local environment and replace obsolete machine paths, while
   preserving the explicit stopped state and verifying intended mode before restart.
3. Choose the authoritative knowledge location and make readers/updates consistent.
4. Enforce the final relevance result and make fallback traces report the actual
   selected evidence and plan; cover both with regression tests.
5. Reduce duplicate routing incrementally while preserving direct-response schemas,
   command boundaries, voice brevity, and existing compatibility tests.
6. Investigate entry-policy/strategy evidence mismatches separately, with a fixed
   behavior baseline and isolated experiments. Do not lower confidence or remove
   trading guards as a generic repair for installation or answer-routing problems.

The evidence supports targeted repairs, not a wholesale rewrite. Working tests and
safe execution boundaries should be preserved while these inconsistencies are removed.
