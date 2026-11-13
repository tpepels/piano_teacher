# P1 learning statistics — software integration receipt (2026-11-13)

The application exposes read-only `learning.statistics` through its existing in-process asset worker. Versioned requests filter the learner-scoped piece fingerprint, session, date range, stage, hand, policy, performed BPM and exact scope, with insertion-watermark pagination (250 default, 1,000 maximum). Bounded query and report retain missingness and truncation rather than converting omitted observations into zero. Settings provides All history/Current piece, Refresh and page navigation.

**Implementation:** `piano_teacher/learning_statistics_query.py`, `learning_statistics_metrics.py`, `learning_statistics.py`, `godot/learning_statistics_coordinator.gd`, `godot/learning_statistics_view.gd`. Ledger schema 1 and report schema 2 are distinct. A read-only SQLite connection is opened outside the musical command lock and report formatting is outside the read transaction.

**Verification:** `tests/test_learning_statistics_query.py`, `tests/test_learning_statistics_api.py`, `tests/test_learning_statistics_resources.py`, `tests/test_learning_statistics_native.py`, `tests/test_learning_statistics_ui.py`, `tests/godot/learning_statistics.gd`, `tests/godot/learning_statistics_native.gd`. Local implementation counts in ROADMAP do not certify the remote CI revision. Use current-head GitHub Actions acceptance evidence after each change.

**Unclosed gates:** physical USB/Bluetooth latency, uninterrupted real sessions, clean-machine packaging, measured learning effects. Descriptive statistics do not establish causal effectiveness. No Phase 6 or 7 gate is closed by this receipt.
