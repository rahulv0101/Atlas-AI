# Session-cutoff broker status repair ? 10 November 2026

MT5 was connected to the configured demo account with XAUUSD selected and no positions/pending orders. At the Asia session cutoff, the trader's early-return status omitted `health.broker`. Health synthesis interpreted missing fields as disconnected, so the dashboard incorrectly showed MT5/HFM bridge not confirmed connected. This was a reporting defect, not evidence of an actual terminal outage.

The cutoff path now publishes fresh terminal connection, configured-demo identity and symbol-visibility evidence, plus current risk/account and Gemini configuration evidence. The normal path shares the same broker status reader. A real terminal disconnect, wrong account or unavailable read still reports a failed connection; no stale broker truth is copied forward.

The dashboard recognises broker-confirmed-flat cutoff state and explains that entries are paused until the next eligible session. It does not claim active setup scanning during this early-return path. Session and risk policy are unchanged. The configured next session at the reviewed cutoff was London 08:00 UTC / 10:00 SAST on 10 November; its opening does not guarantee an entry.

Validation: 159 trader/UI/intraday regression cases and 31 focused health/dashboard checks passed. New regressions include real disconnection, account mismatch, symbol visibility, preserved risk/AI evidence, and cutoff-specific user wording.

The reload uses the normal launcher after checking an idle matching demo account. No broker test order is part of this repair. Raw deployment, runtime and browser evidence stays local under `docs/diagnostics/`.
