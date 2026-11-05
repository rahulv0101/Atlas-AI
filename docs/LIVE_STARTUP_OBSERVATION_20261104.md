# Guarded demo startup and observation — 4 November 2026

The operator explicitly requested "run it and see". This authorizes this run
and supersedes the earlier shutdown request. Atlas was left running.

## Startup findings and repair

- MT5 initially had global Algo Trading disabled. The configured account was
  verified to be a demo account before enabling the switch for this run.
- `.env` named `HFMarketsSA-Demo2`, while the matching account was actually
  connected to `HFMarketsSC-Demo2`. The server setting now matches that session.
- Both readiness and broker startup performed unconditional logins. During
  these reconnects Algo Trading became disabled again. A shared session helper
  now reuses a connected session only when both account and server match.
  Other or disconnected sessions still require login, and the resulting
  identity is verified. Disabled Algo Trading still blocks startup: this code
  never enables the switch automatically.
- Normal launcher subsequently reported `SUCCESS` / `backend_healthy_desktop_ready`.
  Backend PID 12772, desktop ready, UI API returned HTTP 200.

## Fresh runtime evidence

Four completed decisions were observed at 20:21:39, 20:22:47, 20:23:55 and
20:25:02 SAST. Every cycle returned HOLD / "No directional trade signal
selected." All eight raw strategy outputs were flat, with confidence zero.
The selected flat candidate's displayed confidence of 0.45 is not a buy/sell
signal; its raw seed remained zero. The effective confidence threshold was 0.44.

Timing explicitly reported "not applicable: no directional signal was
selected". Therefore timing was not the first stopping gate on these cycles.
The timing diagnostics still described missing entry conditions, but no
directional candidate reached that gate. Fresh market retrieval succeeded
(1,200 bars), and the status freshness check was not stale.

A final read-only broker check confirmed matching demo account and server,
connected terminal, Algo Trading enabled, Python API allowed, zero positions,
zero pending orders, and zero broker orders since launch. Old saved execution
results in the status are historical; they are not fills from this run.

No order was forced. Strategy, risk, approval and execution restrictions were
not loosened. This run verifies startup and scanning, not successful broker
submission or that all possible bugs have been fixed. A naturally qualifying
candidate is still needed to observe the complete entry path.

## Validation and artifacts

- Initial focused suite: 54 passed (session helper, process roles, wake launcher,
  broker adapter).
- Expanded session regression module: 10 passed, including both actual startup
  callers with Algo Trading enabled and disabled. Four tests were added after
  the initial focused suite, for 58 distinct passing tests overall.
- A broader test run was interrupted during startup troubleshooting; no full
  suite pass is claimed for this change.
- Fresh decision snapshots: `storage/live_observation_20261104.json`.
- Launcher log: `storage/run_observation_launcher.err.log`.
- Backend log: `storage/wake_spawn_logs/backend_20261104_182116.log`.
- UI server log: `storage/wake_spawn_logs/ui_server_20261104_182134.log`.

Existing staged changes were preserved; this repair was not staged or committed.
