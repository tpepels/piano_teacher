# Learning measurement verification — 2026-11-04

This is an evidence receipt, not an active plan. [ROADMAP](../../ROADMAP.md)
owns priorities. The [approved contract](../learning-measurement.md) defines P0;
the [architecture map](../architecture/system.md) defines ownership.

## Scope and provenance

Work is on `main`, based on merge `549f4bb3` (including remote documentation
through `9d58c98` and earlier local verified fixes). The user explicitly selected
accepted-take mastery and approved the full P0 contract/defaults. The
[74-variable ledger](../evidence/learning-measurement-2026-11-04/variable-audit.json)
preserves the pre-P0 audit and adds a separate implementation delta to every row.
P0 capture and privacy controls are implemented. This does not certify the full
architecture, P1 analytical reports, physical performance or teaching efficacy.

One ledger replaces `practice_evidence`; migration imports its bounded rows once
with unknown historical timing/clean/passed/rules. `LearningCapture` supplies
stable IDs and sealed context/results to the existing SQLite transaction.
The grader retains its own actual assignment and independent timing/hold facts.
All six fixed policies remain registered. No learned selector was added.

## Confirmed findings and corrections

Severity **Important** means data/credit/timeline correctness; these were fixed
before delivery. Tests below exercise the real engine/SQLite except explicitly
identified storage or UI fixtures.

| Finding / file | Reproduction | Correction / regression |
| --- | --- | --- |
| Inert recovery settings, `application/mistake_responses.py` | Set slowdown .75 and guidance after four failures; registered default formerly stayed .9/two. | Read validated startup values; fresh-process recovery-settings contracts. |
| Partial reset, `server.py`, repository/stores | Reject generator construction, either delete, or replacement save. | Preflight replacement and one shared savepoint; failed reset preserves active take and reopened progress. |
| Guided credit before evidence, `server.py:_save_guided_preparation` | Reject guided detail insert after preparation callback. | Preparation and capture settle together; restore prepared flag and retry same exposure. Remedial completion records evidence without preparation/mastery credit. |
| SQL in physical callback, `server.py:_receive_message` | Send a note after passage/rest deadline with SQLite tracing. | Queue timestamp/correction at due handoff; existing worker advances and drains. Callback mutation regression. |
| Reset/deletion with active evidence, `server.py` | Reject terminal update or history deletion with a real open attempt. | Capture RAM/savepoint rollback; publish transport changes after successful maintenance. Deletion does not append data being deleted. |
| Unsafe checkpoint/non-full write failures, `server.py:_update` | Reject checkpoint or preview/Perform/section/partial detail insert. | Pause with explicit error, retain sealed evidence/recorder and retry after Resume. |
| Perform feedback outside settlement, `server.py` | Reject saved trouble after Perform assessment insert. | Trouble feedback and assessment share the savepoint; no partial durable result. |
| Mid-take calibration mutation, `server.py` | Change 100 ms correction to zero during a take. | Seal old exposure before applying validated setting; retain old applied correction and intent/applied events. |
| Failed full settlement loses credit on Retry, `server.py` | Reject assessment insert, remove trigger, press Retry. | Save the same attempt/credit exactly once before another musical repetition. |
| Recovery doubles near-limit prefix, `learning_ledger.py` | Recover 9 MB and exactly-at-16-MiB checkpoint fixtures. | Store prefix once; close interrupted sessions before retention enforcement; preserve coverage and unknown suffix. |
| Unclosed verification after observed focused work, `learning_ledger.py` | Crash after a proximal exposure is recorded but before original-target verification. | Censor the episode separately from its proximal outcome, using stable identities. |
| Preference-event export leaks, `learning_ledger.py` | Export music folder/device/recent-piece changes with detailed observations. | Redact those values as well as named path fields; preserve source hashes and derived residual microseconds. |
| Mapped Perform review missing, `assessment_service.py`, `server.py` | Complete Perform under two tempo segments. | Build review from same graded result and map extras through the authoritative tempo inverse. |
| Review counted as practice / missing phase checkpoints, `server.py`, `learning_capture.py` | Leave Perform review open for 100 seconds; inspect phase totals at an authored boundary before shutdown. | Separate feedback/Listen/preview from active time and persist phase prefixes with musical/guided checkpoints. Fault rollback restores phase buffers. |
| Per-note status order outlives detail retention, `learning_ledger.py` | Prune a completed session, then inspect exported assessment summary/statuses. | Remove the ordered status sequence; retain coarse status counts, note count and explicit clean/passed. Advisory history uses retained assessments only. |
| Aborted/interrupted verification loses its episode, `learning_capture.py` | Begin original-target verification, then Stop or interrupt it with another rolling decision. | Persist/replace/finish verification only for a completed assessed exposure; interrupted work retains the episode for censoring or later verification. |
| Reset duplicate event fails after commit, `server.py` | Reject `manual_action` after Reset's dedicated event has committed. | Reset uses its single atomic `lesson_reset` event; no fallible duplicate acknowledgment is appended. |
| Deleted learner inherits guidance, `server.py` | Learn → enable hints → delete piece/all learner history. | Clear guided route and hints before success; next exposure has no inherited assistance. |
| Unlinked manual events survive piece deletion, `server.py`, `learning_ledger.py` | Stop/change tempo, delete piece history, then export. | Index each manual event by its captured source; deletion also removes older nested source references without mutating hashed payloads. Unrelated sources remain. |

