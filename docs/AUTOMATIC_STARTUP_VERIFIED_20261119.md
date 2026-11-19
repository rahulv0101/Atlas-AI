# Automatic sign-in startup verified

The second operator-approved Windows restart produced a new boot and a current
at-logon success receipt on November 19, 2026. No Atlas launcher, worker or recovery
was started manually during this check. The sign-in task ran and ended with result
0, with zero missed runs. A later competing launch was deduplicated by the startup
lock. The receipt's legacy startup_folder_invocation field records --at-logon for
both the scheduled task and Startup shortcut.

The launcher started at 16:44:15 UTC and finished at 16:52:52 UTC (18:44:15 to
18:52:52 SAST), taking 516.56 seconds. The first readiness attempt failed; the
existing bounded second attempt recorded SUCCESS/backend_healthy_desktop_ready.
This proves automatic recovery on this boot, not a fast or first-attempt-clean start.
The exact cause of the initial readiness failure remains unestablished.

Final live checks verified backend and desktop/API health. The MT5 display-only
service has a fresh heartbeat, confirms D1,H4,H1,M15,M5 and is resting on M5.
The original collector and paper evaluator resumed without resetting experiments;
their checkpoints/journal/source integrity checks pass. The snapshot records 29
forecast sets and 51 resolved paper candidates. These counts can overlap and do
not prove independent strategy qualification or broker fills.

The current live blocker is extreme-volatility protection. No new trade, risk
limit, strategy activation or execution policy change was made during this check.
Natural broker lifecycle and profitability remain unproven. Current-boot startup
is now verified, with the slow initial attempt retained as an operational limitation.
The accompanying JSON contains the portable receipt and component evidence.
