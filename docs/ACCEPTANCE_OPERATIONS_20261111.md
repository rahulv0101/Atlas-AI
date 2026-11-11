# Sign-in recovery and continuous execution-cost reporting

The current-user Startup shortcut now resumes the bounded acceptance supervisor at Windows sign-in, using this checkout's virtual environment and original saved plan. It does not start the trading backend, wake operator sleep, change strategies, place diagnostic orders or activate the paper model. Healthy collectors retain their process locks and evidence; original account/source/dependency checks, deadlines and restart budgets remain active.

The existing cost report now runs each supervisor cycle. Raw dispatch evidence is recorded by the existing broker adapter; the refreshed report separates diagnostic fills from ordinary fills and reports unknown/unfilled dispatches and malformed rows. Its calibration and strategy-proof flags remain false pending review. No risk or cost assumption changes automatically.

Validation: 54 focused tests passed across sign-in launch, supervision, cost reporting, checkpoints, paper observation and runtime reliability. Tests cover duplicate prevention, expired/corrupt plans, quoted Windows paths, no trade/backend launch authority, report refresh and cost-report failure isolation. The installed shortcut target and arguments were read back, an already running supervisor was reused, and the shortcut was exercised to launch the updated supervisor while retaining both collectors.

This is not a demonstrated Windows reboot. Recovery begins at user sign-in; a running backend is still required for stopped collectors to resume. A Windows shutdown or operator sleep can interrupt observation. The frozen first and subsequent thirty-case stages, actual natural protected trade lifecycle and representative execution-cost evidence remain pending new observations.
