# Backend-only operation

The operator selected backend-only operation on November 14, 2026. The local preference is stored in `storage/operator_interface.json` with `desktop_ui_enabled: false`.

The existing desktop and Windows sign-in launcher reads this preference. In backend-only mode it retains command validation, MT5 readiness and backend readiness checks, resumes the existing acceptance observer, and skips launching the desktop, browser wrapper and audio watchdog. This preference does not change strategy, risk or broker execution policy. An already-running local API server may remain available for monitoring.

The manual startup check completed with `SUCCESS / backend_only_ready`, no desktop UI process and a fresh M5 worker status. No new Windows reboot was performed. Seventeen focused startup regression checks passed.

Opening the desktop later must be an explicit operator action. Re-enable automatic desktop startup only when the operator requests it by changing the saved interface preference. The preference is local runtime state and is not committed to Git.
