# Local startup repair and system checks — 4 November 2026

## Outcome

The local environment and launcher paths are repaired. Atlas remains stopped;
no startup task was enabled, broker login attempted, or order submitted.

The previous environment and a source snapshot were preserved under:

`C:\Users\rv010\AppData\Local\Temp\atlas-repair-afa42432b8ce47cd83a716a32da40bb9`

The old environment is `venv-before`. Verification copies and test artifacts are
`source-before` and `source-after`. Tests ran in those copies without the original
`.env` or trading journals. Test copies contain generated test state and should
not be used as production state backups.

## Repairs

- Rebuilt `.venv` with the installed Python 3.12.2. Installed declared dependencies,
  pytest, and the edge speech provider. The environment no longer references the
  previous Windows account or its missing Python 3.11 interpreter.
- Cleared machine-specific Python/model paths in `atlas_wake_config.json`, allowing
  the existing loader to resolve this project's `.venv` and `models` directory.
  The active `guarded_demo` launch profile is unchanged.
- Replaced obsolete account paths in the VBS/CMD wrappers, startup-task utilities,
  legacy reboot utility, and night-watch script with paths derived from the script
  location. These utilities were edited, not executed.
- Made the example config portable. It explicitly selects `paper_compare`, matching
  its previous paper-comparison command intent, and lets the loader generate the
  commands. The former example mixed paper commands with the implicit guarded-demo
  default, which the loader rejects.
- Fixed parsing of quoted Windows command strings, preserving executable paths
  and argument values containing spaces.
- Fixed clap-setting precedence: JSON `false` now overrides an environment `true`.
  An explicit disabled voice-trigger setting cannot be lost through truthy fallback.
- Aligned `requirements.txt` and project dependency metadata, including the directly
  used OpenAI, pyttsx3, edge-tts, psutil, and requests packages. Added
  `requirements.lock.txt` recording the tested Windows Python 3.12 environment.
- Added package-data declarations for dashboard HTML/CSS/JS, packaged knowledge JSON,
  and prompt text. A wheel built before this change omitted these assets; the rebuilt
  wheel includes them.
- Fixed the Brain v2 relevance failure path. A draft rejected twice is replaced
  with an insufficient-evidence response. The retry reports its actual plan and
  narrowed evidence. Ask Atlas also enforces the rejection flag, excluding rejected
  drafts from conversational memory, AI journal updates, and generated control items.
- Updated the replay harness's mock execution gate to supply the snapshot interface
  required by trader observability. Existing trade-behavior baseline fixtures were
  preserved.
- Corrected `.gitignore` so monitoring Python/PowerShell source under
  `storage/monitoring` can be versioned while runtime state and logs remain ignored.
  The test suite depends on that monitoring source.

## Verification

| Check | Result |
| --- | --- |
| Full suite in repaired environment | 1,362 passed, no failures/errors/skips, 250.33 seconds |
| Final startup/configuration/voice-command tests | 37 passed, 16.40 seconds |
| Relevance, replay, portability, monitoring focused checks | 20 passed before the final three clap-precedence cases were added |
| Python syntax scan | 345 files, no syntax errors |
| Modified PowerShell syntax | Both scripts parsed successfully |
| Dependency integrity | `pip check`: no broken requirements |
| Core source preservation | All 37 compared trader/risk/execution/strategy files unchanged |
| Local startup paths | Python, Pythonw, MT5 executable, and Vosk model resolve locally |
| Offline speech model | Successfully loaded from the current project directory |
| Installed runtime imports | All declared runtime modules imported successfully |
| Package build | Wheel built successfully; required asset entries verified |

The full run collected tests before the final three clap-setting parameter cases
were added. Those cases and the final config implementation are covered by the
37-test follow-up run. These counts describe separate invocations, not 1,399
distinct tests.

The original full baseline run reported nine failures: eight were an audit-copy
omission of `storage/monitoring/atlas_monitor.py`, and passed once that unchanged
source was included. The ninth was the replay mock's missing `snapshot()` method,
which was repaired. The baseline otherwise had 1,347 passes. This is not evidence
of nine production defects.

JUnit artifacts are `source-after/full-tests.xml` and
`source-after/final-startup-tests.xml` under the repair directory. The tested wheel
is under `wheel-fixed`. Machine-readable verification is also recorded in
`docs/diagnostics/local_repair_20261104.json`.

## Reproducing checks

Use the rebuilt interpreter:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q tests
```

For future environment recreation, `requirements.lock.txt` contains the exact tested
package versions, including pytest. It targets this Windows/Python 3.12 setup;
`requirements.txt` remains the declared runtime dependency list.

The full suite writes some generated artifacts relative to its source tree, so use
an isolated copy when production knowledge/state must remain untouched.

## Scope and remaining limits

No core strategy, timing, risk, or execution-policy changes were made. The `.env`,
saved trading state, model downloads, and historical journals were preserved.

Live broker connectivity, order submission, microphone capture, and an interactive
desktop launch were not exercised. The October 23 instruction to keep Atlas stopped
was preserved. A green suite does not establish real-market performance or prove
the absence of every bug.

The split knowledge locations and overlapping direct-answer routes identified in
`PROJECT_AUDIT_20261104.md` remain architectural follow-up work. This repair does not
silently consolidate potentially different risk-policy explanations. Git still has
no commits; no commit was created as part of this repair.
