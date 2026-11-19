# Post-reboot check

A new Windows boot was confirmed against the pre-restart marker. At the initial
check there was no current-boot sign-in receipt and no Atlas/MT5 processes. The
existing launcher was invoked manually for recovery, which is NOT automatic-start
proof. A later launch attempt was blocked by the existing startup lock during that
recovery. This supports delayed startup, not a conclusive permanent shortcut failure.
The precise reason the original Startup-folder invocation was delayed is unknown.

Manual recovery restored backend, desktop/API and MT5. The native display Service
resumed on terminal reopen and confirmed D1,H4,H1,M15,M5. The collector and evaluator
resumed through the launcher with their original checkpoints/protocols, not a new
experiment. Their checksums/source hashes verify; downtime was not backfilled as
fresh forecasts. Current health/count snapshots are in the accompanying JSON.

A second bounded user-sign-in mechanism is installed as `Atlas AI - Start at sign-in`:
interactive current user, limited privileges, no stored credentials, 30-second logon
delay, IgnoreNew overlap policy, at most two one-minute retries, ten-minute launcher
limit. It invokes the same guarded project pythonw launcher. Core worker/startup
locks remain responsible for deduplication with the existing shortcut. The installer
now reproduces both the shortcuts and this scheduled task. Twenty focused startup
checks pass. Task registration does not prove its next logon trigger works.

A second reboot was not performed automatically. A fresh timing approval is needed
before closing open applications again. No new at-logon receipt was fabricated from
manual recovery. No trading strategy, risk limit or order authority was changed.
