# Current application architecture

**Source review: 20 November 2026.** This is the current owner map. The
[roadmap](../../ROADMAP.md) records product phases; the
[remediation tracker](ownership-and-practice-progression-remediation.md)
records outstanding source review and acceptance. The superseded subsystem
inventory is archived as [4 November architecture](historical/system-2026-11-04.md).

The product is one Godot 4.7 desktop process with embedded CPython, a native
Verovio notation renderer, one immutable score stream and one musical
MIDI/transport timeline. MIDI files are the only product input. Generated
MusicXML and authentic Verovio artwork are internal notation assets. The
learner-visible contract is [Practice Flow](../practice-flow.md).

## Decisions and application effects

| Responsibility | Current owner and boundary |
| --- | --- |
| Moving windows, hands, tempo and mastery | [PracticeFlowLessonGenerator](../../piano_teacher/practice_flow_course.py) and the pure [teaching decisions](../../piano_teacher/teaching_decisions.py) select one immutable decision. Each new bar is introduced alone, then with up to three preceding bars. Each window has independent progress; the whole-piece examination is separate. |
| Selected source and persisted progress | [LearningPlan](../../piano_teacher/learning.py) installs the selected course definition/progress. [SessionCommands](../../piano_teacher/application/session_commands.py) applies a validated manual decision; [AttemptSettlement](../../piano_teacher/application/attempt_settlement.py) commits judged progression and evidence. Consumers do not select another source or tempo. |
| Listen → Free → Tempo preparation | [Exposure preparation](../../piano_teacher/application/exposure_preparation.py) materializes the selected source interval and prepares typed score/lifecycle effects. [PracticeFlowCourseSession](../../piano_teacher/application/flow_course_session.py) tracks the display step and messages. Free completion commits the 50% starting BPM and reset counters in the generator's decision and next exposure; the display session consumes those values. Listen and Free use the target tempo. |
| Guided input and source interval | [GuidedSession](../../piano_teacher/application/guided_session.py) owns the teaching controller, selected fragment, derived beat range, hints and recovery return. Its fragment is the same source used for visible notation and note recognition. |
| Playback lifetime and admission | [PlaybackCoordinator](../../piano_teacher/application/playback_coordinator.py) authorizes immutable source-bound transitions/count-in plans. [PlaybackSession](../../piano_teacher/application/playback_session.py) owns mode, running/automatic state, take epochs, score waits and start/pause/resume/completion effects. The engine retains its lock and applies selected source/persistence effects. |
| Musical scheduling | [VisualTransport](../../piano_teacher/visual_transport.py), [MusicalScheduler](../../piano_teacher/application/musical_scheduler.py) and the active [TempoMapCache](../../piano_teacher/application/tempo_map_cache.py) share source-time mappings and authored meter. Renderer geometry may constrain physical admission; it cannot alter grading time. |
| Assessment and evidence | [AssessmentService](../../piano_teacher/assessment_service.py) and [PracticeAssessmentPolicies](../../piano_teacher/application/practice_assessment.py) produce grading facts. One selected verdict governs progression, recorded acceptance and trouble resolution. [AttemptRuntime](../../piano_teacher/application/attempt_runtime.py), [AttemptSettlement](../../piano_teacher/application/attempt_settlement.py), [LearningCapture](../../piano_teacher/application/learning_capture.py) and [ProgressRepository](../../piano_teacher/progress_repository.py) retain the take and commit evidence/progress transactionally. |
| MIDI and Listen | [MidiIngress](../../piano_teacher/application/midi_ingress.py) preserves calibrated physical arrival timestamps and source-bound input routing. [ListenSession](../../piano_teacher/application/listen_session.py) owns asynchronous audio preparation and score/audio readiness. These services do not infer course mastery. |
| Source and future assets | [SourcePreparationSession](../../piano_teacher/application/source_preparation_session.py) preflights import, curriculum and fingering. [ScoreArtifacts](../../piano_teacher/application/score_artifacts.py) owns compilation from a frozen score selection; [TeachingContinuation](../../piano_teacher/application/teaching_continuation.py) retains exact future source/asset identities without choosing another teaching outcome. |

[PracticeEngine](../../piano_teacher/server.py) is the locked application/API
boundary. It composes these owners, captures facts and applies effects. The final
independent source review found no remaining concrete ownership blocker;
source-specific verification is recorded separately from physical acceptance.

## Desktop presentation and the immutable score

