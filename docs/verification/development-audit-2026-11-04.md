# Development audit — 2026-11-04

This is a dated findings/evidence record, not another development plan.
[ROADMAP](../../ROADMAP.md) remains authoritative. Audit started on `main` at
`b8a2aa8f`; Godot reports 4.7.2 stable Arch Linux and tests use the repository
Python environment. No physical learner comparison was conducted.

The [architecture map](../architecture/system.md) describes owners, contracts
and the full workflow. [Mistake-response policies](../mistake-response-policies.md)
contains the evidence review, proposed adaptive specification and evaluation
protocol. Six fixed baselines are preserved. New adaptation remains proposed.

## Prioritized findings

Severity describes consequence, not whether a finding was newly introduced.
P1 affects session/data correctness or blocks a declared verification gate;
P2 affects presentation/maintainability or limits evidence. Reproduction uses
temporary test data and no physical MIDI input.

| ID / severity | File/owner | Reproduction and consequence | Fix/status |
| --- | --- | --- | --- |
| A1 / P1 | `server.py:_finish_full_passage`, `application/assessment_commit.py` | Perform at 100 BPM under slow-practice/micro-loop, settle failed full take, then commit: history stored retry 90 BPM. | Captured pending performed BPM and clear it with the pending-result lifecycle; only observation uses it. Regression covers SQL abort/rollback and cancel/navigation/mode/tempo changes. |
| A2 / P1 | `application/stage_change.py`, `server.py:_change_stage` | Send invalid tempo/hand/unknown typed command while recording: response rejects request but take had already stopped and recorder was lost. Fractional BPM was silently truncated. | Validate complete intent before `_stop`; route tests preserve recorder, source, transport and running state on rejection. |
| A2b / P1 | `application/midi_connection.py:selecting` | Send null/numeric/bool/list/object device name through `midi.device.select`: rejection happened after port close and take cancellation. | Validate name type before releasing the port or entering cancellation. Five typed-route cases preserve the exact active port/recorder/session; actual valid-name switches retain their lifecycle. |
| A3 / P1 | `library.py:ScoreLibrary` | Write valid JSON with empty/whitespace/file-valued music folder; startup raises. Saved negative/>250/bool MIDI offsets bypassed update bounds. | Reuse folder normalizer and strict 0–250 integer offset validator on load, safe first-run defaults for invalid saved values; explicit edits still reject invalid values. |
| A4 / P1 | `lesson_generators.py:_fukuda_error_sections` | Standalone Fukuda error at beat 4 after a right-hand note held 0–6: excerpt began at 4 and omitted that sounding attack/hand. | Expand entry backwards to authentic safe boundaries, including transitive sustains; exact-release control and full-original equality regression. Default hybrid already used safe cuts. |
| A5 / P2 | `godot/notation/native/view.gd`, `practice_score_stage.gd`, `score_step_timeline.gd` | READY first attack after long rest: native preview moves camera, label remains on unshifted axis and may disappear. | One cached native display-camera projection feeds current label and painting. Future label keeps its own camera. Genuine retained-head tests cover RH/LH/both, 96/300 density, play/pause and next marker. Independent review caught an initial per-frame full-score scan; an 18,058-event red/green resource regression protects the corrected cache and its invalidation. |
| A6 / P2 | `notation/symbol_pixel_proof.py`, `connector_difference_pixels.py` | Existing dependency test detects coordinator → causal helper → coordinator cycle. | Pass existing registration/translation callbacks and playhead constant explicitly. Same pixel algorithms/thresholds and negative controls, no back-import. |
| A7 / P2 | `practice.py:Curriculum` | Source search finds no production caller; obsolete parallel curriculum awards two-pass progression unlike current LearningPlan. | Delete unused class and its obsolete progression test. Authoritative grading/Recorder remain; no compatibility alias. |
| A8 / P1 | Extended/notation test fixtures and drivers | Initial extended gate: 18 failed/286 passed; old HTTP callbacks, removed fields/PNG interfaces, unversioned persistence and stale geometry constants. Notation driver also selected a deleted test module. | Migrate exercised fixtures to typed command state, actual native readiness/retained compilation, versioned progress and current geometry contracts. Replace deleted visible-playback selectors with native motion/corruption checks. Remaining gate results below are explicit. |
| A9 / P1, collection resolved | Full pytest legacy modules | Initial whole-suite collection had 27 errors referencing removed facades/APIs/tools. | Migrate useful obligations to direct canonical owners; final collection has 4,716 tests and zero errors. Retire tests of already-deleted grading-session/learning-UI/cursor-log tools; current assessment/callback, screen and real-head motion/corruption checks cover their product contracts. Running all remaining assertions is still a distinct gate. |
| A10 / P2, open | Current policy evidence/interface | Rolling evidence contains aggregate wrong/missed counts; static `interrupt_rolling` cannot dynamically defer; priority note status omits independent residuals. | Implement the proposed evidence and shared continue/repair contract only as an agreed complete phase. Current six policies are fixed baselines, not learned adaptation. |
| A11 / P1 verification blocker, open | `tests/test_fingering_real_placement.py` / native fingering geometry | Broad attempt fails `chopin-turn`: several real source attacks report no local finger-label position clear of musical ink. | Preserve clearance criteria and failure. Determine whether geometry/density or genuinely unavailable space causes each report; do not hide the labels or relax the oracle to claim acceptance. |
| A12 / P2, open | `tests/test_native_fingering.py::test_insufficient_staff_space_is_reported_without_losing_source_assignments` | Independent framebuffer run: one label offset norm 15.3683 px exceeds 2.5 × 6.12 px staff-gap bound (15.30 px). | Reconcile physical placement/rounding and local attachment policy with retained source evidence; do not silently widen the bound. Eight other non-HTTP fingering tests pass in the same run. |

