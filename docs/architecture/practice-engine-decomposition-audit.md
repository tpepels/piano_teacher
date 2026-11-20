# PracticeEngine ownership and extraction audit

**Revision audited:** `89771989f615480d6035919679c275e4632a6894` (20 November 2026), `piano_teacher/server.py` (3,572 lines, ~194 KB).  
**Scope:** Every application method and state group, existing domain collaborators, and the next safe ownership transfers. This is the **baseline audit** before the subsequent extraction checkpoints; the implementation-status section immediately below is current. The original L01 discussion in the remediation tracker records historical baseline source locations.  
**Method scan:** 158 `def` definitions including property accessors, with approximately 99 fields assigned during `PracticeEngine.__init__` and a 148-line constructor. High line count is a symptom; multiple writable owners, hidden re-entrancy and ordering dependencies are the actual risks.

## Current resolution — integrated 20 November source

The sections beginning **Concrete responsibilities** below preserve the baseline
observations and source ranges. They are historical audit evidence, not a list
of current defects. Checkpoints CA onward in the
[remediation tracker](ownership-and-practice-progression-remediation.md) record
this integration and its source-specific verification. The last remote baseline
is `12f50e66` ([core run 44736734032](https://github.com/tpepels/piano_teacher/actions/runs/44736734032));
new local commits have not been pushed.

| Baseline violation | Authoritative implementation now | Verification / remaining gate |
| --- | --- | --- |
| Whole Engine passed to PlaybackCoordinator | Frozen source/runtime facts, one authorization protocol; PlaybackSession executes the exact original admitted transition | Existing core suite passes; current production journey running |
| Several take-state writers and mixed start/resume/stop logic | PlaybackSession owns mode, running/automatic/preview flags, take epoch, count-in, score wait, suspended intent and deferred ACK. Engine captures facts and applies returned effects. | Independent final source review cleared the implemented fixes |
| Duplicate pending assessment and incomplete completion transaction | AttemptSettlement owns the exact event assessment, selected completion, rolling recovery and committed receipt. Original source revision, visual offset, performed BPM and asset identity survive storage/publication retries. AttemptRuntime holds recorder/review projections only. | Checkpoint and guided publication retries reviewed; existing core suite passes |
| Feedback/recovery policy in Engine | CompletionEffect, exposure preparation, AttemptProgression and TeachingContinuation select typed routes. Engine dispatches source effects; it does not choose another grade, window, outcome or tempo. Flow display consumes the selected decision ID once. | Existing core suite passes after the failure-order fixes |
| Private transport mutations and duplicate source epochs | VisualTransport owns musical source epochs, held-note pause floor, tempo epoch, rest-resume announcement and preview/preparation state. MidiIngress alone owns the input grading gate. PlaybackSession applies metrical effects through those owners. | No foreign private-field access remains in the three facades; current native verification due |
| Preloader supplies timing or several future-asset policies | TeachingContinuation owns exact future selection, reservation, readiness and source-stamped post-settlement publication. Its retry-poll timestamp cannot retime an announced musical deadline. MusicalScheduler remains the single deadline calculator. | Final native stage-handoff journey due |
| Fingering correction identity checks in Engine | SourcePreparationSession owns source mutation serialization, generation and original-note identity validation, then returns an exact Piece/revision install effect. Engine applies it under its existing short state lock. | Existing correction/concurrency tests pass |
| Snapshot traversal writes musical state | SnapshotReadPorts now contains reads only. The timed source installation installs the authentic source gap through VisualTransport; serialization cannot alter rest scheduling. | Existing core suite passes with the write port removed |
| Native view combines engraving, paint and queue mutations | NativeScoreView composes ScoreEngraving, ScorePainter, ScoreStreamController, StreamTakeBinding, StreamRecoveryPlanner and RetainedNotationPool. Only ScoreStreamQueue mutates FIFO membership; no executor receives the entire renderer. GlyphAssets, GlyphHeadMasks and Glyphs separate artwork, masks and drawing. | Existing Godot checks pass; full current embedded/native run due |
| Root scene owns callback/event policy | Main wires scenes and application lifetime. Inbox, presentation, polling, command, library, settings, MIDI, navigation, lesson and audio sessions own their respective replies/effects. PracticeChrome separates construction/layout from PracticeScreen interaction. | Existing Godot syntax/UI/schema checks pass |
| Replacement modules grow into another monolith | PlaybackSession is a cohesive take-lifecycle executor; pure scheduling remains in AttemptProgression, immutable DTOs in playback_facts. TeachingContinuation owns source readiness/publication, with no generator or Engine reference. ScoreStreamController coordinates one transaction queue; binding/recovery, painting and resource lifetime have distinct owners. | Independent review found no second grader, FIFO or world clock |

The final independent source review cleared the corrected storage-failure
ordering holes, snapshot write port, source-correction generation and failed
native-journal teardown. It found no remaining concrete structural or
correctness blocker and no second grader, FIFO or world clock. The existing
core suite passes after these fixes (335 passed, one skipped, all Godot checks);
the structural verifier reports `PHASE5_ARCHITECTURE_AUDIT_OK`.
**Phase 5 source review is complete; closure awaits the running integrated
production verification. Phase 6 remains incomplete:** current embedded/
repertoire/relocated-package results must be recorded, and physical
CA49 USB/Bluetooth MIDI, speakers, latency, performance and clean-machine
desktop acceptance cannot be inferred from headless checks. No tests were added.

## Historical baseline audit

## Concrete responsibilities and existing authorities

| Responsibility | Engine entry points and high-risk source range | Present authoritative collaborator | Residual defect / extraction |
| --- | --- | --- | --- |
| MIDI hardware and raw incoming messages | `_receive_message` ~46 lines; `connect`, `ports`, `_midi_lost`, calibration | `MidiIngress`, `MidiConnection`, `MidiKeyShortcuts` | Engine still builds hardware facts, calls private `visual_transport._preview_loop_pending`, dispatches MIDI shortcuts and grading; replace private read with a snapshot and pass immutable facts |
| Course progression and hand/windows | `_flow_execute`, `_begin_course_stage`, `_skip_stage`, `_place_original`, `_begin_learn` | `PracticeFlowCourseSession`, `LearningPlan`, `LearnerProgress`, Teaching reducer | UI labels / stage selection should consume one typed outcome; Engine currently still calls separate prepare methods for each resulting mode |
| Playback intent and score ACK | `start` (~95), `_commit_playback_intent` (~80), `_control_acknowledgement` (~73), `_control_transport` (~78), `_start_or_restart` (~96), `_resume_current_session` (~97) | `PlaybackCoordinator`, `SessionCommands`, `VisualTransport`, `AttemptProgression` | **Highest coupling:** PlaybackCoordinator takes the full Engine object and writes through `engine._commit_playback_intent` / `engine._stop`, while Engine independently changes `running`, `awaiting_score_revision`, `run_at`, `pause_context`, count-in and preview status. Replace engine pointer with typed source/clock facts and an explicit single authorization commit boundary; no second deadline planner |
| Attempt lifetime / reset | `_open_take` (~22), `_stop` (~58), `_reset_current_path` (~43) | `LearningCapture`, `MidiIngress`, `AttemptSettlement`, `LiveAssessmentPublisher` | `_stop` resets >30 interdependent fields; external sessions retain references across deletion. Introduce one attempt-lifetime owner for start/stop/reset and move take-scoped fields there instead of copying state into another shadow cache |
| Graded completion, recovery and persistence | `_advance_pending_feedback` (~131), `_complete_attempt` (~112), `_apply_rolling_recovery` (~91), `_finish_full_passage` (~87), `_commit_pending` (~62) | `AttemptSettlement`, `AttemptProgression`, `PracticeAssessmentPolicies`, `TeachingContinuation` | **Critical split transaction:** temporary pending result, rolling checkpoint, external progress settlement, continuation scheduling and UI announcements are spread across methods and exception handlers. Move the durable decision and status transitions into one typed attempt completion transaction; preserve exact capture/source revision and rollback, then leave Engine to invoke it once |
| Live assessment | `_publish_live_assessment` and `_live_feedback` | `PracticeAssessmentPolicies.live_projection`, `LiveAssessmentPublisher` | Grading policy and held-release tolerance already extracted. Engine still builds capture facts and triggers projection; leave orchestration until attempt owner accepts a bounded source/played snapshot |
| Source import and fingering | `load` (~44), `correct_fingering` (~36), `fingering_status` | `SourcePreparationSession`, `FingeringService`, `ScoreArtifacts` | Import is now atomic outside musical lock. Fingering correction still directly performs generation validation, revision retargeting and asset invalidation. Extract correction to its own serialized revision-aware service; Engine should install an exact returned source update |
| Ahead-of-time stage assets | `_next_stage_selection`, `next_stage_score`, `report_preload_failure`, `acknowledge_preloaded_stage` (~41) | `TeachingContinuation`, `FutureScore`, `ScoreArtifacts` | Stage selection/identity and preloader status are rechecked in four places. One preparation session should validate exact stage/revision identity, publish failure and ack, never supply a musical deadline |
| Learning history, durable reports | `_learning_context`, `learning_history_status`, `learning_statistics`, `delete_*_history` | `LearningEvidenceSession`, `ProgressRepository`, `LearningCapture` | Query ownership already extracted; deletion still coordinates many old session fields, so use the central attempt-lifetime owner when resetting learner |
| Snapshot and projection | `_state_snapshot` (~82), `_capture_session_snapshot` (~74), `_phase` | `SessionSnapshotBuilder`, `ScoreStatePublisher`, `PlaybackCoordinator` | Snapshot code still reads ~49 Engine fields directly. Emit one frozen runtime fact group from existing owners, not another snapshot writer or a second phase reducer |
| App facade and settings | preferences, library listing, diagnostics, public geometry/fingering APIs | `ScoreLibrary`, `LibraryHealth`, `MidiConnection` and dedicated services | These API boundary methods can remain small forwards; don't decompose merely to reduce lines |

## State ownership violations requiring removal

1. **Whole-engine callback from PlaybackCoordinator:** its `request`, `reserve`, `present`, `fail`, `withdraw` inspect or mutate `engine.*`. It owns the intent and receipt but not the actual graded session; replace with explicit input values, one commit protocol and a rollback port. Keep the counted-in musical start a single decision.
2. **Two paths to change take-scoped state:** `_open_take`, `_stop`, `_commit_pending`, `_complete_attempt`, `_apply_rolling_recovery` and `_advance_pending_feedback` each reset or mutate parts of the same pending-result/feedback/capture/continuation state. That causes staleness after interrupted settlement or repeated Retry.
3. **Private transport writes/reads:** Engine reads `visual_transport._preview_loop_pending` and writes `visual_transport._retry_previous_pass`, `visual_transport._preparation_pending` alongside `VisualTransport` and coordinator methods. Replace private field pokes with bounded `VisualTransport` methods/facts before relocating more code.
4. **Ahead-score revision in several owners:** `_future_stage_ready`, `future_score`, `awaiting_score_revision`, `_prepared_stage_published`, `_native_preload_failure` are spread over `PracticeEngine`, `TeachingContinuation`, `ScoreAckState` and `FutureScore`; explicitly separate **asset identity/readiness** from **transport authorization**.
5. **Large, identity-blind exception handlers:** `_update`, `_advance_pending_feedback` and `_commit_pending` can fail after durable write but before state publication. Preserve idempotent decision IDs, capture transaction, single rollback and exact source revision instead of merely moving the exception text.
6. **UI text written during policy flow:** `feedback` and `next_action` are updated from multiple command, course and assessment methods. Text should be a projection of a typed result, never re-parsed as a decision. The existing `PracticeFlowCourseSession.say` is the first owner; remaining calls should consume explicit effects.
7. **Overloaded lifetime:** `plan` and `score_revision` persist across takes, `transport_id` is per take, `recorder` and pending assessment are per attempt, and playback segment is per authorization. They must not be reset together during Pause, Retry or preloader promotion.

## Dependency-safe extraction order

1. **Transport facts boundary:** establish immutable input facts for MIDI suppression and PlaybackCoordinator's source/clock validation; remove private transport reads without creating a new clock or effect resolver. Existing `VisualTransport` and `PlaybackCoordinator` retain their own state.
2. **Take state owner:** move recorder, pending result and grading snapshots into an attempt-scoped unit with explicit begin/interrupted/complete; change all Engine call sites in the same commit, and update any compatibility fixtures only where they assume retired internals.
3. **Typed playback commit:** make PlaybackCoordinator receive a source identity, deadlines and bounded `commit/rollback` callback rather than `engine`; the Engine's public controls dispatch exactly one authorization. No shadow transport or double count-in.
4. **Settlement/application unit of work:** transfer the enormous `_advance_pending_feedback` and `_complete_attempt` paths by decomposing **decision → durable commit → next source scheduling → presentation effect**; `AttemptSettlement` already owns evidence/progress atomicity. Avoid a new giant class holding `PracticeEngine` by reference.
5. **Stage/asset and fingering revision owner:** move metadata, failure and exact source generation matching to existing `TeachingContinuation`/`ScoreArtifacts`; avoid preloader-supplied musical deadlines.
6. **Finish snapshot and UI separation:** compose frozen typed snapshots at the application boundary and reduce Main's command/UI callback choreography; NativeScoreView continues as a renderer facade only. Retire incompatible docs.
7. **Acceptance:** unchanged core tests after each integrated change, then the existing full Godot/Python/Moonlight/Peace Piece/Chopin/clean relocated package audit. Physical CA49, USB/Bluetooth and audible timing are **manual gates**, not inferred from headless success.

## Completion gate

Phase 5 cannot close while an engine pointer controls timing through two modules, while two objects write the same attempt/score revision or while the three originally oversized files still hold different domain mutation policies. Phase 6 software gates are version-specific; passing GitHub Actions on another commit does not certify new source, and headless Dummy audio cannot certify speakers or a physical piano.