| Responsibility | Current owner and boundary |
| --- | --- |
| Scene composition | [Main](../../godot/main.gd) creates scenes/services and wires explicit signals and ports. It does not select teaching decisions or own the stream ledger. |
| Commands and accepted state | [PracticeCommandCoordinator](../../godot/practice_command_coordinator.gd) owns command sequencing/results. [ApplicationStateInbox](../../godot/application_state_inbox.gd) accepts backend snapshots; [ApplicationPollSession](../../godot/application_poll_session.gd) owns polling. Navigation, input and settings have dedicated sessions. |
| Presentation time | [PracticePresentationSession](../../godot/practice_presentation_session.gd) reconciles accepted state and score readiness. [PresentationTimeline](../../godot/presentation_timeline.gd) owns forward world projection and rate epochs, consumed by [ContinuousScoreFlow](../../godot/continuous_score_flow.gd). It cannot revise a graded deadline or move already exposed ink backwards. |
| Admission and renderer promotion | [ScoreAdmissionGateway](../../godot/score_admission_gateway.gd) coordinates source/revision/deadline-bound physical receipts. [ScoreSceneController](../../godot/score_scene_controller.gd) promotes renderers. [ScoreRunway](../../godot/score_runway.gd) prepares assets; readiness is not permission to invent a transport deadline. |
| Engraving and drawing | [ScoreEngraving](../../godot/notation/native/score_engraving.gd) owns layout/asset preparation, [ScorePainter](../../godot/notation/native/score_painter.gd) composes native drawing, and [NativeScoreView](../../godot/notation/native/view.gd) supplies the canvas/lifecycle boundary. [GlyphAssets](../../godot/notation/native/glyph_assets.gd), [GlyphHeadMasks](../../godot/notation/native/glyph_head_masks.gd) and [Glyphs](../../godot/notation/native/glyphs.gd) separate authentic artwork, derived status masks and canvas composition. |
| Stream and retained ink | [ScoreStreamController](../../godot/notation/native/score_stream_controller.gd) owns the sole source/rest queue through append, retirement and rollback. [StreamTakeBinding](../../godot/notation/native/stream_take_binding.gd) owns take identity reconciliation; [StreamRecoveryPlanner](../../godot/notation/native/stream_recovery_planner.gd) owns recovery selection. [RetainedNotationPool](../../godot/notation/native/retained_notation_pool.gd) owns compiled source/rest CanvasItems. Painters and snapshots cannot mutate the live FIFO. |
| Controls, feedback and sound | [PracticeScreen](../../godot/practice_screen.gd) presents snapshots and emits intents; [PracticeChrome](../../godot/practice_chrome.gd) owns widget construction/layout. [PracticeFeedbackSession](../../godot/practice_feedback_session.gd) consumes the acknowledged note-event channel. [CountInAudioSession](../../godot/countin_audio_session.gd), the metronome and Listen sound owners execute authorized audio cues. |

The typed command/response queue is in-process. The command/tick worker
advances backend deadlines even without UI polling; a separate asset worker
keeps cold engraving outside the tick worker and engine lock. See the
[embedded runtime contract](../inprocess-runtime.md) for startup and packaging,
and [playback coordinator contract](playback-coordinator.md) and
[ADR-0001](decisions/ADR-0001-single-authority.md) for authorization rules.

## Verification and remaining gates

Phase 5 is complete: the final independent source review found no remaining
concrete architectural blocker, and existing core/native checks pass. The
full embedded production/repertoire/strict relocated-package workflow passed
at `9654d2a3`. Python reported 335 passed/one skipped (the existing optional
system SF2/libfluidsynth check); all existing Godot failure counters were zero.
The source stayed on main and was not pushed. The latest cited remote
baseline remains [`12f50e66`, run 44736734032](https://github.com/tpepels/piano_teacher/actions/runs/44736734032).
Phase 6 remains incomplete for physical acceptance below.

Run the existing [test entrypoint](../../scripts/test.sh); it does not establish
audible output, physical MIDI latency or on-screen rendering acceptance.
Physical Kawai CA49/USB/Bluetooth, Listen/Free/Tempo, count-in, low-tempo and
changing-meter playback, continuous handoffs, sparse/sustained source notes,
reconnect, saved reopen and clean-machine acceptance remain owner gates.
Outstanding learner-visible features stay listed in
[Practice Flow](../practice-flow.md); extraction does not make them complete.
