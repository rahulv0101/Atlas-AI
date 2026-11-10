# Session-cutoff broker status repair ? 10 November 2026

MT5 was connected to the configured demo account with XAUUSD selected and no positions/pending orders. At the Asia session cutoff, the trader's early-return status omitted `health.broker`. Health synthesis interpreted missing fields as disconnected, so the dashboard incorrectly showed MT5/HFM bridge not confirmed connected. This was a reporting defect, not evidence of an actual terminal outage.

The cutoff path now publishes fresh terminal connection, configured-demo identity and symbol-visibility evidence, plus current risk/account and Gemini configuration evidence. The normal path shares the same broker status reader. A real terminal disconnect, wrong account or unavailable read still reports a failed connection; no stale broker truth is copied forward.

The dashboard recognises broker-confirmed-flat cutoff state and explains that entries are paused until the next eligible session. It does not claim active setup scanning during this early-return path. Session and risk policy are unchanged. The configured next session at the reviewed cutoff was London 08:00 UTC / 10:00 SAST on 10 November; its opening does not guarantee an entry.

Validation: 159 trader/UI/intraday regression cases and 31 focused health/dashboard checks passed. New regressions include real disconnection, account mismatch, symbol visibility, preserved risk/AI evidence, and cutoff-specific user wording.

The reload uses the normal launcher after checking an idle matching demo account. No broker test order is part of this repair. Raw deployment, runtime and browser evidence stays local under `docs/diagnostics/`.


## Live-window follow-up

Direct inspection of the Atlas desktop found three more incomplete cutoff displays: the daily goal remained Checking, the Gemini note fell back to unavailable, and Setup search displayed fallback candidates even though entry selection was paused. The cutoff path now uses the same daily-objective calculation as the normal path, explains that market analysis is paused, and labels the setup card as paused/not evaluated. The research idle label is rendered as watching new bars. This changes reporting only.

The follow-up passed 140 regression cases and 32 focused UI/health checks. Overview/Diagnostics navigation and scrolling were checked on the actual app. The daily goal displayed -R6 / R1,000 and MT5 connection evidence was visible after reload.

Cold-start observation also exposed unnecessary diagnostic fan-out and optional learning requests delaying the core refresh. Core status polling now completes independently of events/learning. Operator panels load only after the first successful refresh on the visible Diagnostics tab, issuing requests sequentially. Tests hold optional requests pending and verify that core refresh still completes without declaring a connection failure. All 35 focused refresh/cutoff/dashboard tests passed. Duplicate fallback browser tabs were closed and the desktop interface was reloaded separately from the trading backend. Intermittent reconnection was observed before that reload; a successful startup alone is not evidence of sustained UI availability.
