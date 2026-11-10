# Local audit evidence

New raw diagnostic reports, broker snapshots, screenshots, journals and test-run artifacts are kept local because they may contain account or machine details. Source changes, regression tests and audit summaries under `docs/` are committed. Previously tracked diagnostic records remain tracked.

Run `tools/run_system_audit_tests.py` to generate fresh isolated test evidence locally. Broker lifecycle diagnostics default to preview; actual demo execution requires an explicit operator instruction and `--execute`.