## Verification scope

Focused regression evidence is recorded with the changes. The first fast run
had 554 passes and one failure from an ignored retired-renderer bytecode folder.
That folder was preserved at
`/tmp/piano-handoff-retired-rendering-cache-20261104`; no audit was weakened.
The clean fast rerun passed 555 tests before new regressions were added.

The native bridge smoke registered `PianoNative` and retrieved the library
through embedded Python. Full source-recovery engraving checks passed 52 tests;
composed generators/repertoire/sparse Coda checks passed 161 tests; independent
Coda contract checks passed 225 tests. Fukuda's bounded audit checked 33 files,
38,477 notes and 234 stages with zero failures. The Coda live-note audit checked
16 fixtures/112 stages with zero rejected stages. Counts overlap other gates
and must not be summed into a unique test total.

### Broader verification failures and subsequent repairs

The first complete extended group passed 302 tests after fixture repair.
Its next group initially had 5 failures/146 passes/4 fixture errors: stale
score lifecycle callbacks, missing overview fields, moved source helpers and a
removed tie-paint method. The recorded
[extended attempt](../evidence/development-audit-2026-11-04/extended-attempt.log)
retains those failures. Subsequent focused checks repair the moved owners and
preserve actual native tie positives plus the old-geometry corruption control.

The broad notation attempt was deliberately interrupted after known failures:
**4 failed, 59 passed, 12 errors in 260.94 seconds**, exit 2. The
[attempt log](../evidence/development-audit-2026-11-04/notation-attempt.log)
retains every observed failure; it is not a completed suite. Three failures
came from requesting unregistered hands in the real-piece fingering traversal;
that test now traverses registered hands and passes all three pieces. The
remaining Chopin clearance failure is A11. Twelve errors shared a removed
import in the native-fingering fixture. Its current non-HTTP rerun has
**8 passed, 1 failed, 3 deselected**; the failure is A12. The three older HTTP
popup scenarios remain an unmigrated runtime-test obligation and were not run.

