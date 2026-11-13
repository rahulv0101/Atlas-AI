# Starting Atlas without Codex

The desktop shortcut **Start Atlas** runs the repository's existing `atlas_fullstack_startup.pyw` using `.venv/Scripts/pythonw.exe`. It sets the project working directory and launches without a command window. The installed current-user **Atlas Full System** Startup shortcut invokes the same launcher when this Windows user signs in. Neither requires Codex, this conversation, or Codex credits.

The existing guarded-demo configuration coordinates MT5, the backend and desktop UI, with their existing account/readiness checks. It does not introduce new trading permissions or relax risk/entry rules. Simultaneous shortcut clicks are locked; existing core processes are detected within this project. Unknown process inspection blocks an unverified duplicate launch. The original launcher recovery behavior remains unchanged.

Successful startup also resumes the existing bounded acceptance plan, which coordinates paper evidence, natural lifecycle observation, costs, the publication archive, activity review and the frozen learning experiment. Missing or failed observation recovery is logged separately; it does not grant trading authority. The existing sign-in observation shortcut remains valid and duplicate-safe.

## Use

- Double-click **Start Atlas** on the desktop.
- After a reboot, sign into Windows; Atlas will start automatically. MT5 must be able to connect to the demo account and the computer must remain awake for observation/trading.
- To disable automatic launch, remove **Atlas Full System** from the current user's Startup folder. This does not remove the desktop shortcut or uninstall Atlas.
- Reinstall shortcuts with `.\.venv\Scripts\python.exe tools/install_atlas_startup.py` from the project folder. Administrator privileges are not needed.

The launcher writes `storage/atlas_fullstack_startup.log` and `storage/atlas_fullstack_startup_result.json`. Component logs are under `storage/wake_spawn_logs`. Codex credits are unrelated to local startup. Optional Gemini analysis has its own API availability/quota; market data and broker connectivity still require their services.

Validation on 13 November: the desktop shortcut launched MT5, the backend, UI server and desktop host and reported `SUCCESS / backend_healthy_desktop_ready`. A repeated launch found the existing core processes; one worker for each core mode remained. All 23 focused startup/integration checks passed. Windows sign-in invocation is installed but has not been verified by rebooting the machine.
