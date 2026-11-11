# Publication evidence archive

Atlas's acceptance supervisor now preserves sampled published decisions, selected saved learning/control state, and referenced chart image bytes when available. This improves future incident investigation without changing strategy, risk, execution, or the frozen paper experiment.

The archive is a post-publication observer. Saved files are not an atomic pre-decision checkpoint; polling can miss publications, and running code is not bound to its on-disk version. Images without an original matching decision hash remain explicitly unbound to the decision. Intrabar quotes and broker protection still require separate evidence. Every capsule remains `replay_ready=false`, `broker_eligible=false`, and `orders_sent=0`.

## Storage and integrity

Local artifacts are under ignored `storage/replay_evidence`. Selected fields are whitelisted; credential fields and configured secret values are redacted. Compressed state blobs and image bytes are content addressed, and the append-only index has a hash chain. The total budget is 1 GiB, with a 256 MiB image sub-budget. Budget exhaustion retains existing evidence; it never deletes older records automatically.

Run the read-only integrity check from the repository root:

```powershell
.\.venv\Scripts\python.exe tools/verify_replay_evidence.py
```

Exit 0 means recorded integrity checks passed, 1 means missing/invalid evidence, and 2 requests retry while a writer is active. Integrity is not authenticity, complete historical replay, or proof of profitability. Archive failures are reported separately and do not stop the existing paper and natural lifecycle observers. Operator sleep and the original acceptance deadline remain respected.

## Evidence still outstanding

At implementation, the original prospective experiment had 2/30 first-stage cases and 0/30 validation cases. No natural automated lifecycle or representative natural-fill cost sample had qualified. The guarded historical comparisons produced no qualifying replacement candidate. These outcomes require new observations; the archive does not create a trading edge or grant broker eligibility.

Validation: 69 archive and related observation/supervision checks passed before activation. After restarting only the acceptance supervisor, it captured a third live publication with observed chart pixels while both original collectors remained running. Live captured records also passed the offline integrity verifier. The local focused-run report is `docs/diagnostics/evidence_archive_final_20261111.xml`.