The [baseline collection blocker inventory](../evidence/development-audit-2026-11-04/collection-blockers.json)
records the intermediate 23-error state for provenance; the final collection is
clean. Source imports were moved to their real owners, not added as aliases.
Three deleted-tool test modules were retired: `test_grading_session_capture`,
`test_learning_ui` and `test_phase0_cursor_trace`. No deleted diagnostic,
network service, alternative renderer or compatibility module was recreated.

### Final bounded command ledger

The machine-readable [receipt and source/log hashes](../evidence/development-audit-2026-11-04/verification.json)
bind the implementation commits and local environment. Logs record both failed
attempts and later checks; counts from different commands overlap.

| Command / selection | Result |
| --- | --- |
| `PYTHON=.venv/bin/python bash scripts/ci-smoke.sh` | **581 passed**, exit 0; transport aliases remain zero. |
| `PYTHON=.venv/bin/python bash scripts/ci-extended.sh` | **All six groups passed:** 302, 155, 36, 1, 12, 1; final Godot parse exit 0. [Final log](../evidence/development-audit-2026-11-04/extended-final.log). |
| `bash scripts/check-godot-syntax.sh` | **Passed**, including request/preload/Practice screen fixtures; expected injected failure diagnostics remain visible. |
| `bash scripts/verify-native-bridge.sh` | **Passed** actual extension registration, embedded import and `library.catalog`, 18 pieces. |
| `pytest --collect-only -q` | **4,716 collected, zero errors**; this does not execute their assertions. |
| Focused core/READY/dependency regressions | **76 passed** after the final cache correction. Independent review also ran 86 focused tests and found no unresolved new core defect. |
| Native startup/idle/motion; UI sessions; independent measure pixels | **5 passed; 32 passed; 28 passed**, respectively. Measure proof includes five real source cases and seven rendered corruption controls. |
| Direct-owner test migrations | **99 passed**, one shared camera test deselected, full corpus excluded; current native/lesson/learner/slur group **61 passed**. |
| Pixel/dependency/native-tie focus | **76 passed** after final fixture migration. |
| Broader notation `--ci` attempt | **Failed/incomplete:** 4 failed, 59 passed, 12 errors before interruption. Later focused repairs do not certify the whole suite. |
| Current non-HTTP native fingering | **Failed:** 1 failed, 8 passed, 3 deselected. See A12 and [failure log](../evidence/development-audit-2026-11-04/native-fingering-failures.log). |

Final delivered implementation commits are `42a63f70` (session/source fixes)
and `f9b7a15` (verification maintenance); the accompanying documentation commit
does not change application behavior. The user's pre-existing moodboard
deletions and untracked Godot/runtime/provider files were not staged.

## Remaining acceptance gates

- The full 24-shard independent notation audit was not rerun. Existing retained
  evidence and known audit limits in the October verification records remain;
  no old successful captures/checkpoints were deleted or promoted to new proof.
- Real USB/Bluetooth callback latency, calibration accuracy, disconnect/reconnect
  behavior and ALSA close-thread interactions require actual hardware.
- Retained-head coordinate parity and headless scene fixtures do not establish
  independent framebuffer glyph correctness or target-GPU cadence. Software
  framebuffers cover only their stated fixtures.
- Multiple lessons, changing meter/rests, retries, tempo changes, navigation,
  completion and interrupted persistence have synthetic software coverage.
  Unattended wall-clock sessions, real system suspension and the specified
  Beethoven/long-piece playing journey remain physical acceptance cases.
- Sound-card Listen onset/latency and clean-machine packaged installation were
  not certified by embedded startup or Dummy-audio runs.
- Corrupt numeric rows and crash interruption at every historical schema
  migration were not exhaustively injected. Reviewed SQLite settlement failure
  tests do not establish recovery from every manually damaged database.
- Comparative learning effectiveness, 24-hour/seven-day retention and learner
  frustration require the proposed controlled study. MIDI replay alone cannot
  establish counterfactual learning gains.

Use the existing [physical MIDI checklist](coda-fukuda-physical-midi-checklist.md)
and record source hash, stage/hand, BPM, transport/revision, device and timestamps.
No architectural, release, physical or pedagogical completion is declared by
this audit.
