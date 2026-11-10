# Broker-sized orders and native-test investigation

The operator asked Atlas to support small amounts and resolve the remaining
native-fault concern. Strategy rules, risk fractions, drawdown limits and the
approved demo-execution cap remain active.

## Sizing changes

When the broker supplies a valid minimum volume, it is now authoritative. Atlas's
nominal base_lot is no longer an additional minimum. Calls without broker
metadata retain their configured fallback minimum. Invalid metadata still fails
closed. Volumes are rounded down to the broker step and must fit the risk budget.

The trader's execution request previously formatted lots to four decimal places.
It now preserves their fixed-point decimal text, preventing a valid small lot
from becoming zero while passing through the guarded execution request.

Regression tests cover:
- hypothetical brokers allowing 0.001 and 0.000001 lots;
- exact preservation of those amounts through real ExecutionGate routing to a
  simulated broker;
- no increase above the configured monetary risk budget;
- preservation of the configured fallback minimum when broker metadata is absent.

The initial sizing/routing regression run passed 33 tests. The latest focused
sizing, signal, execution, policy and diagnostic run passed 150 tests. These examples are simulated
broker capabilities. They do not change the connected broker's contract specs.
The current XAUUSD demo contract still requires at least 0.01 lots in steps of
0.01. Small cash balances, lot sizes, margin and stop-loss risk are different
quantities. Atlas cannot submit a broker-invalid order or force a minimum lot
that exceeds the account's permitted risk.

## Native diagnostics

The earlier native fault records occurred during instrumented test runs using
periodic all-thread stack dumping. Their causal relationship to the timer is not
proven. The combined isolated reruns without it passed. A complete single-process
run of 1,697 cases completed without a native fault. One future-timestamp test
failed because its timestamp was created at collection and became valid during
the long run; it now constructs the timestamp when executed and passed on
rerun. Normal pytest fault handling remained enabled. Latest passing outcomes
cover 1,702 distinct cases across that run and the focused correction run.

A repeatable audit runner is now available as tools/run_system_audit_tests.py.
It records per-test progress and outcomes without timer-based native stack
walking. It uses separate storage and clears real AI keys inside its test process.
The normal broker-operation guards in tests/conftest.py remain active. Its own
smoke run passed two native-diagnostics tests. Original fault output is retained
in docs/diagnostics/native_fault_instrumented_20261109.log.

No diagnostic trade was submitted. Deployment and final test results are recorded
under docs/diagnostics/small_volume_* and full_system_final_suite_20261109.*.

## Guarded demo cap consistency

The sizing stage could propose a lot above the auto-approval policy's existing
0.01 maximum. Such a request could not auto-approve. Sizing now caps the proposed
volume at that same maximum before creating the request, and reports proposed,
effective and maximum volume in guarded_demo_size_cap. The constant is shared
with the approval check. Invalid scaled volumes and a broker minimum above the
cap fail closed. The cap, confidence floor, timing checks and all other approval
criteria are unchanged. A large-account regression proves that a 0.1-lot proposal
becomes a 0.01-lot request through the real gate and simulated broker.

## Native fault evidence

Windows Application Error records locate the three diagnostic crashes in
python312.dll (c0000005). PE exports and x64 unwind data map one fault directly
to PyCode_Addr2Line; the other repeated offset is in an internal function near
_Py_DumpTraceback. This narrows the failing path to interpreter traceback/line
handling, but does not prove why the referenced memory was invalid. A synthetic
Python-only allocation/GC control completed both with and without frequent
periodic dumps; that small workload did not reproduce the fault. No interpreter
or dependency binary was replaced and native fault reporting was not disabled.
See native_windows_events_20261109.json, native_fault_mapping_20261109.json and
native_diagnostic_control_20261109.json. The safer audit runner avoids periodic
all-thread native stack dumping and retains normal fault handling.

## Deployment verified

The backend stopped cleanly with no positions or pending orders and was relaunched
through the normal launcher. A new backend process, fresh API data and ready
desktop were verified. Launcher result: SUCCESS / backend_healthy_desktop_ready.
The risk fraction, daily/weekly limits, daily objective, Gemini advisory role and
approved performance source match the pre-reload snapshot. No diagnostic order
was submitted. Final proofs: small_volume_final_test_summary_20261109.json and
small_volume_final_runtime_20261109.json in docs/diagnostics.
