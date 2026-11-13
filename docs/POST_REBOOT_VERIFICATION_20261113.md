# Real Windows reboot verification

Following explicit approval that work was saved, Windows was restarted on 13 November. The Startup-folder shortcut invoked the local Atlas launcher after sign-in. Its receipt records a new boot identity, `startup_folder_invocation=true`, exit code zero and a fresh `SUCCESS / backend_healthy_desktop_ready` result. The sequence completed at **09:47 SAST**. `tools/verify_atlas_startup.py` returned `post_reboot_startup_verified` with `verified=true`.

This proves the observed sign-in startup sequence, without Codex launching the components manually after reboot. It does not establish profitability or a natural trade lifecycle.

## Interrupted paper publication

The reboot interrupted a multi-file publication by the frozen paper observer. Its CSV contained one additional 66-byte candle row, while the artifact checksum still identified the earlier CSV. Signals retained their existing verified checksum. The supervisor correctly refused to bless the changed file, but that failure initially prevented independent collectors from restarting too.

`tools/recover_paper_prefix.py` located the **byte-exact earlier CSV prefix matching the existing SHA-256**. It copied the complete interrupted artifacts into the paper run's `recovery` directory, restored only that previously verified prefix and left the artifact checksums, existing ten outcomes and all frozen rules unchanged. There was no invented history, re-signing of changed data or case-count reset. The next normal collector read can obtain subsequently closed bars again.

The supervisor now performs this bounded recovery automatically for an exact verified prefix with unchanged signals. Changed historical bytes, changed signals or a missing verifiable prefix remain blocked for review. A blocked paper artifact is isolated to its own stream, so the natural lifecycle and learning observers can continue independently. The restart budget is retained. The natural observer was explicitly resumed once during repair after the earlier storage fault had exhausted that budget.

## Validation

59 focused tests passed, including exact-prefix recovery, retained outcomes/backups, refusal of unrelated corruption, stream isolation, startup receipts and operator integration (`docs/diagnostics/post_reboot_20261113.xml`). The existing paper, natural lifecycle and frozen learning streams resume their original evidence; no broker order was forced and no trading-policy changes were made.

Real trading evidence remains incomplete. The original paper experiment had ten first-stage outcomes at this check, no validation stage and no verified natural lifecycle. Startup success must remain separate from those results.