A valid manual policy change now seals the old exposure, as calibration does;
Play starts the next. This is a deliberate manual-override behavior change for
immutable policy provenance. Invalid changes preserve the current take. Mastery
continues to use three accepted full-target takes, with clean separately stored.

## Software verification

Final command results and source hashes are captured in
[software-results.json](../evidence/learning-measurement-2026-11-04/software-results.json).
Logs distinguish intermediate failures from final commands. Counts overlap;
they must not be added as independent tests.

| Gate | Evidence / scope |
| --- | --- |
| `PYTHON=.venv/bin/python bash scripts/ci-smoke.sh` | **704 passed**; includes observations, ledger, capture, Settings, accepted-mastery, reset and recovery contracts. |
| Focused measurement/storage/privacy/grading/atomicity | **136 passed**. MIDI-source replay covers six policy IDs; callback fixtures cover aborted/partial/guided/remedial/Perform/preview routes. Mastery fixtures explicitly commit pending results; separate progression tests exercise exact renderer acknowledgment and runway gating. |
| `scripts/verify-hybrid-workflow.sh --all` | **163 focused + 17 corpus passed**, plus three Godot contracts. |
| `scripts/check-godot-syntax.sh` | Passed; expected deliberately injected error diagnostics are included. |
| `scripts/verify-native-bridge.sh` | `PIANO_NATIVE_CLASS_OK`, `PIANO_NATIVE_LIBRARY_OK pieces=18`. |
| `./run.sh --phase0-smoke` under Xvfb | Isolated synthetic MIDI/config, automatic rebuild verification, real READY native model; deliberately terminated after readiness. No graceful-shutdown or physical-MIDI claim. |
| Packaging source contracts | 18 passed: artifact installer, notation diagnostic package/provenance and native smoke consumers. This is not an offline clean-machine installation. |
| Whole-suite collection | **4,839 collected**, no collection errors. Whole-suite execution is not green/certified. |

One concurrent hybrid run failed its bounded Listen-render join
(`test_combined_stage_uses_real_notation_listen_and_grading[coda-dotted-]`).
The isolated hybrid rerun passed. No audio timeout or acceptance threshold was
relaxed. Earlier missing-source-identity and removed-backend fixture failures
were migrated to the explicit current contracts. The native camera fixture still
contains removed HTTP-era Main seams (`requested_layout_revision`, `_on_layout`,
`_on_timeline_model`); that separate acceptance gate remains open.

Two independent intermediate reviews found transaction/callback/calibration
defects; the reported findings were fixed with failing-then-passing regressions.
After an earlier agent usage interruption, fresh scoped storage/lifecycle and
controls reviews found the episode/reset/deletion issues above. The fixes were
reviewed and have regressions. Both scoped reviews report no remaining confirmed
Critical/Important findings; broader architecture and physical acceptance are
not inferred from those reviews.

## Resource and retention evidence

Run `.venv/bin/python scripts/benchmark-learning-ledger.py --output REPORT.json`.
The [resource receipt](../evidence/learning-measurement-2026-11-04/ledger-resources.json)
records 200 settled exposures × 256 notes (51,200 observations), 1,000 synthetic
phase intervals (166.7 hours), 20 checkpoints and one pending exposure.
It measures settlement/export/checkpoint time, Python/SQLite versions and source
hashes. An SQLite authorizer denies historical detail reads while checkpoints
succeed. Byte accounting uses transactional SQLite triggers, not repeated scans
of historical note payloads.

Age pruning removes 200 old closed-session details and preserves the pending
exposure, summaries and explicit pruned coverage. The logical payload budget
does not bound SQLite/WAL file size. These local synthetic timings do not certify
long physical sessions, extreme scores or a different machine.

## Open acceptance and research limits

- P1 accuracy/variation/repetition/time/tempo/error-frequency reports and
  comparable fixed-policy analytical queries are not implemented. Captured
  counts, outcomes and exports are inputs, not an analytical dashboard or causal
  policy comparison.
- Broad notation/fingering clearance and stale native-camera acceptance remain
  open. A prior interrupted broad run had 711 passes, 13 failures and three
  errors; several stale fixtures were corrected subsequently. It is not a
  current whole-suite result. No UI artwork was changed.
- USB/Bluetooth, measured key-to-light/audio latency, reconnect, real uninterrupted
  sessions and GPU acceptance require the user's hardware/checklist.
- No standalone bundle was available and the configured bundled Python/Godot/Node
  inputs were absent. Clean-machine offline install and corrupt-state release
  acceptance remain open; developer launch is a different gate.
- Phase duration and guidance transitions are worker/transition samples, with
  bounded prefixes checkpointed at musical/guided boundaries.
  Crash suffixes, unavailable calibration measurements and pruned note detail
  remain explicit missingness. No complete pre-install lifetime history exists.
- No learners, consented trial, frustration measure, matched randomized policy
  comparison, delayed retest, efficacy result or calibrated skill model exists.
  Research thresholds remain hypotheses; see the canonical retry evaluation
  protocol and the reconciled historical pilot.

The active plan remains only [ROADMAP](../../ROADMAP.md).
