# Application architecture

[Practice flow](practice-flow.md) defines learner-visible behaviour.
[Production transition ownership ledger](#production-practice-transition-and-ownership-ledger) maps
input, application, physical admission, acknowledgements and observables.

[ROADMAP](../ROADMAP.md) records product decisions, phases and dated verification.
This document is the current technical overview; [development](development.md)
covers operation and acceptance, and [reference](reference.md) covers fingering,
learning evidence, privacy and research limitations.
The ownership descriptions are the required contracts. The
[2026-11-20 source audit](#remaining-work--source-audit-2026-11-20)
retains the original six findings as historical evidence. The corresponding
correction commits and software verification are recorded below; physical
MIDI, audio and visual acceptance remain separate.

## A0 runtime and ownership baseline — source inspection (2026-11-22)

**Evidence revision:** 4a80beed2ab6d973eb7afb8477e5391f1522fd61.
**Status:** source inventory and critical paths inspected; **A0 not yet
accepted** because the source-to-runtime reachability trace, all remaining
individual module behavior, and same-HEAD core/native execution are open.
The following complete *file-path inventory* is from GitHub's recursive
repository tree, not proof that every listed file is loaded at runtime.
Every disposition is a **migration hypothesis** until its callers, data
writers and actual behavior have been verified. No production behavior
was changed in this audit.

### Runtime architecture actually entered

- `godot/main.tscn` loads `main.gd`; `InProcessBus` loads the
  native `PianoNative` GDExtension. The native C++ bridge initializes
  embedded CPython and creates `piano_teacher.inprocess.EngineCommands`.
  Its command worker serializes the request queue and monotonic Python
  `tick`; a separate asset worker handles expensive score operations.
  Native real MIDI callbacks enter the Python MIDI connection/ingress path,
  not a Godot grading engine.
- `EngineCommands.request` exposes state, source, library, MIDI device,
  preferences, history, score, playback reserve/present/withdraw/failure,
  stage-ready/failure, lesson controls, Listen audio and fingering correction.
  `PracticeEngine` delegates to composition-built services, acquiring
  `r.lock` for authoritative state and command mutations. A separate
  source-mutation lock prevents source replacement races while expensive
  MIDI import/fingering preparation runs outside `r.lock`.
- Raw Godot gestures/shortcut intents reach `PracticeCommandCoordinator`
  → `practice.command` → `PracticeControls`. The accepted command
  returns an outcome **and** authoritative versioned state; Godot only
  publishes effects after checking both. Polling uses
  `ApplicationStateInbox` and `StateContract`; native control projections
  must not independently decide lesson transitions.
- Actual MIDI flows through `MidiConnection` callbacks and
  `MidiApplicationInput`/`MidiIngress` to the active recorder/guided
  controller; `PracticeTimeline` assesses progress on worker ticks.
  `AttemptSettlement` and learning repositories record decisions,
  `TeachingContinuation` coordinates preloaded next stages, and
  `PlaybackCoordinator` owns playback intent/receipt authorization.
- `ScoreAssetSession` requests initial native layout and semantic score
  separately; `FutureScore`/`ScoreRunway` prepare the next stage as
  a bundle and acknowledge it independently. `ScoreAdmissionGateway`
  gathers physical clearance, asks Python to reserve the only musical
  deadline, arms the native immutable stream and reports attestation.
  `ScoreStreamQueue` owns physical online/offline strip retention.
  `PracticePresentationSession`, visual clock, metronome and practice
  frame coordinator paint accepted motion and trigger local cues.
- Persistence edges are `ScoreLibrary` JSON settings, preprocessing
  and fingering caches, `ProgressRepository` / learner history /
  `LearningLedger` SQLite, and source-specific error evidence.
  Migration code still has a legitimate purpose for existing data.

### Known concurrent and timing boundaries

| Boundary | Observed mechanism | Why A1–A5 must preserve it |
| --- | --- | --- |
| C++ → embedded Python | Native command worker and independent asset worker; GIL around embedded requests/ticks | A long engraving command cannot starve the musical tick |
| Application state | Single Python RLock in composition; locked commands and snapshots | Command eligibility, transport and settlement see one state |
| Source preparation | Source mutation lock and separate fingering ThreadPoolExecutor | Expensive import/model inference cannot hold the musical lock |
| Future scores | FutureScore bounded background worker, source/revision-keyed cache and retries | Async results from a former piece cannot become active |
| Native physical admission | Godot frame clock supplies *physical* travel/clearance; Python scheduler chooses final absolute downbeat | No duplicate musical deadline, immutable source movement or speculative grading |
| Native retained notation | Renderer generation, texture prewarming, queue/tail retention | Protect rendered ink across transition and resize, avoid frame stalls |
| Godot state delivery | Versioned state inbox, command reply contract, lost-ACK status reconciliation | Invalid/stale/canceled operations cannot partially apply UI or audio |

### A0 measured composition coupling (source baseline 4a80bee)

The 63 explicit `r.name = Class(...)` constructions in
`application/composition.py` include **21 services with at least ten**
distinct `r.*` injected dependencies and **14 with at least fifteen**.
These count direct constructor references, not a complete runtime call
graph or implicit callback dependencies. The largest are:

| Constructed service | Distinct composition dependencies |
| --- | ---: |
| `PracticeTimeline` | 33 |
| `SessionReadModels` | 25 |
| `TransportActions` | 24 |
| `SourceWorkflows` | 20 |
| `LessonExecution` | 20 |
| `MidiApplicationInput` | 20 |
| `TimedPlayback` | 19 |
| `RecoveryWorkflows` | 19 |
| `PracticeControls` | 19 |
| `TeachingDecisions` | 16 |

`godot/main.gd` references **42 unique preloaded resources**
and has **44 `.new(` call sites**; neither number equals the total
independent runtime coordinators. The embedded `inprocess.py` protocol
has distinct reads, commands, score-readiness operations and physical
reserve/present/reconcile operations. Its public names are not by
themselves a source of excess business authority.

The coupling problem is concrete: action-oriented services depend on
most mutable session roots. Simply adding more injected wrappers
would worsen it. A1 must replace the execution chain with one
serialized event transaction and narrow domain inputs, without
creating a 63-field `PracticeSession` god object. A2–A5 must remove
old injected owners after their full behavior and callers migrate.
Treat these counts as diagnostics, never arbitrary pass/fail targets.

**Real-time worker constraint:** The native C++ bridge sends
the production `score.bundle` and the retained headless diagnostic
`score.native_layout`, `score.semantic` reads, plus
`learning.statistics`, to its separate asset worker; other commands
and the musical tick use the session worker. Each embedded Python call
obtains the GIL; application and artifact locks separately protect
state. Heavy layout/statistics work must not run on the musical-tick
worker or hold the session lock during fingering inference.

### Source-backed legacy and complexity findings

| Candidate | Evidence | Proposed fate | Verification before deletion |
| --- | --- | --- | --- |
| Recursive-update preservation | `PracticeTimeline.update` loops through nested requests and deliberately repeats publications to imitate the previous recursive update flow | **Remove/replace** in A1 with ordered events and exactly one publication | Check MIDI feedback/event ordering and automatic rest/retry transitions |
| Repeated score preparation state machines | Initial `ScoreAssetSession` layout→semantic requests vs bundled future `FutureScore` and `ScoreRunway`, each with generations, retries and success ACKs | **Merge** in A4 as immutable ScoreBundle lifecycle | Normal load, stage handoff, source change, resizing, retained tails, stale worker |
| Distributed playback lifecycle | `PlaybackSession` stores running/mode/count-in; `PlaybackCoordinator` stores intent/receipt/state/deadline; `VisualTransport` stores pause/epoch/visual rest; `SessionPhase` derives phase | **Merge mutable authority**, retain pure projection and physical evidence in A3 | Pause/Resume/Listen/Free/Tempo/failure/lost ACK/odd-meter count-in |
| Long continuation chain | `PracticeTimeline` → settlement/effects/continuation → exposure execution → transport and score preparation; each has overlapping references | **Merge orchestration** in A1–A2; retain pure graded policy and persistence | Rolling and full take, remediation, fixed rest, source switch, interruption |
| Multiple read-side passes | SessionSnapshotBuilder → project_session_state → ScoreStatePublisher/control_projection; separately constructed locked command snapshot | **Merge** to one pure committed-state projection in A5 | Button availability matches same command authorization during admitting/failure |
| Alternative teaching courses | Both practice-flow and coda-fukuda-midi remain selectable in ExerciseStrategies/ScoreLibrary; source-progression is warm-up route | **Retain unless owner retires**; place all supported course policies in A2 | Existing saved alternate course, selectable settings and migrations |
| Old lesson tuning defaults | lesson_settings.json includes clean_runs_to_master=3 and focus_measures=2; practice_flow reducer requires 2 clean target passes and 4-bar moving windows | **Investigate**, remove duplicate authority but retain other-course configuration | Verify call sites and policy-dependent use; do not change Practice Flow |
| Headless projection and research helpers | headless_score_projection is an explicit fixture contract; active Coda curriculum imports modules under research/ | **Not automatically dead** despite names; evaluate test and production reachability | Check every importer including dynamic generator registrations |
| Third-party Godot MCP addon | under godot/addons; explicit release packaging removes it | **Keep development-only** or separately remove by owner choice | Verify no runtime autoload and no packed dependency |
| State contract generated checker | generated Godot state_contract.gd and Python state_contract.py | **Keep** as one cross-language schema, not two independent policies | Schema/checker version and error response parity |

### Current test baseline and non-executable gates

- GitHub Actions `Tests` currently uses **manual workflow_dispatch**
  with core/full options; there is no push-triggered current-HEAD run.
  The latest full success reported in Actions is **run 45017492022**
  at **1c1b98e** (2026-11-22), preceding the present source revisions.
  Earlier failure witnesses: 45016371433 at ed9e11b (Moonlight
  pause-in-count-in resume), and 45015311868 at d32cb13.
  **None verifies 4a80bee or later A0 documentation edits.**
- The local baseline commands are
  `bash scripts/test.sh --coverage` and
  `bash scripts/verify-embedded-production-local.sh`.
  Full verifier requires **Python 3.14**, **Godot 4.7.2**, a working native
  GDExtension, Verovio/mido/rtmidi, and (for the full package) Node.js.
  This connected GitHub source environment provides neither an installed
  runtime nor a new workflow-dispatch operation; no new CI execution
  or result is claimed.
- The embedded suite covers real-scene Play/Pause/Resume, fake physical
  MIDI success/failure/repeats, lost reserve/present ACK, Moonlight and
  all 16 versioned MIDI repertoire files; the optional exact Pathétique
  case requires `PIANO_PATHETIQUE_II_MIDI`. Physical CA49 timestamps,
  actual speaker/click/voice, visual readability and an independent
  clean machine remain owner acceptance, separate from A0 source audit.

### Risk and migration ordering

| Risk | Consequence | Owning phase and required check |
| --- | --- | --- |
| Command/order collapse | Stop or Pause lost behind admitted future request | A1: real command/worker fake MIDI, stale response and queued Stop |
| Lesson state projection drift | Wrong bar/hand/tempo or lost recovery progress | A2: exact saved reopening, Coda/Fukuda and alternate-course cases |
| Cross-language deadline authority | Count-in incorrect, grading starts before ink, lost ACK leaves live source | A3: same-epoch physical receipt and failure/reconciliation journeys |
| Preparation unification | Blank score, frozen UI, stale source published or texture stall | A4: bundle source binding, real Verovio and prewarm/retained-ink tests |
| Native UI policy resurfacing | Captions contradict backend intent or unseen stage starts | A5: versioned command/state contract and full scene input/navigation |
| Incomplete retirement | Duplicate service writer remains and defects recur | A6: imports/scene/package reachability and state-writer closure |
| Stale acceptance claim | Architecture appears done with broken current HEAD | A7: exact-SHA core, native repertoire, relocated package and separate hardware handoff |

### A0 static module disposition inventory

The following inventory is **path-complete** for the Python application and
non-addon Godot GDScript files at the evidence revision. It gives the
proposed A-phase home and preliminary disposition; each A1–A6 phase must
replace provisional labels with a proved retain/merge/delete choice and
list all actual migrated callers. The complete non-application Python
module list is appended separately to avoid hiding domain utilities.
This inventory is not a dynamic import graph.

**Python application modules (79)**

| Relative path under piano_teacher/application | Intended home | Preliminary disposition |
| --- | --- | --- |
| __init__.py | A1 session and input | Package marker |
| application_worker.py | A1 session and input | Merge orchestration; migrate all callers |
| assessment_settlement.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| assessment_verdict.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| attempt_progression.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| attempt_runtime.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| attempt_settlement.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| coda_midi_curriculum.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| completion_continuations.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| composition.py | A1 session and input | Merge orchestration; migrate all callers |
| control_dispatch.py | A1 session and input | Merge orchestration; migrate all callers |
| control_projection.py | A5 state and presentation | Merge orchestration; migrate all callers |
| device_workflows.py | A1 session and input | Merge orchestration; migrate all callers |
| exposure_installer.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| exposure_preparation.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| exposure_workflows.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| flow_course_session.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| future_score.py | A4 source and preparation | Merge orchestration; migrate all callers |
| guided_fragment.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| guided_session.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| headless_score_projection.py | A5 state and presentation | Test/headless contract—verify caller |
| history_management.py | A6 persistence and settings | Retain policy/model/edge; audit writers |
| learner_progress.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| learning_actions.py | A1 session and input | Merge orchestration; migrate all callers |
| learning_capture.py | A6 persistence and settings | Retain policy/model/edge; audit writers |
| learning_evidence_session.py | A6 persistence and settings | Retain policy/model/edge; audit writers |
| lesson_cursor.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| lesson_execution.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| lesson_snapshot.py | A5 state and presentation | Retain policy/model/edge; audit writers |
| listen_session.py | A3 transport and playback | Retain policy/model/edge; audit writers |
| live_feedback_workflows.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| midi_application_input.py | A1 session and input | Merge orchestration; migrate all callers |
| midi_connection.py | A1 session and input | Retain policy/model/edge; audit writers |
| midi_ingress.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| midi_key_shortcuts.py | A1 session and input | Retain policy/model/edge; audit writers |
| mistake_responses.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| musical_scheduler.py | A3 transport and playback | Retain policy/model/edge; audit writers |
| passage_outcome_presenter.py | A5 state and presentation | Retain policy/model/edge; audit writers |
| physical_admission.py | A3 transport and playback | Retain policy/model/edge; audit writers |
| playback_coordinator.py | A3 transport and playback | Merge orchestration; migrate all callers |
| playback_facts.py | A3 transport and playback | Retain policy/model/edge; audit writers |
| playback_session.py | A3 transport and playback | Merge orchestration; migrate all callers |
| playback_transitions.py | A3 transport and playback | Retain policy/model/edge; audit writers |
| policy_registry.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| post_assessment_effects.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| practice_assessment.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| practice_controls.py | A1 session and input | Merge orchestration; migrate all callers |
| practice_flow.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| practice_timeline.py | A1 session and input | Merge orchestration; migrate all callers |
| practice_transitions.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| recovery_streak.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| recovery_workflows.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| rolling_recovery.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| score_ack.py | A4 source and preparation | Retain policy/model/edge; audit writers |
| score_artifact_registry.py | A4 source and preparation | Merge orchestration; migrate all callers |
| score_artifacts.py | A4 source and preparation | Retain policy/model/edge; audit writers |
| score_preload_workflow.py | A4 source and preparation | Merge orchestration; migrate all callers |
| score_preparation.py | A4 source and preparation | Retain policy/model/edge; audit writers |
| score_read_services.py | A4 source and preparation | Merge orchestration; migrate all callers |
| score_state_publisher.py | A5 state and presentation | Merge orchestration; migrate all callers |
| session_commands.py | A1 session and input | Merge orchestration; migrate all callers |
| session_evidence_context.py | A6 persistence and settings | Retain policy/model/edge; audit writers |
| session_lifecycle.py | A1 session and input | Retain policy/model/edge; audit writers |
| session_notices.py | A5 state and presentation | Merge orchestration; migrate all callers |
| session_phase.py | A5 state and presentation | Merge orchestration; migrate all callers |
| session_read_models.py | A5 state and presentation | Merge orchestration; migrate all callers |
| session_snapshot_builder.py | A5 state and presentation | Merge orchestration; migrate all callers |
| settings_workflows.py | A6 persistence and settings | Merge orchestration; migrate all callers |
| source_identity.py | A4 source and preparation | Retain policy/model/edge; audit writers |
| source_preparation_session.py | A4 source and preparation | Retain policy/model/edge; audit writers |
| source_workflows.py | A4 source and preparation | Merge orchestration; migrate all callers |
| stage_change.py | A2 lesson and assessment | Retain policy/model/edge; audit writers |
| teaching_continuation.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| teaching_workflows.py | A2 lesson and assessment | Merge orchestration; migrate all callers |
| tempo_map_cache.py | A3 transport and playback | Retain policy/model/edge; audit writers |
| timed_playback.py | A3 transport and playback | Merge orchestration; migrate all callers |
| transport_actions.py | A1 session and input | Merge orchestration; migrate all callers |
| transport_commands.py | A3 transport and playback | Retain policy/model/edge; audit writers |
| transport_timing.py | A3 transport and playback | Merge orchestration; migrate all callers |

**Godot GDScript files excluding developer addon (146)**

| Relative path under godot | Intended home | Preliminary disposition |
| --- | --- | --- |
| action_button.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| application_event_router.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| application_input_session.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| application_poll_session.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| application_state_inbox.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| calibration_beat_pulse.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| challenge_flow.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| command_failure_presenter.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| command_request_state.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| command_success_effects.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| command_success_policy.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| command_success_presenter.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| continuous_score_flow.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| countin_audio_session.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| countin_cue_timeline.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| countin_voice_player.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| debug_session_logger.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| demo_player.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| feedback_event_inbox.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| frame_meter.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| game_backdrop.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| game_countin.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| game_input_indicator.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| game_phase_cue.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| game_stage.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| game_streak.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| game_transport_button.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| guided_presentation_session.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| hint_keyboard.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| home_screen.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| inprocess_bus.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| inprocess_request.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| learning_statistics_coordinator.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| learning_statistics_view.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| lesson_screen.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| lesson_session.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| library_catalog_coordinator.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| library_row.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| library_screen.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| listen_sync.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| live_midi_feedback.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| living_score.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| main.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| metronome_frame_coordinator.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| midi_device_coordinator.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| mint_glow_field.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| moving_meter_grid.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| native_bridge_smoke.gd | A0/A7 harness | Retain if exercised by native verifier |
| native_score_assets.gd | A4 score preparation | Merge preparation/adoption; keep rendering |
| native_score_feedback.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| navigation_drawer.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| navigation_policy.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| navigation_session.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| notation/native/ambient_meter_geometry.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/barline_layout.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/beam_sprite_plan.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/connector_geometry.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/context_painter.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/cursor_ink_clearance.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/engraving_readiness.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/event_window.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/fingering_annotations.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/fingering_obstacles.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/fingering_placement.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/fingering_spatial_layout.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/geometry.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/ghost_note_painter.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/glyph_assets.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/glyph_head_masks.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/glyphs.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/ink_geometry.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/ink_spacing.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/notation_clip_planner.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/note_status_layer.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/render_pass.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/rest_lane_layout.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/rest_lane_planning.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/retained_annotation_overlay.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/retained_notation_pool.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/retained_note_projection.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/retained_segment.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/score_engraving.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/score_index.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/score_layout.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/score_painter.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/score_stream_controller.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| notation/native/slur_sprite_plan.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/source_pass_painter.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/source_span_index.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/source_spans.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/stream_admission_executor.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| notation/native/stream_geometry.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| notation/native/stream_lifecycle.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| notation/native/stream_recovery_planner.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| notation/native/stream_take_binding.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| notation/native/symbol_painter.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/view.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/viewport_fit.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/native/voice_layout.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/shared/spacing_policy.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/shared/timeline.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| notation/shared/view_base.gd | A5 notation renderer | Retain authentic engraving/geometry unless proven dead |
| note_status_ink.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| note_status_registry.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| pause_sheet.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| performance_review_strip.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_caption_layout.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_chrome.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_command_coordinator.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| practice_feedback_session.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_frame_coordinator.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| practice_metrics.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_objective_glyph.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_presentation_session.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| practice_score_stage.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_screen.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_state_presenter.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| practice_step_selector.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| practice_theme.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| presentation_timeline.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| production_fake_midi_journey.gd | A0/A7 harness | Retain if exercised by native verifier |
| production_session_journey.gd | A0/A7 harness | Retain if exercised by native verifier |
| production_ui_smoke.gd | A0/A7 harness | Retain if exercised by native verifier |
| review_sheet.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| score_admission_gateway.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| score_asset_queue.gd | A4 score preparation | Merge preparation/adoption; keep rendering |
| score_asset_session.gd | A4 score preparation | Merge preparation/adoption; keep rendering |
| score_effects.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| score_runway.gd | A4 score preparation | Merge preparation/adoption; keep rendering |
| score_scene_controller.gd | A4 score preparation | Merge preparation/adoption; keep rendering |
| score_step_timeline.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| score_stream_admission.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| score_stream_archive.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| score_stream_queue.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| score_stream_window_cuts.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| score_transport_reservation.gd | A3/A5 physical surface | Consolidate admission API; keep immutable queue |
| settings_interaction_session.gd | A1/A5 adapter | Merge transaction/presentation orchestration |
| settings_screen.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| source_measure_picker.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| state_contract.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| status_head_preloader.gd | A4 score preparation | Merge preparation/adoption; keep rendering |
| status_ink_warmup.gd | A4 score preparation | Merge preparation/adoption; keep rendering |
| tempo_timeline.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |
| tempo_vocabulary.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| ui_factory.gd | A5 UI or local effect | Retain UI effect; verify no domain decision |
| visual_transport_clock.gd | A3/A5 presentation | Keep local cues/painting; merge state coordination |

**Other piano_teacher Python modules (120)**

| Relative path under piano_teacher | Intended home | Preliminary disposition |
| --- | --- | --- |
| __init__.py | Cross-cutting source support | Review at actual call site |
| __main__.py | A1 application boundary | Keep embedded protocol; shrink coordinator |
| adaptive_hybrid_curriculum.py | A2 teaching/music | Retain supported policy; audit course reachability |
| assessment_clock.py | Cross-cutting source support | Review at actual call site |
| assessment_service.py | Cross-cutting source support | Review at actual call site |
| clock.py | Cross-cutting source support | Review at actual call site |
| completion_route.py | Cross-cutting source support | Review at actual call site |
| course_navigation.py | A2 teaching/music | Retain supported policy; audit course reachability |
| demo.py | Cross-cutting source support | Review at actual call site |
| diagnosis_policies.py | A2 teaching/music | Retain supported policy; audit course reachability |
| engraving/__init__.py | A4 score model/engraving | Retain authentic notation |
| engraving/engraving.py | A4 score model/engraving | Retain authentic notation |
| engraving/geometry.py | A4 score model/engraving | Retain authentic notation |
| engraving/spacing.py | A4 score model/engraving | Retain authentic notation |
| exercise_contracts.py | A2 teaching/music | Retain supported policy; audit course reachability |
| exercise_generator.py | A2 teaching/music | Retain supported policy; audit course reachability |
| exercise_pipeline.py | A2 teaching/music | Retain supported policy; audit course reachability |
| exercise_strategies.py | A2 teaching/music | Retain supported policy; audit course reachability |
| feedback.py | Cross-cutting source support | Review at actual call site |
| feedback_events.py | Cross-cutting source support | Review at actual call site |
| fingering/__init__.py | A4 fingering | Retain inference and manual correction |
| fingering/lumikey.py | A4 fingering | Retain inference and manual correction |
| fingering/projection.py | A4 fingering | Retain inference and manual correction |
| fingering/service.py | A4 fingering | Retain inference and manual correction |
| fingering/types.py | A4 fingering | Retain inference and manual correction |
| fukuda_midi.py | A2 teaching/music | Retain supported policy; audit course reachability |
| fukuda_mistake_store.py | A2/A6 learning/persistence | Retain durable model/migrations |
| grading_tolerance.py | Cross-cutting source support | Review at actual call site |
| grouped_variants.py | A2 teaching/music | Retain supported policy; audit course reachability |
| hardware_probe.py | Cross-cutting source support | Review at actual call site |
| importing/__init__.py | Cross-cutting source support | Review at actual call site |
| importing/pieces.py | Cross-cutting source support | Review at actual call site |
| inprocess.py | A1 application boundary | Keep embedded protocol; shrink coordinator |
| learner_state.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_ledger.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_ledger_common.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_ledger_export.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_ledger_retention.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_ledger_schema.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_statistics.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_statistics_facts.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_statistics_metrics.py | A2/A6 learning/persistence | Retain durable model/migrations |
| learning_statistics_query.py | A2/A6 learning/persistence | Retain durable model/migrations |
| lesson_contracts.py | A2 teaching/music | Retain supported policy; audit course reachability |
| lesson_generators.py | A2 teaching/music | Retain supported policy; audit course reachability |
| lesson_settings.py | A2 teaching/music | Retain supported policy; audit course reachability |
| lesson_source_planner.py | A2 teaching/music | Retain supported policy; audit course reachability |
| lesson_stage_semantics.py | A2 teaching/music | Retain supported policy; audit course reachability |
| lesson_timing.py | A2 teaching/music | Retain supported policy; audit course reachability |
| lesson_validation.py | A2 teaching/music | Retain supported policy; audit course reachability |
| library.py | A2/A6 learning/persistence | Retain durable model/migrations |
| library_health.py | A2/A6 learning/persistence | Retain durable model/migrations |
| live_assessment_publisher.py | Cross-cutting source support | Review at actual call site |
| live_feedback.py | Cross-cutting source support | Review at actual call site |
| live_input_view.py | Cross-cutting source support | Review at actual call site |
| measure_grid.py | A2 teaching/music | Retain supported policy; audit course reachability |
| midi_calibration.py | Cross-cutting source support | Review at actual call site |
| music.py | Cross-cutting source support | Review at actual call site |
| musical_groups.py | A2 teaching/music | Retain supported policy; audit course reachability |
| notation/__init__.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/__init__.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/beams.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/chords.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/glyphs.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/notes.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/runtime.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/slurs.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/ties.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/tuplet_recovery.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/tuplets.py | A4 score model/engraving | Retain authentic notation |
| notation/assets/vector_art.py | A4 score model/engraving | Retain authentic notation |
| notation/display_envelope.py | A4 score model/engraving | Retain authentic notation |
| notation/expressions.py | A4 score model/engraving | Retain authentic notation |
| notation/lesson.py | A4 score model/engraving | Retain authentic notation |
| notation/midi_beaming.py | A4 score model/engraving | Retain authentic notation |
| notation/model.py | A4 score model/engraving | Retain authentic notation |
| notation/musicxml.py | A4 score model/engraving | Retain authentic notation |
| notation/piano_registers.py | A4 score model/engraving | Retain authentic notation |
| notation/practice_timeline.py | A4 score model/engraving | Retain authentic notation |
| notation/rhythm_safety.py | A4 score model/engraving | Retain authentic notation |
| practice.py | A2 teaching/music | Retain supported policy; audit course reachability |
| practice_flow_course.py | A2 teaching/music | Retain supported policy; audit course reachability |
| practice_history.py | A2/A6 learning/persistence | Retain durable model/migrations |
| practice_windows.py | A2 teaching/music | Retain supported policy; audit course reachability |
| preprocessing_cache.py | A2/A6 learning/persistence | Retain durable model/migrations |
| progress_repository.py | A2/A6 learning/persistence | Retain durable model/migrations |
| recovery.py | A2 teaching/music | Retain supported policy; audit course reachability |
| recovery_projection.py | A2 teaching/music | Retain supported policy; audit course reachability |
| remediation.py | A2 teaching/music | Retain supported policy; audit course reachability |
| repeated_passages.py | A2 teaching/music | Retain supported policy; audit course reachability |
| research/__init__.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_author_catalog.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_auto_chord_levels.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_matrix.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_midi_grid.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_midi_sparse.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_notation_hierarchy.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_reference_exercises.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_reference_matrix.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_source_connectors.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_source_metadata.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| research/coda_written_rests.py | A2 source-backed algorithms | Do not assume test-only: Coda imports research modules |
| runtime_timings.py | A1 application boundary | Keep embedded protocol; shrink coordinator |
| sample_piano.py | Cross-cutting source support | Review at actual call site |
| server.py | A1 application boundary | Keep embedded protocol; shrink coordinator |
| source_attack_index.py | Cross-cutting source support | Review at actual call site |
| source_svg.py | Cross-cutting source support | Review at actual call site |
| sqlite_transaction.py | Cross-cutting source support | Review at actual call site |
| state_contract.py | Cross-cutting source support | Review at actual call site |
| state_projection.py | Cross-cutting source support | Review at actual call site |
| teaching.py | Cross-cutting source support | Review at actual call site |
| teaching_course.py | Cross-cutting source support | Review at actual call site |
| teaching_decisions.py | Cross-cutting source support | Review at actual call site |
| teaching_manual.py | Cross-cutting source support | Review at actual call site |
| tempo_difficulty.py | Cross-cutting source support | Review at actual call site |
| timed_assessment.py | Cross-cutting source support | Review at actual call site |
| transport_projection.py | Cross-cutting source support | Review at actual call site |
| visual_transport.py | Cross-cutting source support | Review at actual call site |
| warmups.py | Cross-cutting source support | Review at actual call site |

### A0 production transition and acceptance matrix (source-traced)

All paths below refer to the actual embedded runtime, not a parallel
simulator. The named tests are **existing witnesses**, but were last
verified on an older source revision; their presence is not proof they
pass on the A0 evidence revision. A1–A5 must collapse the execution
chain without changing the chosen result.

| Trigger and current path | Authoritative decision and state write | Native or durable effect | Existing witness and unresolved edge |
| --- | --- | --- | --- |
| Library selection → godot LibraryCatalog → InProcessBus library.open → EngineCommands → PracticeEngine.load → SourceWorkflows/SourcePreparationSession | Build original MIDI fingerprint and LearningPlan outside short lock; SourceIdentity/lesson cursor install it under lock | ScoreLibrary last piece, progress restore, finger model, new score revision; ScoreAssetSession fetches Verovio geometry/model | test_score_import, test_library_and_settings; confirm concurrent source switch and stale fingering worker |
| Fresh default Practice Flow stage → PracticeFlowCourseSession/PracticeFlow reducer → ExposureWorkflows/Installer | Course selects exact moving window, hand and Listen step; no whole-piece opening | New source/score projection; Listen audio waits for real source readiness | test_practice_course; Godot production_ui_smoke, source-specific first-bar visibility |
| Listen requested → PracticeControls → LearningActions → ListenSession/TimedPlayback → PlaybackCoordinator | Backend chooses selected source and original target tempo; intent/receipt controls authorization | Godot physical reserve/arm/present; audio and ungraded lighting after accepted segment | test_desktop_playback listen cases; fake MIDI and UI smoke |
| Listen ends → PracticeTimeline and PracticeFlowCourseSession.listen_finished | Lesson switches to Free without grading or progress credit | Same selected original notes, stationary target at playhead | test_practice_timeline listen_again; test_practice_course Free progression |
| Free MIDI note → native MIDI callback → MidiApplicationInput/MidiIngress → GuidedSession TeachingController | Original-source pitch/position matching: correct next, wrong waits; Free is untimed | Feedback/hint and next-target motion; no extra neighboring measures or early progress | test_state_transition_journeys wrong Free, test_practice_course; physical latency still open |
| Free completed → guided completion → FlowCourseSession/PracticeFlow free_completed → TimedPlayback/PlaybackCoordinator | One transition to Tempo at 50% target BPM | Fresh full-meter count-in and exact source-bound admission, score advances only after auth | test_practice_course, test_practice_timeline; native fake MIDI journey |
| Tempo note attack/release → MidiIngress, recorder, AssessmentService/AssessmentVerdict | Onset tolerance and optional hold grading; original note-ID evidence retained | Green/red per-note feedback and durable signed evidence | test_note_feedback, test_state_transition_journeys release setting |
| Tempo window end → PracticeTimeline → AttemptSettlement → TeachingDecisions/Continuation | One clean/failed verdict, current window tempo ladder, streak, recovery, next hand/window decision | Rolling/full passage evidence and progress persist; next announced score prepared without extra rest | test_practice_course ladder/floor, test_desktop_playback automatic repeat |
| Failed floor Tempo twice → PracticeFlow and TeachingDecisions → Coda/Fukuda generator | Return to original Free; second qualifying return chooses real source-safe simplified aid | Announced different exercise and eventually exact original window again; no aid mastery credit | test_practice_resume, test_state_transition_journeys remediation; real original-score acceptance open |
| Two target-tempo clean takes → LessonDefinition/LearningPlan → AttemptSettlement | Complete current hand/window; move to next trailing range, or whole-piece final; persist exact stage identity | Preload next authenticated stage; native outgoing ink continues | test_practice_course complete course, test_state_transition_journeys full mastery |
| Pause command, button or MIDI gesture → PracticeControls → TransportActions/TimedPlayback/PlaybackSession | Session-authorized stop of grading and musical advance; preserve current take and exposed source | Godot holds notation, stops cues, restores only after explicit Resume and fresh authorization | test_desktop_playback paused count-in; production_ui_smoke, production_fake_midi_journey |
| Resume from Pause → transport_commands.resume_timing → PlaybackCoordinator fresh intent | Same take identity, fresh complete authored count-in, new future physical source; no truncated 5/4 | ScoreAdmissionGateway protects predecessor ink, re-arms, attests and publishes deadline | test_practice_timeline 5/4, Moonlight native journey; later changes unverified |
| User Stop or screen exit while command pending → raw ui_stop/ui_suspend → PracticeControls under lock | Stop cancels source and queued actions; one-way suspend can Pause but never Resume | Native command queue prioritizes Stop; cancels unconfirmed cue/source | test_state_transition_journeys stop/suspend, test_desktop_playback terminal Stop |
| Native reserve/present reply lost or stale → ScoreAdmissionGateway → playback.status and reconciliation | PlaybackCoordinator checks current source/attempt/take/segment, rejects replay after failure, cannot shift known ink | Provisional queue either matches attested receipt or is safely withdrawn/reported failed | test_desktop_playback lost-ACK/stale source; production_fake_midi_journey drop reserve/present |
| Lost MIDI connection during a take → MidiConnection/MidiApplicationInput/DeviceWorkflows | Reject progress and suspend/fail current attempt; no missing attacks fabricated as success | UI device notice and fresh note-edge gate on reconnect | test_midi_devices; test_state_transition_journeys disconnect |
| Score compilation/preload failure → FutureScore/TeachingContinuation or ScoreAssetSession/ScoreRunway | Source/revision-keyed terminal failure, retry or explicit user recovery; no unearned stage | No partial prepared renderer or authorization; outgoing ink retained | test_score_import; test_desktop_playback bounded failure; verifier checks SCRIPT ERROR |
| Saved reopening → ProgressRepository and LearningPlan restore → PracticeFlowCourseSession | Same window/hand restored; Free warmup, then 50% tempo, not a half-completed MIDI chord | Source revision and score reloaded; no duplicate mastery or pending physical take | test_practice_resume and test_learning_history |
| Metronome/voice display → backend authorized PlaybackCoordinator snapshot → MetronomeFrameCoordinator/CountInAudioSession | Backend deadline, meter and tempo define cue source; no local music timing decision | Native beat numbers and sound once per segment | test_practice_timeline; real audible/latency acceptance pending |
| Persist settings/history/delete/fingering → EngineCommands → SettingsWorkflows/HistoryManagement/SourceWorkflows | Validate source/history scope and changes under lock; actual file/database commit is authoritative | Godot refreshes only after accepted result | test_learning_history, test_fingering, test_library_and_settings |

### A0 state-writer and dependency ownership checks

The inspected current source shows the following distinct mutable roots.
They are not necessarily independent *decisions*: the audit must preserve
legitimate ephemeral physical state and remove duplicated musical state.
The **migrate** column names the authoritative *target*; it is not a
claim that all current writers have already moved.

| Current mutable root | Concrete state / writer | Intended sole owner and migration rule |
| --- | --- | --- |
| SourceIdentity / LessonCursor | fingerprint, revision, current plan, source selection and selected beat | PracticeSession source/lesson aggregate; ScoreBundle binds exact immutable identity |
| GuidedSession / PracticeFlowCourseSession / LearningPlan | Free target, lesson stage, hand, tempo, failed/clean and aid counters | One selected LessonDomain state with a pure reducer; score projection reads, never writes |
| AttemptRuntime / AttemptSettlement | current attempt and recorder, pending take/rolling/full settlement, cancellation generations | Assessment evidence and one lesson settlement; recover atomically on failure |
| RecoveryStreak / LearnerProgress / teaching continuation | recovery counters, future selection and deferred choice | One LessonDomain decision and one explicit scheduled effect; do not create a second choice |
| PlaybackSession | mode, running, authorization, count-in, paused-context, awaiting score | One TransportDomain aggregate; a derived UI phase is not a second mutable owner |
| PlaybackCoordinator | pending PlaybackIntent, ScoreReceipt, playback enum, take/segment/deadline, failure | Same TransportDomain aggregate; reserve/present/reconcile remain authenticated |
| VisualTransport / MidiIngress | display authorization epoch/hold, transport score beat, grading resume gate/deferred notes | TransportDomain timeline plus device ingress boundary; no separate decision clock |
| TeachingContinuation / FutureScore | prepared/acknowledged future stage, schedule, failed generation, cache/worker state | ScoreBundle prep pipeline owns assets; LessonDomain owns which next stage is selected |
| ScoreAssetSession / ScoreRunway | current revision/renderer/model/layout, future renderer/ACK, outgoing tails | One source-keyed preparation/adoption contract; retained ink remains native |
| ScoreAdmissionGateway / ScoreStreamController / ScoreStreamQueue | physical offer/receipt/reconciliation and immutable committed strips | One native physical surface; preserve single existing ledger and physical truth |
| SessionReadModels / ScoreStatePublisher / state_projection | independently assembled controls, phase, motion and pending transport facts | One pure versioned presentation projection after session commit |
| ScoreLibrary / ProgressRepository / LearningLedger / cache files | persisted settings, stage progress and evidence, imported/fingered artifacts | Explicit persistence and source-cache ports; migrations confined to storage boundaries |

**Dependency rules for A1–A6:** Input adapters call PracticeSession only;
PracticeSession calls cohesive domain interfaces; pure lesson/assessment
policy has no knowledge of Godot, Python bridge or storage; ScoreBundle
build and physical geometry do not make teaching choices; transport
may consume immutable physical evidence but never a Godot business policy;
presentation reads a committed snapshot and cannot mutate the model;
persistence receives explicit transactions/effects and publishes no hidden
lesson transitions. Retain one monotonic source clock and bounded threaded
workers. This map forbids coordinator-to-coordinator backreferences and
self-mutating projection getters.

### A0 reproducible reachability method and concrete A1 contract

Commit [9ec6936](https://github.com/tpepels/piano_teacher/commit/9ec6936c421775c96098a1e9e5ad7c996a269407)
adds a conservative, **read-only** local source graph tool:

    python3 scripts/audit-a0-reachability.py --output /tmp/piano-a0-reachability.md
    python3 scripts/audit-a0-reachability.py --json --output /tmp/piano-a0-reachability.json

The script enumerates actual Python import statements and literal/dynamic
\`importlib\` calls, Godot \`res://\` preload/load paths, known
\`class_name\` usages and scene/project resources. Its regular runtime roots
are \`godot/main.tscn\` (plus declared main scene and configured resources),
embedded \`piano_teacher.inprocess\` from native CPython, the standalone
\`piano_teacher.__main__\` launcher and explicitly invoked script modules.
Test-only references are reported separately. The JSON edge graph supports
manual review of individual dependency chains.

**Caveat:** An untraced path is *never* proof of dead code. The graph
cannot certify computed resource names, reflection, loaded third-party
plugins, platform packaging, arbitrary data-driven file names or actual
execution; class names appearing in comments can conservatively produce
false-positive edges. Native C++ and asynchronous GDScript callbacks must
still be checked against the real runtime. These limitations are explicit
because a false "dead" classification could remove working support.

**Concrete current protocol and proposed A1 seam**

| Existing boundary | Current source API | A1 event or stable read |
| --- | --- | --- |
| Raw button and MIDI keyboard gesture | \`practice.command\` with \`ui_*\` or explicit action | \`UserIntent\` containing action, source revision/fingerprint, authenticated renderer readiness where needed |
| Physical MIDI callback | \`MidiApplicationInput.receive_message\` → \`MidiIngress\` | \`MidiInput\` containing note-on/off, hardware timestamp and corrected musical time; current source/take validated |
| Native tick | \`EngineCommands.tick\` → \`ApplicationWorker.advance\` → \`PracticeTimeline.update\` | \`ClockAdvanced(now)\`, processed once in serialized event queue; timer checks are pure requests, not recursive ticks |
| Source opening and corrected fingering | \`library.open\`, \`fingering.correct\` / \`SourcePreparationSession\` | \`SourcePrepared\` / \`SourceRevisionChanged\` tied to original MIDI fingerprint and generation |
| Prepared current/future ink | \`score.native_layout\`, \`score.semantic\`, \`score.next_stage\`, \`score.stage_ready\` | \`ScorePrepared\` / \`ScorePhysicallyReady\`; ultimately one ScoreBundle protocol in A4 |
| Physical reservation and attestation | \`playback.reserve\`, \`playback.present\`, \`playback.withdraw\`, \`playback.failure\`, \`playback.status\` | \`AdmissionEvidence\`, \`ReservationReceipt\`, \`ArmedPresentation\`, \`Withdrawal\`, \`PhysicalFailure\` and explicit \`Reconcile\` events |
| Whole/rolling take evidence | AssessmentService and AttemptSettlement | One typed \`TakeAssessed\` / \`SettlementCommitted\` transition, with persisted outcome identity |
| Authoritative snapshot | \`state.snapshot\`; \`practice.command\` returns \`{state,outcome}\` | One stable versioned \`SessionProjection\`; an accepted command may include both the already-committed snapshot and one typed effect outcome |

**Identity model:** Keep immutable \`SourceKey\` (fingerprint,
revision, stage_key, hand, selected bounds), \`TakeKey\` (source key,
take_id, attempt) and \`PhysicalSegmentKey\` (take key, segment_id,
queue_generation, renderer_generation). The current
\`PlaybackIntent\` and \`ScoreReceipt\` already carry nearly all these
fields. The new types must preserve their meanings across Python/Godot:
the source revision is not just a renderer serial, and an old ACK cannot
authorize a newer source or take.

**Processing/commit model:** Commands and native acknowledgements enter
the *existing* C++ worker queue and Python application lock, not another
thread or bus. The session applies **at most one canonical publication
for each committed state change**, with no synthetic nested recursion.
A no-op event need not publish a new snapshot. External physical effects
are asynchronous and cannot be treated as part of a synchronous database
transaction: \`intent\` and \`reservation\` are pending states; **grading,
audio and moving source presentation start only when the exact physical
arm/attested-present event is accepted**. Durable lesson settlement uses
one idempotent repository commit. Failure or stale ACK compensates only
unexposed future strips; already visible source remains immutable.
This preserves the current correct split of musical authorization and
physical canvas truth without the existing coordinator cascade.

**Migration dependency direction:** Native input adapter → PracticeSession
→ pure Lesson/Assessment/Transport/Score decision ports; authorized
effects → native physical adapter, audio adapter and persistence ports;
committed state → one pure presentation projection → Godot screens.
The in-process \`EngineCommands\` operation names should remain stable
at the external boundary until every native consumer has migrated.
Deleting the prior Python service is permitted only after its actual
producer/consumer ports and negative/failure behavior are accounted for.

**Confirmed live, not legacy by filename:** The native
\`PracticeScreen\` preloads \`challenge_flow.gd\` and
\`tempo_vocabulary.gd\`; \`PracticeChrome\` instantiates
\`pause_sheet.gd\`, \`review_sheet.gd\` and measure picker;
\`DemoPlayer\` instantiates \`listen_sync.gd\`;
\`NavigationSession\` preloads \`navigation_policy.gd\`.
They have live presentation/adaptation callers. Any cleanup must
first distinguish their display utilities from duplicated domain
state. The \`challenge_flow.gd\` fallback for an absent
\`clean_runs_required\` is three, whereas default Practice Flow
requires two target-tempo clean passes; confirm the backend always
provides the correct course-specific value before replacing its UI
status fallback. This is an audit warning, **not** a reproduced bug.

### A0 observed local baseline and reconciled reachability (2026-11-22)

**Owner-supplied exact invocation:** `bash scripts/test.sh --coverage` on
the prior audit source. Result: **159 passing, 4 failing Python tests in
27.04 seconds**; therefore Godot syntax/behavior stages did not execute
and the local core gate did **not** pass.

| Failure | Source cause traced | Corrective main commit | Validation state |
| --- | --- | --- | --- |
| `test_real_state_contract_includes_authoritative_motion_directive` | Non-presenting `SessionReadModels.snapshot` skipped the required `playback_timeline` field because `ScoreStatePublisher.publish` returns early without a desktop intent | [3726c45](https://github.com/tpepels/piano_teacher/commit/3726c45f00d38e20a69ed67ed45f6ef256e7f1bc) | Corrected source, local rerun still required |
| `test_command_reply_carries_backend_resolved_action_outside_state` | Same incomplete **committed** snapshot was returned in a successful command envelope | 3726c45 | Corrected source, local rerun still required |
| `test_real_state_rejects_missing_control_and_invalid_motion_contract` | Same missing required playback timeline in the loaded state snapshot | 3726c45 | Corrected source, local rerun still required |
| `test_real_midi_release_setting_changes_tempo_credit[strict-held-release]` | `SettingsWorkflows.update(grade_note_holds=True)` unconditionally called `SessionLifecycle.stop`, cancelling the *ungraded* opening Listen's asynchronous audio. The fixture then waited five seconds for an intentionally cancelled token | [6f6ea2e](https://github.com/tpepels/piano_teacher/commit/6f6ea2e7bba5eb7b073aa1b2d932e412a5408b6c) | Preserve Listen/Free; invalidate graded practice/perform; local rerun still required |

**Architectural consequences:** The state contract applies to *all* session
projections, not only physically presented sessions. A selected settings
change should invalidate the **smallest affected active domain transaction**;
canceling an unrelated async source job caused this regression. Both
observations directly inform A1's typed event routing and single committed
presentation contract. No new test doubles, alternative score engine,
compatibility projection or test deletion was added.

**Complete reconciliation of the nine source-report "unreached" candidates:**

| Reported paths | Evidence / correct classification |
| --- | --- |
| `godot/native_bridge_smoke.gd` | Native verification launcher: `scripts/verify-native-bridge.sh` passes this script to Godot with `--script` |
| `godot/production_fake_midi_journey.gd`, `production_session_journey.gd`, `production_ui_smoke.gd` | Real-scene native test harnesses: `scripts/verify-embedded-production-local.sh` executes each with Godot `--script` |
| `piano_teacher/engraving/__init__.py`, `importing/__init__.py`, `notation/__init__.py`, `notation/assets/__init__.py`, `research/__init__.py` | Python package markers, implicitly loaded when the corresponding production submodule is imported. The first version of the static graph did not model these implicit edges |
| `godot/countin_voice_player.gd` computed load | Live module constructs `res://assets/countin/%s.ogg` for `ichi, ni, san, shi`. All four Ogg recordings are checked into `godot/assets/countin`; this is **asset lookup**, not dynamic code selection |

[835613a](https://github.com/tpepels/piano_teacher/commit/835613a81ebb4a1f2462e6c5100ab4dd4dc756d0)
amends the read-only reachability auditor so it models implicit Python
package initializers and classifies shell-invoked Godot smoke scripts as
**verification-harness references**, without treating them as runtime
production roots. **No file has been proved dead** by this static report.
Run the amended audit again locally to confirm the expected categories.

**Still required:** Run the full existing Python+Godot test suite, embedded
fake MIDI/native package verifier and corrected A0 auditor on the **same
final commit**. The submitted log predates both source fixes and does not
establish a passing state. No physical CA49 acceptance is claimed.

### A1 transaction ordering implementation checkpoint (2026-11-22)

The A1 code commits above changed actual production ordering. The native
worker still drives the same monotonic source timeline and MIDI callback
lock; no second runner or duplicate domain is introduced.

1. **Advance**: `PracticeTimeline.settle_transitions()` drains eligible
   automatic handoffs with its bounded same-tick cycle guard. No
   intermediate playback/live projection occurs.
2. **Replay**: `ApplicationWorker.advance()` replays MIDI deferred across
   a source boundary, retaining the hardware/corrected timestamp and
   letting `MidiIngress` apply the current authenticated take.
3. **Publish**: `PracticeTimeline.publish_settled()` advances playback
   status, publishes Free target preparation and live assessment once.
   Prior nested-update simulation could repeat all three per tick.
4. **Read**: `SessionReadModels._committed_base` is shared by
   `control_snapshot` and full graphical `snapshot`. Both consume the
   same `PlaybackCoordinator.snapshot` result. Only the full snapshot
   adds score-related presentation and the headless fixture queue.
5. **Command**: `EngineCommands.request("practice.command")` holds
   the existing RLock across `PracticeControls.control` and
   `PracticeEngine.state`, so native MIDI callbacks cannot interleave
   a different event between action acceptance and Godot's state reply.

These edits remove **duplicate publication and projection paths**. The
individual old domain coordinators and the general native message dispatch
still need A1 architectural replacement. The source-level review did not
run the tests or prove physical MIDI acceptance.

### A1 concrete serialized write boundary — source integration 2026-11-22

`piano_teacher/application/practice_session.py` is the sole new
input/transaction coordinator; `session_events.py` declares frozen event
envelopes, and `PracticeEngine` remains an adapter for the stable
`EngineCommands` operation names. The old `PracticeControls` and
`ApplicationWorker` source files are deleted.

| Producer and arrival | Event and transaction | Real domain owner / invariant |
| --- | --- | --- |
| Accepted UI or direct take request | UserCommand / TimedStartRequested | Backend `resolve_ui_intent` + TeachingDecisions; no UI progress decisions |
| Physical MIDI and keyboard shortcuts | PhysicalMidi / MidiShortcut | MidiIngress uses raw hardware/corrected times; SettingsWorkflows writes key ranges; note grading stays source-keyed |
| Native monotonic tick | ClockAdvanced | PracticeTimeline settles eligible handoffs, replays deferred MIDI, publishes once; no second musical timer |
| Native physical score arm/receipt/reconciliation | PresentationRequired, PlaybackReserved, PlaybackPresented, PlaybackWithdrawn, PlaybackFailed | TransportActions delegates to exact PlaybackCoordinator receipt validation; no early grading/sound |
| Imported and corrected source | SourceCommitted, FingeringCorrectionCommitted | Heavy import/ONNX prediction occurs outside session lock under source_mutation; source identity and revision are validated on install |
| User settings and hardware actions | SettingsChanged, DeviceSelected, CalibrationRequested, HardwareRequested | SettingsWorkflows/DeviceWorkflows retain validation; session sequences mutation |
| History/persistence operations | HistoryExported, PieceHistoryDeleted, LearnerHistoryDeleted, SessionClosed | HistoryManagement and SessionLifecycle retain durability and cancellation rules |
| Future score readiness | PreloadReady, PreloadFailed | ScorePreloadWorkflow validates stage and revision; does not choose a new independent lesson |

**Important timestamp preservation:** The MIDI hardware callback obtains
`received_at = self.clock()` **before** requesting the session RLock.
Captured source/transport facts and graded delivery are then sequenced
under that lock. Moving the timestamp sample inside the lock would shift
notes by the duration of a source-admission or persistence operation;
this was caught and corrected in 29d6aa0. A callback cannot credit a
future unadmitted take: grading remains gated by MidiIngress and the
validated playback receipt.

**No accidental blocking work in tick:** Source preparation/fingering
computation, native score geometry and semantic generation, and library
health diagnostics retain their own bounded preparation workers or locks;
only exact adoption/reconciliation enters the session mutation boundary.
The pre-existing `source_mutation` mutex remains necessary to serialize
source import and fingering correction while releasing the application
lock during inference.

**Post-migration dependency check:** All 79 current Python application
modules were read from the repository at the A1 integration HEAD and
checked for the two deleted coordinator classes, their old instance
names, the removed MIDI ingress method and the previous direct fingering
workflows method. There are no matching production references in those
modules. This does not verify semantic behavior, the current Godot scene,
or source-module references outside the application package.

**Current remaining debt (updated 2026-11-22):** The previous
`SessionCommands` mutable action/effect/prepared/idempotence context and
the `ControlDispatcher` router were deleted after complete caller migration.
`TeachingDecisions` validates and installs exact lesson decisions and
owns their plan/source/stage-bound prepared selection. The public UI,
MIDI and physical command paths enter `PracticeSession`. The previously outstanding
immediate-continuation event queue now belongs to `PracticeSession`,
with typed `ImmediateTransition` entries, an explicit follow-up return
from `PracticeTimeline`, and the former mutable same-tick flag removed.
The remaining A1 work is complete event/effect atomicity and verified
Stop/stale receipt/source transition behavior. `PracticeTimeline`
still executes lesson and settlement continuation logic (primarily A2),
and separate bounded
library-health/future-score workers remain necessary for non-blocking
preparation (A4). No current-revision runtime acceptance is claimed.

The new event envelopes are frozen dataclasses but may carry mutable
JSON payload dictionaries or already-prepared source objects; these are
used immediately under the lock and are **not deep-immutable event logs**.
Authentication and source generation validation remain the domain's
responsibility.

### A1 command-context elimination and source-bound MIDI evidence (2026-11-22)

The session event boundary now uses an explicit original teaching decision
and explicit cancellation reason. The old `SessionCommands` and pure
`ControlDispatcher` files are absent from current source. The lesson owner
validates `CommandEffect` and holds one source-bound approved exposure;
a native score-ready/retry cannot silently consume a previous piece's
`prepared` field. The selected exposure identity includes the same
LearningPlan instance, source fingerprint, and stage key, and is reset
when a new source is installed.

Deferred MIDI is a typed `DeferredMidi` record whose **original**
fingerprint, score revision, stage, hand, transport id and exact timestamps
survive across the native worker tick. The queue is checked against the
newly selected source before replay. A new take epoch for the *same*
stage may receive an event only if the corrected physical time is at or
after the newly authorized run onset; notes from earlier rests do not
earn credit by crossing an epoch. Clearing the queue on Stop and source
cancellation remains with `SessionLifecycle`.

The static app-module audit covers 77 extant Python application files
and found no remaining executable references to `SessionCommands` or
`ControlDispatcher`. The former file owners and callers were removed
rather than left as redirecting wrappers. Source code has **not** been
parsed/executed by the target embedded Python 3.14 or Godot runtime in
this environment; the behavioral and physical gates remain open.

### A1 immediate-transition queue implementation — 2026-11-22

The native tick's one short-lock transaction now owns
`deque[ImmediateTransition]`. Each domain update reports whether an
immediate follow-up becomes due, without holding a latent mutable
`_followup_requested` field or publishing an intermediate score state.
The worker drains at most one initial update plus 16 follow-ups; an
overflow or transition exception pauses the current transport and
publishes the original save/retry error notices.

Automatic preview-repeat, feedback settlement, and immediate
post-completion transitions report their follow-up through a return
value from `PracticeTimeline`. After the queue is empty, only
source/revision/stage/hand-authenticated deferred MIDI is replayed, then
the authorized playback status and live feedback are projected once.
This keeps the original physical reservation/attestation authority and
does not invent a second timeline or background queue.

The method-level change and source consistency were reviewed through the
connected GitHub tree. **No Python 3.14, Godot or fake MIDI runtime gate
has executed on this HEAD**, so replay, failure, Pause/Resume and
physical ink invariants remain unverified.

### A1 committed MIDI identity and fail-closed Stop (2026-11-22)

`PracticeSession` now publishes a frozen `MidiArrival` identity after
each successful or failed serialized event. The actual physical callback
samples that **committed** object before it waits for the application
lock and copies the hardware message. Its source fingerprint,
revision, stage/hand, device, transport and durable-evidence
cancellation generation are compared under the lock before grading
or lesson-control effects. Deferred MIDI uses the same canonical
identity validator; there is no alternate old-tuple replay branch.
Only an authorized same-source automatic transport rollover may
cross a transport epoch, and only when corrected hardware onset is
at or after the new run clock. A rejected obsolete note-off may clear
suppressed shortcut release state on the same physical device, but it
cannot execute a shortcut or earn any practice credit.

Urgent user Stop no longer depends on stale renderer read-model
projections or an irrelevant curriculum-generated effect. Pause and
Resume likewise bypass unused teaching-decision preparation. The
current Godot coordinator already queues Stop above subsequent
navigation/pause gestures while a request is outstanding. It cannot
preempt a Python source-import command **already running on the same
native worker**; that latency is an unresolved operational gate, not
evidence of a tested Stop priority guarantee.

A failed guided-evidence snapshot or atomic ledger interruption now
leaves playback authorization invalid, the running take disabled,
deferred notes cleared and the visual transport frozen, while
preserving the unflushed original recorder/evidence for retry.
Successful Stop preserves its original durable cancellation order.
Runtime execution and physical MIDI behavior remain unverified.

### A2 frozen completed-take and rolling recovery receipts (2026-11-22)

`AttemptSettlement.TakeResult` freezes the selected `TeachingBinding` and
score revision, hand, attempt ID, original source IDs, completed passage,
performed BPM, raw immutable `PlayedNote` presses/releases and
`Assessment` before persisting. Both full/focused and rolling takes
retain this evidence for any storage retry, rather than rereading a
mutable recorder under another tempo or source. Rolling receipts skip
duplicate evidence sealing and reuse their original tempo/feedback.
A changed engraving revision or cancellation epoch rejects replay.

The durable settlement `effects_applied` checkpoint differentiates
progress saved from source presentation applied. Completion marks remain
visible until successor installation succeeds. The previous
`PostAssessmentEffects` instance/file was removed; its post-assessment
and performance/section/recovery completion effects now belong to
`CompletionContinuations`, together with successor dispatch. All 76
current Python application modules and 16 test modules were source-scanned
for callers of the deleted service and none were found.

Pure Practice Flow policy remains the only graded pace decision;
`practice_windows.moving_windows` contains the authored one-bar then
cumulative trailing-four-window rule. `PracticeFlowCourseSession` now retains only a source-plan-keyed
`FlowPhase` (stage plus Listen/Free/Tempo). Its public `FlowState`
projected BPM, failures, clean runs and returns-to-Free are derived under
the application lock from the canonical `LearningPlan`. Opening another
piece with the same authored-window identifier does not reuse its old
phase; the transition reducer, public flow status and existing action
names are retained.
Course-scoped settings and behavior tests for all source strategies
remain open. All of the above is source inspection, **not tested
Python/Godot or physical acceptance**.

### A2 course policy and continuation ownership checkpoint — 2026-11-22

**Source changes on main (not runtime acceptance):**

- `lesson_settings.course_rules(generator_name, warmup=...)` returns immutable,
  selected `CourseRules`. Practice Flow gets its two-target-pass requirement
  from the existing pure reducer, its four-bar cap from `practice_windows`,
  and a 50%-of-target first graded Tempo step after Listen/Free.
  Initial Listen remains at the prepared source tempo. Source-progression, selectable
  Coda/Fukuda and built-in warm-ups retain the previously configured flat
  `lesson_settings.json` values (three clean runs and two-bar source focus
  by default). The flat on-disk tuning format was not changed.
- `teaching_course.CourseState` resolves the clean-pass rule from the selected
  generator. Source segmentation, Practice Flow engraving-stage selection and
  recovery thresholds request their explicit course rules. Manual tempo
  increases use one course-owned maximum, now also published by
  `LearningPlan.maximum_stage_bpm` to the control read model. In Practice
  Flow the + button is disabled at the original target BPM.
- `LearningEvidenceSession` records the selected course-rule snapshot
  alongside the historical generic tuning and original source identifiers.
  Newly recorded rule identities are version-distinct from earlier evidence;
  previous ledger records and saved lesson state are left intact. Historical
  attempts are not silently reclassified as current-rule attempts.
- `RecoveryWorkflows._apply_prepared_recovery` is the one selected-response
  executor for whole-response and remedial preparation, cursor/attempt,
  transport and notice effects. The source-bound response selectors remain
  pure; guided note-isolation and untimed timed-review preparation keep
  their distinct semantics.
- `CompletionContinuations.dispatch_effect` now validates its receipt,
  decision ID, phase, installed source fingerprint, stage and revision
  **before** applying an effect. `AttemptSettlement.commit_full_passage`
  binds a receipt replay to the original run/session, cancellation and
  authority/course revisions, installed stage and already-committed progress.
  Once-applied effects remain one-shot.

**Remaining A2 gates:** Runtime acceptance is outstanding for exact-HEAD
Practice Flow, Coda/Fukuda, warm-ups, failed SQLite settlement, interrupted
rolling takes, Stop/source replacement, stale and lost physical ACK, guided
aid and all saved-session reopenings. The remaining rolling boundary
assessment/continuation handoff still needs a writer/owner audit before
A2 can be closed. No Python, Godot, embedded native, package or physical
MIDI test execution is claimed; CI remains manual-only.

**A2 explicit-retry closure (2026-11-22):** A failed post-commit full
continuation now sets the runtime retry flag without clearing the original
receipt, note marks or selected feedback transaction. The user Start/Retry
action re-enters `CompletionContinuations.retry_failed_publication`,
retries durable/post-commit effects once, and publishes only after dispatch
succeeds. Worker ticks with stopped automatic playback do not retry it
implicitly. `SettledSourceFacts.automatic` comes from the original
`TeachingRouteFacts` instead of the faulted transport's current auto
flag, and an explicit Retry restores the selected automatic course intent
before effect dispatch. The original route is not reselected. New regression
coverage checks the stopped-auto gate and failed-effect feedback retention.
This remains source-level, unexecuted acceptance.

### A2 rolling and failed-continuation retry checkpoint — 2026-11-22

**Implemented on main, not yet runtime-accepted:**

- Rolling `TakeResult` replay now requires the original run, session,
  fingerprint, physical transport and cancellation identity, plus exact
  source revision, selected passage, hand/BPM and the committed authority/
  course epochs. An alternate learner, changed stage, restarted source or
  further progress cannot claim the same receipt.
- Rolling recovery effects are acknowledged individually in
  `AttemptSettlement`, after each accepted action completes. Replays skip
  the previously acknowledged tempo, completed-rest, preparation, streak,
  attempt, notice, withdrawal and cancellation effects. The required effect
  set is determined by the original transition, and rolling decisions follow
  the same `settled -> effects_applied -> published` lifetime as full takes.
  A failed effect retains the frozen receipt for retry; a superseded or
  unrecognized effect is rejected.
- `PracticeTimeline` prioritizes the frozen rolling decision over new
  boundary assessment when an effect failed after boundary advancement.
  The existing manual Retry path also reuses the same frozen rolling take.
- `RecoveryWorkflows` now rejects stale remedial assignments and missing
  active sources instead of silently treating their no-op as successful
  continuation publication. Selected action/deadline validation occurs
  before cursor/transport effects.
- Full-passage post-commit failures now retain their original
  `TeachingContinuation` feedback transaction even after automatic
  playback is stopped or the original deadline withdrawn. Explicit
  Start/Retry re-enters the selected transaction, including its physical/
  source effects, instead of merely resaving progress. Failed effect dispatch
  preserves original marks and does not publish the receipt; successful
  replay publishes once without a second assessment.
- Added `tests/test_rolling_receipt_replay.py`,
  `tests/test_continuation_effect_guards.py` and
  `tests/test_course_rule_scopes.py` for source/epoch mismatch, one-shot
  effects, failure retention, worker precedence, stopped-auto retry,
  post-commit publication and alternative/warm-up rules.

**Remaining A2 acceptance:** Run the exact-HEAD Python suite and fake-MIDI
full/focused/rolling traces, inject real SQLite failure before and after
durable commit, verify Stop/source-change and physical admission/ACK loss,
saved-session reopening, Coda/Fukuda and warm-up behavior, Godot embedded
execution and real keyboard/audio. Individual effects are acknowledged only
after their call returns; if an external effect partially mutates then raises,
the corresponding physical reconciliation must still be verified in A3.
No passing runtime tests or CI completion is claimed, and GitHub CI was not
triggered. **A2 remains IN PROGRESS until these gates pass.**

**Follow-up A3 epoch reconciliation:** Idempotent `playback.present`
replies are accepted only for the same active source fingerprint,
stage, revision, hand, end-beat, physical transport ID **and mode**.
Terminal `complete`, `failed` or `idle` cannot resurface an old
authorization. The existing bounded lost-ACK reconciliation remains
in force; `tests/test_physical_present_epoch.py` also covers the
terminal/mode cases. Source-inspection only, no actual physical ACK
fault injection has run on this HEAD.

**A4 identity correction:** Both current and future bundles now use
`music.source_note_id(note,index)`, the same canonical original/legacy
note-ID rule used by `display_envelope` and native semantic notation.
This keeps supported sources without explicit IDs readable while
rejecting duplicate/mismatched graded attack identities.

### A3–A6 integrated development checkpoint — 2026-11-22

**A3 — physical receipt replay hardened (source integration):**
`PlaybackCoordinator.present()` now requires an idempotent previously
authorized receipt to remain attached to the exact current source
fingerprint, stage, engraving revision, hand, sounding end and
`transport_id`. A stale repeat `playback.present` cannot reuse a
receipt after its source/transport changes, even before an explicit
invalidate callback reaches the coordinator. Added
`tests/test_physical_present_epoch.py` for same-epoch replay and
stale Stop/source/transport rejection. This does **not** complete A3's
aggregate consolidation, full physical failure reconciliation or
native/audio acceptance.

**A4 — one current/future ScoreBundle production path (source integration):**
`ScoreArtifacts.bundle(ScoreSelection)` compiles one immutable-response
snapshot of authentic native layout, semantic model and source IDs under
the exact fingerprint, revision, stage/window/hand and original-note
identity. It rejects mixed revisions, empty/duplicate IDs and any
disagreement between the selected hand's graded notes and the semantic
active IDs. `ScoreReadServices`, `PracticeEngine` and
`EngineCommands(score.bundle)` expose the same selected source.
`FutureScore` uses the very same compiler and retains its bounded
background lookahead/adoption.

The active Godot `ScoreAssetSession` now requests that bundle once,
checks both halves *before* installing it, and preserves the native
retained-CanvasItem readiness requirement before `score_ready`.
`ScoreAssetQueue` is one request slot, not separate layout/model
requests and retry clocks. The embedded `native_bridge_smoke.gd`
checks real native layout and original semantic notes through that same
bundle. The old `score.native_layout` and `score.semantic` Python
read endpoints remain available to current headless diagnostics/behavior
tests; they are no longer the production native preparation protocol.
Added `tests/test_score_bundle.py` for version/source, original IDs,
read isolation and current-source changes. Same-HEAD Godot execution,
repertoire, fingering corrections and prepared-stage promotion still
need verification; A4 is **not accepted** without those.

**A5 — presentation contract safety:** Python state validation and
its generated Godot counterpart now refuse nonfinite numerical
transport/visual coordinates and nonfinite target beats. The generator
and generated file have matching source changes; the prior
`target has no source_beat` error text remains compatible. Added
`tests/test_state_contract_number_validation.py`. A5 still requires
the complete scene/callback policy audit and one physical score-surface
interface.

**A6 — duplicate native readiness removed:** The active score asset
session no longer owns separate pending flags, semantic-model revision
or retry state. The native diagnostic path reports one
`bundle_pending` fact. No supported course, warm-up or stored-data
format was removed. Other A0 inventory entries, old orchestration
composition and library/persistence migrations still require a full
reachability audit before A6 closure.

**Embedded bridge integration:** `PianoNative::is_asset_operation`
also routes `score.bundle` to the existing dedicated asset worker.
Without this C++ dispatch change the single larger native bundle
would have serialized Verovio engraving with the musical tick.
The previous independent diagnostic read routing is preserved.

**Verification and release gate:** All above changes are committed on
`main` but **have not been executed** in Python, Godot, embedded
native or physical MIDI/audio. CI stays manual-only and has not been
triggered. A0–A7 are not falsely marked complete; A7 needs the same
final HEAD for `bash scripts/test.sh --coverage` and
`bash scripts/verify-embedded-production-local.sh`, then the
owner's connected CA49, audible count-in, visual continuity,
Pathétique II (only if provided), repertoire and relocated-package
acceptance.

### A2 receipt replay and publication boundary — 2026-11-22

A selected `TakeResult` captures immutable original MIDI
`PlayedNote` evidence, original source-note IDs and the run/session,
source/revision, stage/hand, transport, attempt, tempo, window and
cancellation identity. `AttemptSettlement` is the only durable receipt
owner. It now recognizes an already-committed focused/performance
assessment and reuses that receipt only if the original input and
acknowledged canonical progress can still be verified. No second
assessment or evidence seal is selected on that retry.

Once that receipt exists, its state moves from `settled` to
`effects_applied` after the accepted source, revision and score assets
have been installed, and to `published` only when the selected
continuation successfully finishes. A stale/superseded pending decision
cannot be settled or marked as published. In the continuation owner,
the exact `ContinuationIdentity` is acknowledged only after the whole
dispatched effect succeeds; an identical later call does nothing and
conflicting effects under the same identity fail closed. The existing
`PlaybackSession` still owns its separate physical transport
attestation. These changes consolidate publication idempotence without
inventing an additional teaching coordinator.

`PracticeFlowCourseSession` only keeps transient Listen/Free/Tempo
phase, keyed to the installed plan; the canonical `LearningPlan`
owns BPM, streak, failures, mastery and returns-to-Free. Pure
`practice_flow` functions remain the selected practice-flow policy
rather than a second mutable lesson owner. Warm-ups and
non-practice-flow courses retain their existing policy paths.

**Unverified:** No executable Godot, embedded native, fake MIDI,
SQLite fault-injection or physical keyboard acceptance on this HEAD.
Atomicity of every partial side effect, exact course-scoped
settings/policy binding and removal of all legacy recovery flows
remain A2 exit gates.

### A0 remaining evidence required before marking complete

1. Recheck source/runtime reachability for each preliminary **merge** or
   **remove** candidate, including dynamic Godot script creation,
   Python generator registrations, optional policy settings and package
   script inclusion. Record actual callers and state writes rather than
   inferring dead code from filename or static import absence.
2. Trace and record the complete scenario-to-owner transition matrix
   and every asynchronous success/failure edge against the exact source
   revision, including persistence rollback and next-stage art adoption.
3. Obtain a complete exact-HEAD local baseline run for both core/Godot
   behavior and embedded-production/repertoire/package. Record failures
   and correct the roadmap's gate status from evidence, not prior green runs.
4. Obtain the owner's explicit decision *only if* retiring a still
   supported selectable course, policy or durable data type is proposed.

### Composition closure audit — 2026-11-21

The pre-audit composition file retained many direct imports from the
former 2,783-line facade despite constructing no objects from those
imports. It now imports the concrete current application owners only,
and the four unused constructor ports discovered in the extracted
services have been removed at both ends. `PracticeEngine` remains a
343-line public facade and constructs its services through
`application/composition.py`, without injecting a facade or
global service locator into the application services. Full dependency
closure and packaged/native acceptance remain separate requirements.

### Command execution boundary — 2026-11-21

`PracticeControls` owns the locked public command scope, user-action evidence
and typed dispatch. `LearningActions` applies generator-decided lesson
navigation; `TransportActions` applies the selected playback and admission
effects. Resume's deferred score-ready work is handled within the current
transport transaction rather than recursively entering the full command
router. The existing `SessionCommands`, `PlaybackCoordinator`,
`PlaybackSession`, and `TeachingDecisions` remain the only owners of their
respective choices and receipts. This change must pass integration gates.

### Final VisualTransport state-writer audit — 2026-11-21

The full 77-module application scan found no remaining direct writes
to another owner's recognized attempt, playback, transport, source or
lesson fields (including private owner references). The prior explicit
writers in `PlaybackSession` were migrated in `daf466e6` to
`AttemptRuntime.begin_timed_review`, `suspend_recording` and
`VisualTransport.finish_rewind`; `SessionCommands` owns nested
command-reason scopes in `0a688d5b`. This is an attribute-assignment
audit; dynamic behavior and all physical acceptance remain separate.

The application services no longer assign directly to the visual transport's
`scheduled_start`, `rest_take_end`, `short_rest`,
`next_boundary_beat` or `continuous_horizon_beats`. The transport
owns semantic installation, clearing and the renderer's bounded geometry/
reading-horizon validation. The source identity, grading clock, displayed
score and immutable admission ledger remain unchanged. This audit covers
the migrated Python caller modules, not physical instrument acceptance.

### Final runtime and dependency closure — 2026-11-21

A full targeted scan across all 193 Python source modules and 146
production Godot scripts found no old HTTP/socket bridge, alternate
score renderer or abandoned practice-engine implementation in the
active runtime. The native in-process adapter intentionally imports
`PracticeEngine`; the headless `score_queue_next` entry remains
an explicit test/command fixture contract; generated MusicXML is
internal engraving/research data, and historical migration/coverage
labels are not active alternate architecture. The developer MCP addon
is not autoloaded and is removed by standalone packaging.

All 77 `application/*.py` modules were separately checked for direct
cross-owner state assignments; the remaining review/Recorder/rewind,
scheduled strip and command context writers were moved to their
authoritative owners by `daf466e6`. These are bounded source audits;
unknown runtime reflection and physical behavior are not guaranteed.
[Full core/native/relocated-package CI 44907200749](https://github.com/tpepels/piano_teacher/actions/runs/44907200749)
passed on the final code source `daf466e6`. The only subsequent
changes are documentation. Physical hardware/visual acceptance and
a truly separate clean target machine have not been performed.

### Learning evidence persistence boundaries — 2026-11-21

The durable ledger is now an explicit composition rather than a combined
schema, session, retention and export class. `LearningLedger` keeps session,
attempt, event, decision and outcome writes. `learning_ledger_schema.py`
initializes relational constraints and trigger-backed logical-byte accounting;
`LearningDetailRetention` enforces detail budgets and ages without discarding
pending attempts or durable summaries; `LearningHistoryExporter` builds a
consistent read snapshot and writes redacted JSON with atomic replacement.
`learning_ledger_common.py` supplies canonical serialization, validation and
redaction. All collaborators share the ledger's existing SQLite connection,
not a separate writer, data copy or asynchronous history service. Public
`LearningLedger` methods retain their meanings and persistence migrations.
Source: [`8eccd16e`](https://github.com/tpepels/piano_teacher/commit/8eccd16eb1b5ea7fa80ef43b56e7fe955925013e).
Core CI passes (103 Python passed, four skipped; Godot native behaviour zero
failures); the full native-production/package gate is pending separately.

### Native acceptance blind spot — corrected 2026-11-21

Full-repertoire Godot runs that appeared green still emitted hundreds of
runtime exceptions: `ScoreEffects.transition_mode` tried to clear the
removed `PracticeScoreStage.impact_callout` member. The stage now owns only
its actual `GameStage` transient energy, and the stale callout access was
removed in [`03de4498`](https://github.com/tpepels/piano_teacher/commit/03de44984438700ca70a38fe517121b487ab331c).
The existing `verify-embedded-production-local.sh` now treats every Godot
`SCRIPT ERROR:` as a failed acceptance case even if Godot returns zero.
Previously cited green native runs had 239 and 229 such exceptions, so their
visual-mode path was not cleanly accepted. The corrected strict full run is
[44909630866](https://github.com/tpepels/piano_teacher/actions/runs/44909630866)
(pending as of this audit); no physical acceptance is inferred.

### Pause and selected-window projection — 2026-11-21

`GuidedPresentationSession` now freezes the same
`ContinuousScoreFlow`/`PresentationTimeline` world coordinate on an
acknowledged Pause and preserves Free holds across introducing, disconnected,
and guided-complete phases. It does not introduce a second musical clock or
rewrite already admitted immutable strips. `PracticeControlPolicy` and the
backend pausable-phase contract agree on these Free states, and the Play/Pause
label follows the same active-state predicate. The native stream still
pre-engraves authentic neighboring context for clefs, ties and safe cuts,
but visible source-strip crops expose only the selected exercise window and
full sounding tails. The Python `TeachingController` shares the same pause
lifetime in introducing/disconnected states (`9eec8103`). Native
`RenderPass.event_visible` excludes context-role bars and notes
(`fc65791f`) while `SourcePassPainter` retains the selected window's
authentic ending barline and repeat mark (`b37e7693`). The original full native run on `b37e7693` failed obsolete assertions
that Pause should keep scrolling. The existing UI and repertoire checks now
require stationary notation and unchanged admission on Pause (`1948651a`).
A separate real Resume failure on `1948651a` revealed that Python keeps
`paused=true` while awaiting graphical authorization: the visual hold then
prevented the future-deadline inversion from finishing. `ae20d6c4`
reconciles holds in the canonical presentation frame, and `81ae006f`
releases that hold specifically for a pending, explicit Resume intent.
No new timeline, grader, renderer or parallel reservation authority was
introduced. [Full core/native/repertoire/relocated-package acceptance
44925026112](https://github.com/tpepels/piano_teacher/actions/runs/44925026112)
passed on `81ae006f` with zero Godot script errors. Physical piano,
audible and visual acceptance remain outstanding.

### Physical MIDI error and exact-repeat geometry — 2026-11-21

The actual Pathétique keyboard run on `9312b83c` exposed a removed
`impact_callout` UI dependency and a fixed repeat rejected by the immutable
source queue. `LiveMidiFeedback` now uses the existing effects owner only.
`PracticeScoreStage.continuation_geometry` supplies native measured
rest/header clearance through `PracticeCommandCoordinator` and
`TransportActions`, including the `score_ready` handoff before the backend
plans automatic deadlines. `ScoreTransportReservation` uses the same
source/rest obstruction rules as `ScoreStreamQueue` and the existing
`announced_empty_strip_start` proof for a late fixed source. Neither
component may retime an authorized take or move already admitted ink.
Queue failures expose the rejecting physical guard, and the existing
native-production verifier fails on those errors. Source through `584f017a`; full
[CI 44927279888](https://github.com/tpepels/piano_teacher/actions/runs/44927279888)
passed core and all embedded/native/repertoire/package gates with no
script errors or reported immutable admission refusals. The exact
Pathétique II hardware session was not reproduced by CI and remains
open for connected-piano, sound and visual acceptance.

### V0/V2 migration in progress - Python-owned visible controls (2026-11-21)

The active [V0-V7 roadmap](../ROADMAP.md#active-roadmap-ui-boundary-and-midi-transition-verification-v0-v7-2026-11-21)
addresses the remaining cross-language behavior split after the S0-S7
Python refactor. Previously `PracticeCommandCoordinator` interpreted
primary/Pause/Retry/Listen through Godot's `PracticeControlPolicy` while
`PracticeScreen` independently chose captions and disabled controls.
Both could disagree with backend phase and visual/admission status.

The first migrated production route is now: Godot button or shortcut emits
a `ui_*` gesture with native score readiness -> `practice.command`
-> `PracticeControls` resolves the gesture from its current snapshot
under the session lock -> existing authoritative `TeachingDecisions` and
`TransportActions` apply the command -> the read model publishes the
`controls` projection consumed by the native screen. Pending Pause uses
the last published backend action only to manage an outstanding native
request. The score still must be physically ready for start/restart
authorization. Explicit legacy public commands continue to work during
the migration.

**Follow-up in-progress migration:** The `controls` projection
now includes backend-resolved UI gestures: primary, Pause, Retry, Listen,
Previous lesson, source-bound Review previous, Skip, tempo increase/decrease
and physical MIDI start. Native
`PracticeScreen` consumes the projected visibility/enablement and
caption facts; the clicked navigation/tempo actions are routed as
uninterpreted `ui_*` intents, resolved from the fresh Python
snapshot. Score-affecting UI intents carry `score_ready`, renderer revision
and source fingerprint. The application lock rejects a ready
renderer belonging to a different source revision before it acts.
A navigation-only `ui_suspend` requires no renderer witness; it can only
pause an eligible take, never turn an existing Pause into Resume.
The backend command-success routing recognizes the new navigation
intents. Native business-state inference remains elsewhere, notably
in admission, presentation hold and remaining advanced controls.

**Original V3/V4 conflict (resolved in source, unverified in runtime):**
The old `ScoreAdmissionGateway._deadline_at_world` selected a
musical deadline by binary-searching the Godot visual clock.
The native Pause/Resume implementation also released a painted hold
for an unconfirmed intent. Both paths have been replaced. The native
timeline now exposes separate held painting and pure physical-travel
measurement, and the only final deadline is bound by the Python
playback coordinator from authenticated score evidence. Native
execution and physical acceptance of the replacement remain open.

This does **not** complete V0 or V2. The renderer still owns
physical admission and score presentation while Python owns musical
deadlines, transport authorization and controls. The independent
`practice_control_policy.gd` has been deleted. The complete
transition graph, simulated-MIDI/native scenarios and physical
acceptance have not yet been executed. No new unit tests have been
added at the owner's request.

### V4 native hold and forecast boundary (2026-11-21)

The painter's held score position now remains frozen during a pending
Resume, before the first Free target, and through a pending Free-to-Tempo
transition that has not yet been physically authorized. Native admission can read an
independent hypothetical future from the same tempo projector even when
the displayed world is held. Only an authorized backend playback segment
may release the visual hold; its future tempo epochs retain exact time
coordinates through the release and are rebased spatially from the held
world. Later commits replaced the gateway's binary-search deadline
inversion with a direct, read-only physical travel measurement;
Python chooses the only admissible downbeat. The full MIDI/renderer
transition graph and physical acceptance remain unverified.

### V3 admission boundary: typed physical evidence, authoritative scheduling

In-process `playback.reserve` no longer accepts an absolute deadline
from the native renderer. `PhysicalAdmissionEvidence` contains a native
backend-clock sample, measured travel to the physically armable source
world, and stream/revision generations. `PlaybackCoordinator` verifies
source/attempt identity and delegates the *only* deadline choice to
`physical_admission.choose_admission_deadline`, which calls the
authoritative `MusicalScheduler`. It rejects stale, impossible,
source-mismatched or premature placements and does not retime an
immutable strip after it was provisionally armed. Fixed announced
repeats must fit the known exact deadline. The returned reservation
receipt, never the input witness, defines audio, grading and visual
source epoch timing at `playback.present`.

Physical forecasting uses the map of
`state.playback_timeline.current` (the already admitted source) until
the successor is authorized, regardless of UI mode/phase. A pending
source's different tempo map cannot change the outgoing physical clock;
a paused existing variable-tempo source retains its actual segments.
The new contract removes a duplicate musical-deadline decision,
although native-to-engine transaction/lifecycle acceptance remains open.

### V3 native receipt identity gate

The native gateway checks the complete immutable intent/attempt/take
identity before binding a physical source, accepting the presentation
reply or promoting a prepared renderer. A reply without a matching
segment cannot authorize local notation or count-in. Uncertain or
mismatched authorization is reconciled against the backend ledger,
not inferred from an asynchronous callback arriving successfully.

### V5 obsolete native control policy retired

The independent `PracticeControlPolicy` is removed. Raw UI gestures
and controls are owned by the Python application projection, while
`PracticeScreen` paints the backend facts. The existing native syntax
gate now compiles the production coordinators for the actual playback
admission and visual timeline instead of the dead policy. Other
native domain-like responsibilities still require V5 audit and tests.

### V5 additional native control and navigation boundary — 2026-11-22

Navigation has no phase/action-based Pause policy; on exit it emits
`ui_suspend`, whose one-way Pause/no-op meaning is resolved under the
Python practice lock. The command queue retains it when a Play/Listen
request is still pending ([`ceffe050`](https://github.com/tpepels/piano_teacher/commit/ceffe050a0822402934e3eae18fb14310ca31d31)).
Advanced Pause now draws and emits the same backend control actions
as the main screen. Left/right lesson shortcuts use the backend UI
projection rather than unconditional next/previous commands
([`12f04f9`](https://github.com/tpepels/piano_teacher/commit/12f04f9a1372ecbadef9eefadffc9f78ba8b2d97)).
Paused seek availability reads the backend projection
([`2102229`](https://github.com/tpepels/piano_teacher/commit/21022296de3cef3f5b73c1722f0cb353afef5d3f)).
Native preflight rejects malformed physical geometry and exposes its
exact refusal reason without creating another scheduling owner
([`19c7378`](https://github.com/tpepels/piano_teacher/commit/19c7378c8906cdcbf8e83dd3fcf605a6b96f494d)).
The separate Lesson Path passage controls and S/Stop gesture now resolve
through the Python projection. Returning from a rejected lesson navigation
does not change the screen. Source-published activity, hand, hint and
explicit Lesson Path Skip eligibility replace local modal phase/locking rules.
The native binder and backend reservation protocol no longer have a physical
paused-source reuse branch, shortened-count-in option or old receipt flag.
A fresh full-bar count-in and immutable future source are required for every
physical Resume; paused predecessor ink remains protected in the same ledger.
Announced, already-authorized automatic continuation rests retain their
separate valid reuse contract. The lightweight locked command snapshot
and the rendered snapshot share one pure transport-status projection;
both observe the same pending intent, admitting state and terminal failure. See the
2026-11-22 source commits and status in [ROADMAP](../ROADMAP.md).

The ownership scan distinguishes display-only phase readers (`GameStage`,
`GamePhaseCue`, `ScoreStepTimeline`, `NativeScoreFeedback`,
`PracticeScoreStage`, `ViewBase`) from the native queue admission and
score-asset readiness adapters. They may draw or prefetch a selected state;
none may select practice progression or override a backend deadline.
Native parsing, real-scene CI and connected-piano acceptance remain open.

### V2 fail-closed snapshots and V5 warm-up eligibility — 2026-11-22

The Python state-contract owner additionally publishes required top-level
ports, action/enablement shape for all controls and valid motion-directive
variants. Its generated Godot checker rejects unknown/missing/ill-formed
snapshots **before** adoption by the UI, input coordinator or native score
queue. The last accepted source is preserved, stale controls are blocked and
a subsequent valid snapshot restores normal presentation. No new local
phase/transport state machine was added.

Warm-up step, hand and passage selection is validated in
`teaching_course.manual_progress` against the ordered earned stage keys.
`stage_change` invokes the same pure eligibility rule before stopping a
current take. `lesson.overview` reports exact stage availability; Godot's
Lesson Path and advanced Pause selectors display that backend status.
Unrestricted manual navigation for ordinary imported scores is preserved.

These source changes and new real-MIDI regression scenarios have not
been run against this revision. See [ROADMAP](../ROADMAP.md).

### Additional source/receipt invariants (2026-11-21)

A replayed `playback.present` receipt is valid only while its
original segment, take and attempt are still active and have not
failed. Native state/status reconciliation requires a non-failed
playback ledger before promoting its already matched receipt.
The Free/Godot target cache is source-revision-scoped and resets on
a different practice window without waiting for an intermediate
mode change. Only unexpired, strictly future guided target plans
may enter the renderer queue; repeated presentation frames cannot
reinsert the same plan.

These invariants are enforced by existing owners instead of
introducing a second application state machine in Godot.

### Bounded failed-admission recovery

The Python playback owner bounds failed physical offers (three
attempts) and pending admission lifetime (120 seconds), retires
expired fixed automatic repeats immediately, and projects terminal
reasons into the practice feedback model. The Godot physical adapter
explicitly withdraws a fixed repeat that cannot fit its immutable
slot, deduplicating by intent/attempt without selecting a replacement
musical deadline. A native failure can therefore leave `admitting`
and restore manual retry instead of waiting indefinitely.

### V5 local request effects cease interpreting backend actions

The native command coordinator no longer cancels count-in sound from
a projected button action or command failure. The existing metronome
frame owner already follows the authorized playback timeline.
Source-bound physical clearance accompanies any raw gesture that
could request timed playback; Python resolves it from current session
state. The asynchronous queue retains a raw Pause gesture while
a different command is in flight.

### V3 physical binding attestation before audible effects

`StreamTakeBinding.owns_authorized_segment` is the physical ledger's
single ownership query for a backend-authorized source. A pending
ACKed arm and a later live segment are both valid only if their
queue owner still exists. The Godot gateway now queries that port
before renderer promotion, visual epoch authorization or local
count-in audio, reporting `playback.failure` to the backend if
the authorized physical source has disappeared. This prevents
an authorization receipt from producing graded/audio time against
missing or superseded notation. The backend retains sole authority
to stop the musical take and publish failure.

### Pending admission is orthogonal to active playback phase

The canonical state projection retains the actual `playing` or
`paused` phase when a separate future `playback_intent` exists.
`admitting` is emitted only for an idle/unpaused transport awaiting
its first score authorization. A speculative successor cannot
replace the active phase seen by stream painting, audio, pause or
practice controls. The coordinator still owns both identities
and presents the successor through the single receipt protocol.

### Source-bound modal command interpretation

The saved resume prompt is a view snapshot, not a valid source of
course transitions. Its “Review 2” gesture now carries only the
offered source fingerprint/revision. Python validates the context
against the current locked session and computes the lesson index
itself. An obsolete prompt is rejected instead of navigating an
unrelated reopened or revised source.

### Physical timing measurement is the inverse of the canonical visual epochs

`PresentationTimeline.physical_travel_ms_to` provides a pure
renderer-domain read port for the time required for an immutable
source slot to reach the playhead. When an authorized source is
already scrolling, it integrates the ledger's committed
wall-clock tempo epochs. When the display is held, it integrates
the existing authored source-time map from the current held
world, without releasing the visual hold. The former iterative
trial projector in `ScoreAdmissionGateway` has been deleted.

The result is only physical timing evidence. Python remains the
sole authority for whether a count-in, repeat or resume may use
the proposed slot and for the eventual downbeat.

### Native acknowledgement completion is idempotent

A state-poll acknowledgement and a delayed direct
`playback.present` reply may refer to the same authorization.
Once one has bound the physical source, the gateway retires the
local transaction in one place. The late reply cannot restart
reconciliation or inherit a pending status into the next take.
Failed physical ownership or runway promotion retracts the
provisional arm and notifies the backend with the exact take
and segment instead of attempting local musical compensation.

### One physical playback-failure reporting adapter

The native gateway reports missing, invalid or wrongly bound
renderer sources through a single source-bound
`_report_authorized_failure` port. The existing four-frame
watchdog covers an entirely missing renderer. Busy report requests
do not suppress a different failure, and a rejected report is
retryable from subsequent active playback state. Godot never
chooses a grading or musical retry policy as a consequence.

### Untimed Free deadline lifetime follows its full source identity

`ScoreStatePublisher` now owns the persistent guided deadline
together with a (fingerprint, stage, revision, transport) key. A
change of source, including a direct Free-to-Free practice-window
change, clears the previous epoch before `MusicalScheduler.guided`
selects another. Read projection refuses a guided target if its
source key is stale. Godot's native target cache is already
revision-bound, but it is never allowed to invent or reuse an
application-level deadline independently.

### V4 motion directives replace native teaching-phase interpretation

`ScoreStatePublisher._motion_directive` owns the semantic choice
to freeze paused/unready material, retain the previous Free hold
during admission, follow the currently required Free target beat
or run an authorized timed score. The read model now publishes this
single explicit `presentation_directive` alongside the existing
source-bound `playback_timeline`. The native
`GuidedPresentationSession` implements only a physical hold and
target-anchor transform. It no longer reads phase-string sets or
expected MIDI note lists to decide practice progress; unknown
directives fail closed. A new source revision clears the native
target binding while the backend source projection creates the
new target plan. This narrows cross-language responsibility
without creating another timeline or clock.

### No default-tempo scrolling before initial authorization

The canonical backend motion directive freezes idle, unadmitted
notation, even when engraving has finished. A pending first
Listen/Play cannot cause a native 40 BPM fallback world clock to
scroll. In contrast, a prepared successor of an *already
authorized* source retains its predecessor's physical rest
projection until the next transaction commits. The production
smoke gate now distinguishes those two cases, instead of requiring
idle movement without musical permission.

### A practice command returns an accepted action, not a second policy

The in-process `practice.command` protocol has a versioned
`{state, outcome}` result. Python resolves the raw gesture and
projects the effects from the action it actually executed under
the session lock. The native command coordinator validates the
result before forwarding only the original state to
`ApplicationStateInbox` and forwarding only the accepted
effects to its UI presenters. The former Godot
`GUIDED_NAVIGATION` and `CALIBRATION_ACTIONS` maps have been
removed. Disabled gestures have an explicit nonexecuted
outcome, so stale button labels cannot initiate navigation.
No transient command outcome is inserted into persistent state
or the source-bound playback timeline.

### Exact repeat rest uses outgoing source tempo

An automatic retry can select a different incoming tempo after
a graded result. The printed one-bar rest between attempts is part
of the outgoing immutable score epoch and therefore occupies one
bar at the outgoing BPM; the incoming BPM begins at the next
authorized downbeat. The Python `AttemptProgression` policy
selects that full-bar deadline from the actual prior `facts.bpm`.
Previously it shortened the rest to the incoming faster BPM and
placed the next header inside still-visible rest ink; the native
queue correctly rejected the resulting physical overlap. The
scheduler now preserves both the strict one-bar musical interval
and the native queue's collision invariants.

### Physical MIDI key gestures never choose practice actions in Godot

The Godot input session now observes only fresh connected MIDI
key events, a stable source revision and a backend-enabled
`controls.midi_start` availability fact. It issues a raw
`ui_midi_start` gesture for Python to resolve under its
session lock. The backend projection chooses actual Start,
manual Retry or guided primary transition from authoritative
mode, phase and automatic-continue policy. There are no native
`if mode=practice -> start` or `if feedback -> restart`
branches remaining in the MIDI input adapter. Input debounce,
modal suppression and source-readiness checks remain physical
and view-owned. The exact accepted action comes back through
the existing versioned command outcome envelope.

### V3 physical proof compares one absolute downbeat, not sampled world magnitude

The preflight world coordinate is measured in an earlier frame.
Under a held canvas, the relative world destination for the same
future downbeat decreases while wall-clock time advances. Comparing
`physical_world_origin >= preview_world_origin` incorrectly
rejected correctly admitted score strips. `PlaybackCoordinator.present`
now authenticates the final **wall-clock arrival**, revision,
queue generation and native segment binding, while publishing
the final actual world placement into the authorized segment.
A frozen Free/Pause canvas can therefore remain still during
the backend-first reservation handshake without deadlocking
the physical playback.

## Current embedded Python application boundaries (2026-11-21)

The facade at `55e31dd2` has **343 lines** and delegates to the explicit
composition root. The following groups show where the earlier engine
responsibilities execute; each uses the existing single source/clock and
domain policy authorities.

| Boundary | Modules and authority |
| --- | --- |
| Composition/public protocol | [PracticeEngine](../piano_teacher/server.py), [composition](../piano_teacher/application/composition.py), [native in-process commands](../piano_teacher/inprocess.py) |
| Manual intent and navigation | [PracticeControls](../piano_teacher/application/practice_controls.py), [LearningActions](../piano_teacher/application/learning_actions.py), [LessonExecution](../piano_teacher/application/lesson_execution.py) |
| Source and teaching choices | [SourceIdentity](../piano_teacher/application/source_identity.py), [TeachingDecisions](../piano_teacher/application/teaching_workflows.py), [ExposureWorkflows](../piano_teacher/application/exposure_workflows.py), [ExposureInstaller](../piano_teacher/application/exposure_installer.py) |
| Playback and physical input | [TransportActions](../piano_teacher/application/transport_actions.py), [TimedPlayback](../piano_teacher/application/timed_playback.py), [TransportTiming](../piano_teacher/application/transport_timing.py), [MidiApplicationInput](../piano_teacher/application/midi_application_input.py), and the authoritative PlaybackCoordinator/PlaybackSession/MidiIngress |
| Attempt and continuation | [ApplicationWorker](../piano_teacher/application/application_worker.py), [PracticeTimeline](../piano_teacher/application/practice_timeline.py), [RecoveryWorkflows](../piano_teacher/application/recovery_workflows.py), [PostAssessmentEffects](../piano_teacher/application/post_assessment_effects.py), [CompletionContinuations](../piano_teacher/application/completion_continuations.py), and the single AttemptSettlement |
| State queries and ink facts | [SessionReadModels](../piano_teacher/application/session_read_models.py), [ScoreReadServices](../piano_teacher/application/score_read_services.py), [LiveFeedbackWorkflows](../piano_teacher/application/live_feedback_workflows.py), [ScorePreloadWorkflow](../piano_teacher/application/score_preload_workflow.py) |
| Durable data and settings | [HistoryManagement](../piano_teacher/application/history_management.py), [SourceWorkflows](../piano_teacher/application/source_workflows.py), [DeviceWorkflows](../piano_teacher/application/device_workflows.py), [SettingsWorkflows](../piano_teacher/application/settings_workflows.py) and their existing repositories |

The composition root injects explicit owner dependencies, **never an engine
backreference or all-purpose mutable context**. Direct imports in 32
new/extracted application modules were inspected; no facade import was found.
The command router no longer recursively re-enters itself during Resume,
the worker drains immediate continuations with a bound, and snapshots do
not enter that worker. The core CI at `55e31dd2` passed; strict
native/embedded/relocated package acceptance on this exact source remains
a separate requirement.

## One desktop runtime

The product is one Godot 4.7 desktop process with embedded CPython, authentic
Verovio notation, one immutable score stream and one MIDI/transport timeline.
The product imports MIDI. Generated MusicXML is an internal engraving format;
missing expression or editorial information is never invented from MIDI.

[Main](../godot/main.gd) composes scenes and services and connects their signals.
[PracticeEngine](../piano_teacher/server.py) is the locked application/API
boundary. Neither is another lesson policy, score ledger or clock owner.
There is no separate Python server, HTTP/UDP bridge or compatibility renderer.

| Responsibility | Authoritative owner |
| --- | --- |
| Course windows, hands, tempo and mastery | [PracticeFlowLessonGenerator](../piano_teacher/practice_flow_course.py) and [teaching decisions](../piano_teacher/teaching_decisions.py) choose one immutable result. Other registered generators retain their own explicit strategies. |
| Selected curriculum and saved progress | [LearningPlan](../piano_teacher/learning.py), validated [SessionCommands](../piano_teacher/application/session_commands.py) and [ProgressRepository](../piano_teacher/progress_repository.py). |
| Listen / Free / Tempo preparation | [Exposure preparation](../piano_teacher/application/exposure_preparation.py) materializes the chosen source; [PracticeFlowCourseSession](../piano_teacher/application/flow_course_session.py) presents its step and messages. |
| Guided targets | [GuidedSession](../piano_teacher/application/guided_session.py) owns the selected fragment, derived beat range, controller, hints and recovery return. |
| Timed authorization | [PlaybackCoordinator](../piano_teacher/application/playback_coordinator.py) owns source-bound intent/reserve/present/cancel transactions. |
| Playback lifetime | [PlaybackSession](../piano_teacher/application/playback_session.py) owns running/mode/automatic flags, take epoch, readiness, count-in and pause/resume effects. |
| Musical time | [VisualTransport](../piano_teacher/visual_transport.py) stores epochs; the pure [MusicalScheduler](../piano_teacher/application/musical_scheduler.py) calculates deadlines; [TempoMapCache](../piano_teacher/application/tempo_map_cache.py) retains the selected immutable map. |
| Physical input | [MidiIngress](../piano_teacher/application/midi_ingress.py) preserves calibrated arrival timestamps and the source-bound grading gate. |
| Listen sound | [ListenSession](../piano_teacher/application/listen_session.py) owns asynchronous audio preparation and score/audio readiness. |
| Assessment and settlement | [AssessmentService](../piano_teacher/assessment_service.py), [assessment policies](../piano_teacher/application/practice_assessment.py), [AttemptRuntime](../piano_teacher/application/attempt_runtime.py) and [AttemptSettlement](../piano_teacher/application/attempt_settlement.py) retain one verdict, take and durable result. |
| Source installation and correction | [SourcePreparationSession](../piano_teacher/application/source_preparation_session.py) owns mutation serialization, source generation and fingering correction identity. |
| Current/future engraving | [ScoreArtifacts](../piano_teacher/application/score_artifacts.py) compiles a frozen selection; [TeachingContinuation](../piano_teacher/application/teaching_continuation.py) retains exact future source/asset identities without selecting another outcome. |
| Commands and accepted state | [PracticeCommandCoordinator](../godot/practice_command_coordinator.gd), [ApplicationStateInbox](../godot/application_state_inbox.gd) and [ApplicationPollSession](../godot/application_poll_session.gd) own request sequencing, accepted snapshots and polling. |
| Presentation reconciliation | [PracticePresentationSession](../godot/practice_presentation_session.gd) reconciles state and score readiness; [PresentationTimeline](../godot/presentation_timeline.gd) owns forward visual projection. |
| Physical admission and promotion | [ScoreAdmissionGateway](../godot/score_admission_gateway.gd) negotiates exact receipts; [ScoreSceneController](../godot/score_scene_controller.gd) promotes exact-revision renderers; [ScoreRunway](../godot/score_runway.gd) prepares assets and retains outgoing layers. |
| Immutable ink | [ScoreStreamController](../godot/notation/native/score_stream_controller.gd) owns the single source/rest ledger. [RetainedNotationPool](../godot/notation/native/retained_notation_pool.gd) owns compiled CanvasItems. |
| Engraving and drawing | [ScoreEngraving](../godot/notation/native/score_engraving.gd), [ScorePainter](../godot/notation/native/score_painter.gd) and [NativeScoreView](../godot/notation/native/view.gd) own preparation, canvas composition and the canvas/lifecycle boundary. |
| Artwork and derived masks | [GlyphAssets](../godot/notation/native/glyph_assets.gd) owns authentic artwork; [GlyphHeadMasks](../godot/notation/native/glyph_head_masks.gd) owns derived head masks; [Glyphs](../godot/notation/native/glyphs.gd) composes them on the canvas. |
| Controls and feedback | [PracticeChrome](../godot/practice_chrome.gd) builds widgets; [PracticeScreen](../godot/practice_screen.gd) presents state and emits intents; [PracticeFeedbackSession](../godot/practice_feedback_session.gd) consumes acknowledged note events. |

Navigation, settings, device selection, input shortcuts and audio each have
dedicated sessions. They use explicit facts and semantic ports; helpers do not
receive an Engine/Main reference or access another owner's mutable internals.

## One selected lesson decision

A generator consumes immutable source/progress/evidence facts and chooses the
next exact exposure. Its decision includes source, hand, scope, BPM, reset
counters and mastery. Announcement, settlement, preparation and save retry
consume that same selection. Display text is never parsed into a decision.

Practice Flow commits Free → Tempo at 50% of target in both its new progress
and next exposure. Listen and Free use target BPM. The display flow and engine
do not select another BPM downstream. Each trailing window has independent
progress, and the full original examination is separate. The complete rules
live only in [Practice flow](practice-flow.md).

The [course state](../piano_teacher/teaching_course.py) exposes the active
policy's required clean-run count, using Practice Flow's existing two-take
constant or the other courses' configured rule. Lesson snapshots, validation
and captured evidence consume that fact. New rule snapshots retain
`clean_runs_required`; statistics use the captured value, falling back to the
recorded lesson settings for older evidence rather than reinterpreting history
with today's course defaults.

The registered `LessonGenerator` interface receives a canonical `Piece` and
returns a `LessonPlanDefinition` with source-safe stages and an unchanged
whole-piece finale. Variants retain source-note IDs and explicit timing/tempo
policies. Composition uses contributor `passage_stages` and `with_feedback`
ports, rather than decoding generator names. Unknown registrations fail
explicitly. Genuinely different source/timing/tempo performances have separate
stage identities; renamed or duplicate performances do not create new credit.

Simplified stages may not silently replace original music. Exact authored
attacks and complete releases survive source selection, including notes held
beyond the selected last barline. A silent bar creates no fictitious attack.
Changed source/stage/hand/rules cannot inherit incompatible mastery.

The `flow_returns` progress table persists floor-failure returns for the exact
window/stage key and hand. The second return can select a real announced aid;
aid completion returns to the original full-window Free exposure. Aid success
cannot award original-note mastery or advance its target-tempo streak.

## Performance source and display envelope

`authored_duration_beats` is the selected measure-grid duration;
`sounding_duration_beats` also covers complete releases beyond its barline.
The first attack chooses the playable opening after leading silence without
retiming original source attacks or changing their IDs. Grading, Listen and
the take's end use the selected source and complete sounding tail.

[DisplayEnvelope](../piano_teacher/notation/display_envelope.py) extends authentic
ink around that selection. `active_note_ids` identify only the performance hand's
required attacks; `display_notes` and `display_measures` may also contain the
other hand, neighbouring bars and sustained carry-ins. Their signed
`display_extent` can begin before active beat zero. The active authored grid and
performance IDs remain unchanged: context is never hidden graded work.

One compiled native renderer draws active and dimmed ink from that envelope;
there is no second context renderer. Announced transformed exercises display
their own source-safe notes rather than silently acquiring original notes as
context. A direct repeat may trim decorative neighbours to preserve its one-bar
deadline, while retaining the required active notes and full sounding releases.

## Practice state and timing

Source beats are quarter-note positions on the authored measure grid. Source
tempo maps convert them to musical seconds. Deadlines are absolute monotonic
seconds. World beats are forward visual positions, projected at frame rate;
they cannot change a MIDI grade or move already exposed notation backwards.

For constant tempo, `seconds = beats × 60 / BPM`; shaped tempo uses the exact
selected map. Scheduler decisions combine independent lower bounds: authentic
count-in, measured glyph/header clearance, predecessor ink, readiness, latency
and any existing reservation. Rest and count-in may overlap and are not counted
twice. Geometry constrains admission; it does not choose a lesson or tempo.

### Authorized graphical playback

Every timed Listen, Practice, Perform, preview, repeat, retry, stage handoff and
resume uses one transaction:

1. Python publishes an immutable `playback_intent`: intent/take/generation,
   source revision, exact exposure, starting BPM, count-in meter and earliest
   musical deadline. Grading and sound have not started.
2. Godot requires compiled authentic assets for that revision and preflights
   the source against the viewport and all live predecessor layers.
3. Godot physically reserves immutable strips and sends `playback.reserve`
   with the source identity, world origin, stream generation and a
   sampled **physical travel** witness. It never supplies a chosen
   musical deadline. Python validates source, timing and count-in
   constraints and returns its exact bound reservation receipt.
4. Godot verifies that receipt against its immutable physical arm,
   binds the returned segment and calls `playback.present`. Python
   authorizes the exact musical deadline, with lost replies reconciled
   from its read-only ledger instead of guessed or re-scheduled.
5. Notation, MIDI input, metronome, voice and Listen sound consume the same
   authorized take/segment. A preloaded renderer is promoted after authorization.

The musical worker advances deadlines independently of snapshot polling.
Untimed Free has a separate guided segment on the same renderer and holds its
target at the playhead; it has no timed grading deadline. The explicit
Python/headless adapter is not rendered-notation evidence and is never selected
as desktop admission. Its `score_queue_next` projection is not a graphical
playback route.

For an automatic same-source Practice Flow repeat, `fixed_deadline_ms` is the
outgoing sounding end plus **one upcoming authored bar at the next attempt's
BPM**. The already selected count-in origin remains fixed; admission consumes
the lead that remains instead of restarting a full bar. The gateway reserves
that exact world/deadline pair and rejects collision with irreversible active
ink. It cannot add fresh snapshot latency or an offscreen runway to move the
deadline. This exact-repeat route may trim only display context; generic fresh
source reservations still require a complete authored count-in bar.

### Pause and failure

An ordinary timed take receives a complete authored count-in bar. Pausing in
count-in may reuse its remaining part only if the exact admitted opening is
still safely ahead; otherwise another full bar is required. Pausing a played
take preserves its recorder and frozen musical elapsed time. Key releases
during pause/lead remain paired and do not count the paused interval as a hold.
The resumed partial take cannot grade until its admitted opening arrives.

An initial first attack may use the canonical onset allowance before its
deadline. MidiIngress alone admits that input; Recorder preserves its signed
musical timestamp. Resume reading lead still suppresses new grading. A second
Pause during that lead keeps the existing frozen source position.

Stale, expired or infeasible receipts never start grading or audio. A worker
timeout can lose a reply after commit: query `playback.status` before retrying
or withdrawing. Presentation is idempotent by segment identity. Missing bound
ink raises `TAKE_WITHOUT_SCORE` through `playback.failure` and stops the take.
Stop, navigation and source-generation changes invalidate pending work.

Settlement retains the original performed BPM, assessment, selected successor
and source identity. Evidence, progress and generator feedback commit together
under the existing lock/savepoint. A failure restores in-memory state; retry
reuses the same sealed evidence and receipt without regrading or awarding twice.
Incomplete capture is interrupted/censored, never manufactured into mastery.

## Immutable score stream

Retained command-buffer generations identify both geometry changes and
admission-time source crops. ScoreAssetSession publishes the completed
generation together with its readiness status; a ready getter cannot outrun
the corresponding overlay update.

Each logical take is a sequence of adjoining source strips at authored measure
boundaries, with one take identity. Printed cut points are source beats;
header/terminal margins use staff-space units. Once admitted, source range,
world origin and geometry are immutable. Retained layers share those facts;
they are not another source ledger.

There are two removal directions:

- Retire completely departed strips from the front, oldest first.
- Withdraw only the maximal safe, never-exposed suffix from the back. A visible
  strip is irreversible even if later strips belong to the same take.

Replacement is preflighted before mutation. A failed reservation compensates
its own provisional suffix without repainting earlier ink. Resume may reuse
the exact interval if safe; otherwise it retains the first paused source strip
and appends behind that irreversible prefix. Later unseen measures remain
eligible for withdrawal. The new copy explicitly binds its paused predecessor
to the same transport without changing either copy's geometry or identity.
Every incoming renderer checks all still-live outgoing
layers. Different densities cannot overlap printed music.

When Retry needs a complete leading preparation rest, that prefix is admitted
in the same immutable batch and take owner as its source. Stable
before/source/after slot identities distinguish the leading rest, music and
following rest through FIFO retirement, archive reuse and rollback. A
provisional prefix stays hidden until authorization; it cannot become a
separately inserted rest or move the exact automatic-repeat deadline.

The offline FIFO contains available reusable source plans. Its separate
append-only JSONL journal records checksummed enqueue, withdrawal, completion
and reset events under `user://score-stream-journal`, keyed by musical content.
The event is flushed before destructive removal. A failed append blocks that
operation and preserves live bindings and CanvasItems. Reuse materializes a
matching archived plan in a new future owner; it never restores obsolete world
coordinates or consumes an archive entry after a failed enqueue.

## Authentic notation and feedback

Every authentic atlas is extracted from the same complete parsed notation
document. Active performance and bounded display projections cannot remove
context or carry-in chord/tuplet inventory before asset extraction.

Verovio supplies authentic glyphs and composite note/chord artwork. Native
layout maps source identities to retained ink; there is no page-image fallback
or alternate score painter. When internal source notation carries expression,
the compiler preserves the original XML and projects surviving articulations,
ornaments, technical marks and lyrics onto the first generated source attack.
Staff-specific directions keep their hand and offsets without advancing the
timing cursor. Slurs require surviving endpoints in the same hand; ambiguous
unstaffed directions and missing endpoints are not invented. Ties/tuplets are
respelled from the variant's actual durations rather than blindly copied.
Unsupported expression cannot be claimed as natively drawn merely because
internal XML preserved it. Tied continuations do not invent new attacks or
repeat fingering.

Note feedback has one acknowledged channel, `feedback.events`, carrying
sequence, fingerprint, revision, transport, mode and graded facts. The backend
retains unacknowledged events; Godot processes each event before acknowledging.
Gaps/overflow are errors. New-revision events may wait for their exact renderer;
an unrelated current snapshot cannot relabel them. Preview and Listen never
award grades or mastery.

Provisional attack/release observations may appear before authoritative
assessment. `Recorder` alone pairs physical presses/releases, including
overlapping same-pitch keys. `LiveInputView` retains held/recent keyboard facts;
it has no matcher, used-note set or release ledger. Live and final scoring use
the same canonical assignment and shared observations. Live observation
construction is bounded to a two-bar display scope while matching retains full
canonical assignment; strict source projection is O(N + M), with direct source
head lookup rather than per-mark phrase/glyph scans. Elapsed live grading uses
the frozen musical clock during Pause and the resumed reading lead.

Every current canonical assessment snapshot replaces the provisional dimensions
for its source head. `final: true` locks the completed result. A revised local
assignment emits a `pending` withdrawal for its old provisional head; bounded
scope changes preserve older exposed ink rather than erase it. The
ledger preserves independent pitch/onset/release dimensions even when the
product shows only green/red. Records belong to physical take + engraved-note
instances; tied heads inherit the original attack's result. Status masks use
the same authentic head artwork inside its retained strip clip, repainting on
ledger changes rather than on every scrolling frame. Wrong-note ghosts and
Listen lighting are presentation facts, not extra graded source notes. Future
tied heads inherit the attack colour only when the canonical source beat reaches
their continuation. Free feedback uses the same canonical physical take key;
it cannot colour an unrelated future copy of the passage.

The backend carries the persisted `grade_note_holds` choice through the
fixed and tempo-mapped assessment policies into live grading and final settlement.
Feedback events use `release_advisory` as its inverse. With the default off,
correct pitch and onset earn green ink and clean passes regardless of the
physical key release; measurements are still retained. With the setting on,
short, long or unreleased keys are errors and prevent clean Practice Flow passes.
Captured rule identity includes the preference, and switching it cancels the
active attempt rather than reinterpreting existing evidence. Signed wrong-key ghosts use their real musical beat and
the same physical strip/header clip; they cannot enlarge exposed score bounds.

## Native protocol and workers

[PianoNative](../native/) exposes typed operation + JSON requests and raw PCM
audio through an in-memory queue. Internal statuses are success/invalid/unknown/
failed; no URL, socket or network adapter is involved.
[EngineCommands](../piano_teacher/inprocess.py) dispatches the operations.

One native command/tick worker owns command execution and bounded monotonic
wakeups. A separate asset/read-only worker handles cold engraving and statistics
so they cannot block musical ticks. `ScoreArtifacts` serializes engraving then
model publication outside the engine lock. The Python GIL is held while invoking
Python; native condition variables wait without spinning. Godot receives
callbacks on its main thread. Statistics capture bounded read-only WAL snapshots
and never acquire the musical lock or write another history.

Detached snapshots carry explicit facts/read ports; they cannot mutate the live
plan, recorder, renderer or clock. Source/fingering installation similarly uses
an immutable generation/fingerprint/original-notes identity and a validated
install effect; a late correction cannot replace another source.

## PracticeEngine decomposition: original design and implemented boundaries — 2026-11-21

The active [S0–S7 plan](../ROADMAP.md#practiceengine-architecture-replacement-implementation-and-acceptance-2026-11-21)
supersedes treating the oversized `server.py` facade as mere deferred
file cleanup. At the historical `f8bd9cd` baseline the facade contained
2,783 lines, 168 methods and 151,578 bytes. The initial target architecture
below documents the **design rationale**; its implemented services and
source evidence are mapped in
[Current embedded Python application boundaries](#current-embedded-python-application-boundaries-2026-11-21).
This is no longer an unimplemented proposal.

**New architectural layers and boundaries are allowed and may replace
existing ones.** The only architectural constraints are those needed for
correct product behaviour and clear dependency ownership: one actual
lesson/tempo selection, source identity, musical grading clock, admitted
playback authority, canonical notation stream and durable assessment result.
These constraints do not prohibit a new application-service layer, explicit
workflow engines, interface/port layers, an effect-dispatch boundary,
transaction coordinator or immutable snapshot types. Determine their value
from the responsibility inventory and dependency direction, not from the
current class inventory.

The target dependency direction is:

```text
Godot / EngineCommands / native workers
                |
       PracticeEngine entry boundary
                |
        application use cases
    / source  lesson  playback  outcome  read /
                |
    domain state, decisions and policies
                |
       explicit ports / infrastructure
```

The illustration is provisional. Phase S0 must confirm all method and state
ownership and decide the concrete type/module graph. A command coordinator
may orchestrate multiple owners under a documented transaction; it may not
acquire its own competing score queue, MIDI grader, transport clock or
lesson-decision policy. Pure domain modules must not import the facade;
services must not hold a universal mutable `PracticeEngine` reference.
New interfaces should correspond to real dependency seams, not merely
increase layer count.

Initial production migration moves source identity/revision into
`application/source_identity.py`, selected opening/course flag into
`application/lesson_cursor.py`, learner-facing messages into
`application/session_notices.py`, and active remedial assignment into
`AttemptRuntime`. The selected plan lives with its source identity,
the visual transport owns scheduling/rest metadata, and SessionCommands
owns its command reason. The full workflow and transaction decomposition is
still open; these new owners do not establish phase completion.

Native future-stage preload selection and exact-revision acknowledgment
now live in `application/score_preload_workflow.py`. A feedback release
uses only the preloaded source selected by TeachingContinuation, and a
failing next asset stays source-bound.

Source-bound live note observations and acknowledgement identity now use
`application/live_feedback_workflows.py`. It invokes the sole configured
assessment policy and the existing live publisher; it contains no
second used-note matcher or independent musical clock.

Score-state snapshots and exact graphical or explicit headless fixture
projection now use `application/session_read_models.py`. It owns only
the read side; command/worker transitions cannot be induced by polling.

Score selection, current artifact geometry, cached completed-take layouts,
guided marks and overview now use `application/score_read_services.py`,
which resolves the promoted artifact owner through the registry. Cold
native engraving continues outside the application lock.

History-management transactions now reside in
`application/history_management.py`: scoped evidence reset, learner deletion,
lesson reset, history reads and export. It consumes the installed
source/plan identity and `SessionLifecycle` rather than holding a
`PracticeEngine` reference. The external public methods remain locked
entry points. Source installation and fingering correction now live in
`application/source_workflows.py`. Preparation is outside the short
application lock, installation is inside it, and course-entry effects
remain in the facade transaction until S3. Settings and current-policy selection now live in
`application/settings_workflows.py` and
`application/policy_registry.py`. A saved preference change updates the
one current grading/diagnosis instance, while source/transport and read
consumers resolve that same instance; no stale policy reference is
captured at service construction. Device connection lifecycle and calibration now live in
`application/device_workflows.py`, which emits explicit setting changes
rather than calling the engine or mutating configured policies itself.
The short facade entry preserves source interruption ordering and locking.

Native MIDI callback handling, corrected source/transport facts,
device hot-plug and keyboard shortcut dispatch now reside in
`application/midi_application_input.py`. The existing MidiIngress
continues to own physical observation admission and Recorder remains
the one note pairing authority.

Public native/user commands, course-stage controls, state acknowledgement
and committed playback receipts now use `application/practice_controls.py`.
The facade retains the public `control` operation; the command router
uses source-bound services and keeps the existing application lock.
It does not acquire an independent take-admission policy.

Authorized timed take execution, continuation, Pause/Resume and Listen
readiness now use `application/timed_playback.py`. Its return from
Resume carries deferred score readiness to the command boundary, so
the playback service never re-enters the entire engine.

Source-bound count-in, musical-rate projection, rest geometry,
forward visual motion and playback admission facts now live in
`application/transport_timing.py`, which holds no extra clock
epoch and makes no curriculum decision.

The selected musical worker's tick, evidence finalization, take completion
and non-grading course handoffs now execute through
`application/practice_timeline.py`. It calls the existing playback,
graded assessment and source owners rather than implementing a competing
clock, selection or scorer. Bounded re-entry remains to be audited.

Exact post-settlement feedback and typed continuation dispatch now
belong to `application/completion_continuations.py`. The selected
next source and admission deadline come from existing authoritative
course and playback owners, not a second continuation policy.

Recovery materialization, recorded boundary checks and automatic
remedial effects now use `application/recovery_workflows.py`, which
executes the existing configured assessment/recovery decisions and
uses the canonical source clock.

Committed full-passage assessment effects and bounded review return
operations now reside in `application/post_assessment_effects.py`.
It consumes the one sealed `AttemptSettlement` receipt, updates the
selected source/score registry, and never regrades a take or independently
chooses its successor.

The decision-building part of lesson orchestration now lives in
`application/teaching_workflows.py`. It gathers bound evidence and route
facts and applies exactly the generator's validated decision. It does not
create another stage-selection policy or hold an engine backreference.
Exposure selection and materialization use
`application/exposure_workflows.py`; selected-effect installation uses
`application/exposure_installer.py`. Exact guided evidence facts are
assembled by `application/session_evidence_context.py`, and the installer
does not re-decide the lesson. Course entry, guided completion, navigation and original measure
selection now execute inside `application/lesson_execution.py`.
It uses the registered teaching decision and persisted source state
rather than introducing another curriculum selection policy.

The final shutdown path shares `SessionLifecycle` and retains the
evidence-close, MIDI-select-close and database-close ordering exactly.
No shutdown workflow calls back into the engine.

The active-take stop transaction now resides in
`application/session_lifecycle.py`. The stop workflow owns ordered
authorization invalidation, evidence interruption, cancellation and
per-owner resets, with explicit dependencies rather than a facade
backreference. The remaining command and source workflows are still
coordinated by `PracticeEngine`.

Identified high-risk state: `feedback`, `next_action`, selected source
window, `course_guided`, `score_revision`, scheduled starts, paused
source time, recovery and `_stop` lifecycle sequencing. Their concrete
writers, authoritative owners, derivations and explicit effects are S0/S1
deliverables. Later phases move complete source/history, lesson/exposure,
command/transport, settlement/recovery, read-model and score-presentation
workflows; each phase deletes the old implementation and migrates all callers.

The facade's approximate 300–450-line target is a **diagnostic goal, not
an architectural invariant**. Larger well-separated services or additional
layers are acceptable when coherent, whereas a 300-line facade that simply
forwards into another 2,000-line god object fails the goal. The present
ownership table above is an inventory of the *current* architecture and
can change as the S0–S7 plan is implemented. Existing graphical-admission,
read-only snapshot and musical-tick asset requirements remain binding.

### S0 responsibility inventory — implementation baseline 2026-11-21

Method-level audit on `75965fc6` identifies **180 methods
including public properties** after the initial state migration. The original
baseline contained 168 methods, before the explicit owner observation
properties were introduced. The following is a **complete migration map**,
not proof that the listed methods have already moved; final destinations may
become new classes or layers when the group dependencies are resolved.

| Intended responsibility | Current methods (name and source line) |
| --- | --- |
| S2: source/device/history | `_midi_lost` (383), `_present_midi_notice` (396), `ports` (405), `connect` (419), `hardware_diagnostics` (432), `hardware_diagnostics_action` (436) |
| ↳ | `library_listing` (440), `library_health_status` (444), `start_library_health` (447), `midi_calibration_action` (450), `preferences` (472), `_learning_context` (476) |
| ↳ | `learning_history_status` (489), `learning_statistics` (494), `_retry_context` (498), `export_learning_history` (530), `delete_piece_history` (536), `delete_learner_history` (559) |
| ↳ | `close` (586), `set_preferences` (596), `_active_tempo_map` (641), `_elapsed_beat` (652), `_elapsed_seconds` (657), `exercise_diagnostics` (661) |
| ↳ | `load_library` (672), `performance_diagnostics` (691), `load` (746), `fingering_status` (783), `correct_fingering` (788), `_restore` (814) |
| ↳ | `_save` (817), `_reset_current_path` (820), `_poll_midi_connection` (1938) |
| S3: lesson/exposure | `_learner_saved` (864), `_guided_unit` (868), `_save_guided_preparation` (872), `_learner_snapshot` (902), `_enter_selected_exposure` (907), `_flow_active` (920) |
| ↳ | `flow` (924), `_flow_stage_entry` (927), `_flow_execute` (930), `_flow_open` (944), `_flow_say` (953), `_flow_state` (956) |
| ↳ | `_begin_course_stage` (959), `_skip_stage` (966), `_place_original` (976), `_valid_trouble_spots` (990), `_revisit_trouble` (994), `_reset_trouble` (1009) |
| ↳ | `display_phrase` (1012), `_begin_learn` (1019), `_exposure_source` (1035), `_apply_exposure_preparation` (1042), `_prepare_practice` (1100), `_apply_listen_failure` (1117) |
| ↳ | `_prepare_listen` (1124), `demo_audio` (1132), `_start_listen_if_ready` (1136), `_prepare_perform` (1146), `_review_retry` (1164), `_practice_weak` (1176) |
| ↳ | `_seek_grid` (1186), `_seek` (1195), `_teaching_binding` (1214), `_prepare_teaching` (1220), `_manual_effect` (1265), `_install_command` (1269) |
| ↳ | `_control_listening` (1583), `_control_learning` (1601), `_change_stage` (1899), `_open_take` (2448) |
| S4: command/playback | `require_presentation` (321), `playback_status` (325), `reserve_playback` (329), `present_playback` (333), `withdraw_playback` (339), `report_playback_failure` (343) |
| ↳ | `_playback_facts` (348), `_request_playback` (370), `_abort_playback` (374), `_on_playback_failure` (377), `_receive` (694), `_midi_transport_facts` (702) |
| ↳ | `_apply_midi_shortcut` (718), `_receive_message` (726), `_stop` (858), `_presentation_bpm` (1279), `start` (1325), `_commit_playback_intent` (1378) |
| ↳ | `_next_count_in` (1406), `_next_count_in_beats` (1418), `_next_count_in_meter` (1421), `_continue_at` (1424), `_collect_continuation_measurement` (1449), `_start_rate_bpm` (1464) |
| ↳ | `_schedule_preparation` (1471), `_visual_motion` (1481), `control` (1490), `_dispatch_control` (1519), `_control_acknowledgement` (1550), `_update_short_rest` (1642) |
| ↳ | `_collect_rest_measurement` (1660), `_update_continuous_horizon` (1688), `_presentation_lead` (1696), `_control_transport` (1709), `_open_selected_measure` (1780), `_start_or_restart` (1795) |
| ↳ | `_musical_seconds` (1851), `_pause_current_session` (1863), `_resume_current_session` (1871), `_update` (2340), `_update_transition` (2361), `advance_clock` (2501) |
| S5: outcome | `_apply_policy_response` (504), `_performance_review` (1154), `_commit_pending` (1285), `_decided_stage_selection` (1948), `_advance_pending_feedback` (1954), `_publish_feedback_fault` (1986) |
| ↳ | `_dispatch_continuation_effect` (1990), `_start_remedial_assignment` (2012), `_apply_rolling_recovery` (2042), `_complete_attempt` (2106), `_finish_performance_review` (2188), `_finish_section_review` (2194) |
| ↳ | `_finish_partial_recovery` (2206), `_finish_full_passage` (2219), `_assess_rolling_boundary` (2255), `_run_pre_assessment_transition` (2282) |
| S6: projection/read | `_guided_marks` (1091), `_phase` (2417), `_layout_for_completed_take` (2436), `_feedback_take` (2452), `_publish_live_assessment` (2461), `_live_marks_for_snapshot` (2481) |
| ↳ | `_live_feedback` (2485), `_score_projection_facts` (2548), `_prepare_score_presentation` (2579), `_state_snapshot` (2588), `_capture_session_snapshot` (2647), `_next_stage_selection` (2720) |
| ↳ | `next_stage_score` (2728), `report_preload_failure` (2733), `acknowledge_preloaded_stage` (2740), `_score_selection` (2756), `_source_model` (2768), `_selected_artifacts` (2772) |
| ↳ | `semantic_score` (2783), `engraving` (2787), `geometry` (2791), `lesson_overview` (2796) |
| S7: facade/public projection | `plan` (117), `source` (121), `is_builtin_warmup` (125), `fingerprint` (129), `score_revision` (133), `open_from_beat` (137) |
| ↳ | `course_guided` (141), `feedback` (145), `feedback` (149), `next_action` (153), `next_action` (157), `_remediation_active` (161) |
| ↳ | `teaching` (166), `persistent_hints` (170), `running` (175), `mode` (179), `auto` (183), `preview_only` (187) |
| ↳ | `transport_id` (191), `count_in_beats` (195), `count_in_bar_beats` (199), `count_in_meter` (203), `awaiting_score_revision` (207), `pause_context` (211) |
| ↳ | `__init__` (214), `state` (2530), `poll_state` (2541) |

The proposed domain/state dependency ownership is:

| Fact or operation | Single authoritative owner / planned boundary |
| --- | --- |
| Loaded source, `LearningPlan`, source fingerprint and published revision | `SourceIdentity` (now), prepared/install effects in S2 |
| Selected opening and course-guided designation | `LessonCursor` (now); S3 manages semantic transitions |
| Learner-facing feedback and suggested action | `SessionNotices` (now); policy produces facts, presentation consumes them |
| Active remedial assignment, recording, review and recovery flags | `AttemptRuntime` and teaching decisions |
| Current audio/MIDI transport lifetime, count-in and mode | `PlaybackSession`; physical admission in `PlaybackCoordinator` |
| Forward view epoch, continuation rest and rendering runway | `VisualTransport`; native score admission owns physical ink |
| Command reason, selected manual effects and application provenance | `SessionCommands` |
| Assessment and lasting result | `AssessmentService`, `AttemptSettlement`, `LearningCapture` |
| Asynchronous source and asset work | `SourcePreparationSession`, `ScoreArtifacts`, native asset worker |
| Graded command/tick transaction | New/updated S4 application executor; not snapshot reads |
| Cross-workflow completion/return effects | New/updated S5 effect/settlement orchestrator; no shadow selector |
| Read models and score projections | S6 projection boundary using immutable `SnapshotValues` and named read ports |

**Cycle and ordering evidence.** The major method-call strongly connected
groups in the current facade are: `control` /
`_dispatch_control` / `_control_transport` /
`_resume_current_session` (command re-entry);
`_update` / `_update_transition` / `_complete_attempt` /
`_run_pre_assessment_transition` / `_finish_full_passage`
(automatic completion); and `_flow_execute` / `_begin_learn`
(course re-entry). S3–S5 must explicitly resolve those cycles by accepted
commands and ordered effects rather than moving them into mutually
referencing coordinator classes. The planned dependency graph in the
preceding section is the design baseline; the concrete port contracts and
transaction implementations are S1–S5 deliverables.

**Migration rule:** All 180 inventoried names must be
accounted for after S7 as moved code, intentional public wrappers, or
demonstrably unused/deleted methods. Public in-process operations must
retain their contract. User-state migrations and the headless fixture adapter
remain only where needed for supported behaviour.

## Remaining work — source audit 2026-11-20

Historical discovery findings and original source evidence follow. A1–A6 now
have production-code corrections; the table is not a list of unimplemented work.

Implementation ledger (main, starting at `82bf06bb`):

- A1 implemented: admission compares the prepared model with both canonical
  `practice_timeline` bounds, then compares the intent with its sounding bound.
  No second duration field, truncated release or changed authored API.
  Existing desktop/timeline Python checks and all native checks pass
  (`architecture-a1-ci.log`); a direct Godot gateway diagnostic accepts the
  4-authored/6-sounding range and rejects mismatched prepared assets.
  Physical rendering remains unverified. Commit: `96c895e7`.
- A2 implemented: pool reseeding is allowed only before stream binding;
  growth initializes new capacity without rewriting admitted crops. Once ink
  is committed, engraving preserves its gap and safe horizontal boundaries
  through resize while rebuilding vertical placement. Existing native checks
  and 14 desktop/timeline tests pass (`architecture-a2-ci.log`); the actual
  controller/Resume/pool diagnostic preserves each bound source crop during
  pool growth. Physical resize appearance remains unverified.
- A2 commit: `0d959470`.
- A3 implemented: exposure/review/retry, settlement publication, guided return,
  recording suspension and preparation transitions use their existing owners.
  Manual command scopes use SessionCommands' context manager; obsolete Engine
  teaching/hint setters and redundant stop resets are removed. Calibration
  reset and assistance capture also mutate inside their owners. All existing
  Python behaviour checks pass: 107 passed, one optional system-SF2 skip
  (`architecture-a3-ci.log`).
- A3 commit: `e7b10962`.
- A4 implemented: snapshots sample one instant without executing transitions.
  Teaching and calibration reads are passive; their worker/command operations
  advance them. Guided presentation scheduling also moved out of serialization
  into the accepted command/tick boundary. Three existing behaviour cases now
  explicitly tick the worker instead of relying on obsolete poll advancement.
  Full CI script passes: 107 Python tests, one optional system-SF2 skip,
  parser and four native groups (`architecture-a4-ci-final.log`).
- A4 commit: `1507b427`.
- A5 implemented: immutable lesson contracts and the shared source-attack
  index sit below curriculum policies. Composers receive explicit contributors;
  Practice Flow uses their feedback contracts without importing the registry.
  Statistics share pure evidence/numerical operations, and tuplet recovery
  receives the authentic extractor as an explicit operation. No algorithms
  or supported strategies were removed. All 107 Python checks pass (one
  optional system-SF2 skip; `architecture-a5-ci.log`). The one-off runtime
  import scan, including deferred imports and excluding TYPE_CHECKING-only
  edges, reports zero cycles (`architecture-a5-imports.log`). This diagnostic
  is not a new architecture CI test.
- A5 commit: `f8daff77`.
- A6 implemented: admission/preloading query InProcessRequest's pending
  operation semantics. The private numeric ID stays inside its request owner.
  Repository-wide caller inspection removed unused native withdrawal/restore,
  receipt, append, direct-arm and empty-strip facades, their dead helpers,
  unused continuation prediction and the unused flow-rate compatibility port.
  Production admission still uses the existing two-phase executor. Full CI
  passes: 107 Python checks, one optional system-SF2 skip; parser and four
  native groups pass; coverage is 69.6% lines / 49.4% branches
  (`architecture-final-ci.log`). The first full run on `982d3fee` exposed acceptance scripts that still read
  the removed renderer `stream_passes` property. Commit `ad1055ac` uses
  a deep diagnostic snapshot from the canonical stream owner instead.
  Remote core and full native-production CI then passed on `ad1055ac`,
  run 44796955201, including real-score journeys and relocated package
  boot. Physical output acceptance remains unverified.

### Ownership and dependency follow-up — 2026-11-20

The follow-up review inspected engine snapshot construction, PlaybackSession,
VisualTransport, AttemptRuntime, AttemptSettlement, Godot admission, the retained
notation pool and its single queue. The engine delegates take and transport
lifecycle mutations, and snapshot reads do not execute the worker transition
loop. The native diagnostic returns a deep copy of the sole stream ledger and
does not restore mutable queue access.

A further dependency cleanup makes shared lesson focus, hand selection and
hybrid passage segmentation explicit public module ports. It moves bounded
authentic vector rasterization from tuplet extraction to
`notation/assets/vector_art.py`, consumed independently by beam and tuplet
extractors. Runtime/font resource initialization is similarly exposed through
public functions, instead of other extractors importing private helpers.
These changes preserve the existing algorithms; no new architecture, pixel
or infrastructure tests were introduced.

The review covers the critical production owners and the known dependency
clusters. It cannot prove absence of every possible defect. The refactored
source requires a new full CI run and physical acceptance remains separate.

### Musical-tick asset boundary — 2026-11-21

Completed-take feedback consumes the selected `ScoreArtifacts.cached_layout`
without cold engraving. If that layout is missing, the existing
`assess_completed_take` error boundary retains its canonical grading result,
reports the absent visual projection and skips unmapped ink. No Verovio
compilation may run from the locked transport tick. Pre-engraving and publication
remain owned by `ScoreArtifacts` and the asset worker.

### Legacy-dependency review — 2026-11-20

The production paths were checked against the current ownership table above.
The runtime has one in-process Godot–Python command transport, one backend
playback authorization owner, one native score/immutable FIFO and one musical
grading clock. The forward-scrolling visual timeline projects those authorized
epochs but cannot grade or admit MIDI.

Source-level findings and changes:

1. The old `score_queue_next` plan remains an explicit headless fixture
   projection in Python, now isolated in
   `application/headless_score_projection.py` (2026-11-21). The product
   `ScoreStatePublisher` publishes only admitted desktop intents and guided
   plans. `PracticeEngine` calls the headless adapter only when presentation
   is disabled. Godot diagnostics use the actual backend segment identity;
   no graphical score stream reads the compatibility projection.
2. Assessment ink rejects layouts without `source-note-v1` bindings.
   The former pitch/onset-nearest fallback has been removed; only the
   canonical note-to-head mapping can colour music.
3. Fixed-BPM and tempo-mapped recovery now have one reducer over already
   assessed wrong/missed notes. Their time conversions remain separate and
   use the same source grid; no additional scorer, progression state, or
   second recovery clock was introduced. Warm-ups retain their own bounded
   source window as before.
4. The obsolete, invisible coaching card and its standalone GDScript were
   removed. The current native ink/feedback and gameplay rail remain.
5. The old `score_loop_enabled` state field carried no actual loop authority:
   the base renderer used it only to gate practice-timeline validation and
   an otherwise redundant redraw. The validation now derives from accepted
   `mode == "practice"` and `kind != "perform"`; the Python/Godot
   state contract advances together to v4.
6. Unsupported authored expression classes continue to be recorded under
   `unrendered_expressions`. No complete-page or alternate renderer is
   available or selected. Native source fidelity is not silently claimed
   where an authentic glyph cannot be drawn.

The retained migrations in the library, progress repository and learning
ledger safeguard pre-upgrade saved data; they do not govern new lesson
decisions. The explicit headless adapter is restricted to no-presentation
testing. The development MCP toolkit is not enabled by the project and is
excluded from standalone package assembly.

This source audit, including the production Python/GDScript keyword and
caller inspection, is evidence about known paths, not a formal proof against
all dynamic interactions. At that historical audit revision, the main
`PracticeEngine` facade was 2,783 lines and declared 168 methods.
It was decomposed in the later S0–S7 work documented above; present sizes,
software gates and outstanding physical acceptance are reported separately in
the roadmap. No new tests or parallel services were added by the original
read-only audit.

Audited implementation: `640a77f5`. Read-only implementation review, a Python
import-graph inspection and an existing real-MIDI/public-command diagnostic
found the following remaining work. No production code or tests were changed
by this audit. Priority reflects demonstrated software consequences versus
structural debt; physical rendering and instrument acceptance remain separate.

| ID / priority | Remaining work and evidence | Required ownership outcome |
| --- | --- | --- |
| A1 / high | **Unify authored and sounding range contracts at admission.** [Python playback facts](../piano_teacher/server.py#L329) use the complete sounding endpoint; [lesson snapshots](../piano_teacher/application/lesson_snapshot.py#L29) publish authored duration. The [Godot admission guard](../godot/score_admission_gateway.gd#L111) incorrectly requires equality. An existing one-bar MIDI fixture with a held ending publishes 4 and 6 respectively, so that guard refuses admission. Accepted state reaches the gateway unchanged. | Carry both meanings explicitly from the selected source and validate prepared coverage against the correct endpoint. Keep the full release and the authored four-bar window limit. Never fix the disagreement by truncating the music. |
| A2 / high | **Preserve admitted source crops on resize.** [View resize](../godot/notation/native/view.gd#L213) calls [pool resize](../godot/notation/native/retained_notation_pool.gd#L65), which rewrites source windows by pool-array position. [Admission](../godot/notation/native/stream_lifecycle.gd#L122) assigns those same nodes the ledger's context/Resume-specific clips. Resizing can therefore recompile a different source interval under an unchanged admitted ledger record. This is a source-level mutation path, not a claimed visual reproduction. | Stream binding remains authoritative for each allocated node's crop. Pool growth/reflow must preserve bound windows and exposed geometry, and only prepare unbound capacity. |
| A3 / medium | **Finish lifecycle ownership transfers from the Python facade.** [Exposure installation](../piano_teacher/server.py#L1064) writes transport opening/rewind and attempt review fields directly. [Settlement publication](../piano_teacher/server.py#L1299) clears PlaybackSession's score wait; [transition execution](../piano_teacher/server.py#L2294) mutates the transport preparation dictionary and visual offset. [PlaybackSession](../piano_teacher/application/playback_session.py#L287) also clears AttemptRuntime fields directly. | Give VisualTransport, PlaybackSession, AttemptRuntime and GuidedSession semantic operations for their own lifecycle mutations. Keep the facade's lock/composition role without creating another state holder or moving the same field bag elsewhere. |
| A4 / medium | **Remove transition execution from snapshot reads.** [State serialization](../piano_teacher/server.py#L2545) calls the same mutating update as [the clock worker](../piano_teacher/server.py#L2507). This is one serialized clock, but two entry paths for grading, settlement, device polling and continuation side effects; the source explicitly retains a compatibility poll route. | The existing worker/command execution boundary advances transitions. Snapshot construction reads a frozen accepted state and cannot settle a take or start its successor. |
| A5 / medium | **Break deferred dependency cycles and private helper coupling.** [Statistics](../piano_teacher/learning_statistics.py#L285) imports its [metrics module](../piano_teacher/learning_statistics_metrics.py#L8), which imports private helpers back. [Tuplet extraction](../piano_teacher/notation/assets/tuplets.py#L460) calls [recovery](../piano_teacher/notation/assets/tuplet_recovery.py#L109), which imports the extractor back. Course/generator modules also form a deferred cycle; [PracticeWindow](../piano_teacher/practice_windows.py#L16) imports the alternate curriculum's private source index. Type-checking-only edges were excluded from these findings. There is no immediate top-level import failure. | Put shared source indexes/contracts below curriculum policies, and give statistics/tuplet recovery one-way dependencies. Preserve existing algorithms and avoid a duplicate matcher, planner or source index. |
| A6 / lower | **Close remaining private request-state access.** [Admission](../godot/score_admission_gateway.gd#L275) and [preloading](../godot/score_runway.gd#L303) repeatedly inspect [InProcessRequest's](../godot/inprocess_request.gd#L8) private pending ID to decide timeout/reconciliation/cancellation behaviour. | The request owner exposes pending/completion/cancellation semantics; callers do not depend on its storage representation. No current learner-visible failure was established for this item. |

Lower-priority cleanup: repository-wide caller inspection found unused native
mutation facades such as [append_source_take](../godot/notation/native/view.gd#L389)
and [arm_stream_take](../godot/notation/native/view.gd#L457). Review these against
the supported API, then remove obsolete internal admission/compensation paths
while keeping the existing executor as the sole production entry.

The earlier extraction is substantive: Main composes application sessions,
PracticeScreen separates chrome from interaction, glyph assets/masks are
separate, and ScoreStreamController delegates binding/recovery and retained
resource lifetime. This audit found no second production score ledger or
independent progression clock in those paths. File size alone does not justify
another extraction. Durable assessment/progress transactions already live in
AttemptSettlement; A3 concerns remaining lifecycle writers and publication.

Diagnostic evidence: `debug-sessions/practice-completion/architecture-range-probe.log`
records actual Python command values for A1. A2–A6 are source-review findings.
The prior passing CI/native/package record remains valid for its exercised
scenarios; it does not close these newly identified gaps. Address A1/A2 first,
then A3/A4, followed by A5/A6 and obsolete-port cleanup. Keep CI focused on
player behaviour rather than adding architecture-shape tests.

### MIDI-only source boundary — verified source review 2026-11-20

User source dispatch and persisted library selection both accept MIDI only.
The old MusicXML importer and direct source-annotation/fingering placement
parsers were deleted; two dangling imports and an obsolete authored-fingering
test were subsequently corrected. Internal generated MusicXML and the
authentic Verovio asset extraction pipeline remain part of the native view.

There is a single imported `Piece`, single immutable attack identity set and
one original MIDI measure grid. The preprocessing cache returns this `Piece`
directly, and `SourcePreparationSession` builds curriculum and fingering from
that same instance. It no longer carries a fictitious score alongside
`Piece` or installs an always-`None` `PracticeEngine.score`. The old alternate
music21-score branch in `render_layout` and its single-page SVG wrapper are
retired: the engraver accepts the native `LessonScore` exclusively. With
both external source import and music21 page conversion removed, the
`music21` package requirement and its verification checks are also retired.

Original MusicXML inventory parsing retained under `research/coda_*`
supports independent comparisons of Coda's symbolic notation ideas. Those
research tools are not the desktop input seam, own no playback or grading
clock, and cannot inject source pages into the active application. Do not
advertise this separate research capability as a user import format.

160 Python application modules were inspected for deleted-module imports
and stale `source_musicxml` uses; no remaining application reference was
found outside the isolated research adapters. The subsequent source-only
dependency and engraver cleanup passed combined core, native source journeys
and a relocated package boot on `23dd5649` (GitHub Actions run
44836313449). Physical MIDI/audio/visual acceptance is still separate.

Architecture review and software execution are distinct from physical acceptance.
See [development](development.md#verification-and-acceptance) and the dated
[roadmap](../ROADMAP.md) for what was actually checked on each revision.

---

## Current boundary notes (2026-11-22)

**Frozen Resume:** The visible clock holds during Pause. Native score
admission must therefore use `resume_fresh` for a backend-owned new
full-bar slot while preserving the existing unexpired paused strip.
The original paused world's count-in deadline is no longer physically
feasible after an asynchronous reserve/present transaction; no component
is permitted to move that ink to manufacture reuse. The renderer owns
preflight geometry and immutable enqueue; Python owns the one selected
absolute deadline and the grading/transport commitment. Grading cannot
resume before successful physical attestation.

**Terminal admission:** A bounded failed admission is included in
`playback_timeline` for the same snapshot used to project enabled controls.
Failure rendering is driven by that result rather than stale `phase=loading`.
No UI component can grant a retry after Python has exhausted the source's
attempt budget.

## Production practice transition and ownership ledger

This ledger is a **source-level dependency and transition audit** for the
default practice-flow contract in [practice-flow.md](practice-flow.md).
It documents the actual Python/Godot production path, with separate
acceptance gates. Its date is 2026-11-21; do not treat a source-owner
mapping as hardware verification.

### Non-overlapping responsibilities

| Invariant or decision | Sole production owner | Native reader/adapter | Prohibited alternative |
| --- | --- | --- | --- |
| Selected piece, revision, measure window and hand | `SourceIdentity` / `LessonExecution` and generator-approved `TeachingDecisions` | `PracticeScreen` and `ScoreAssetSession` | Godot selecting a neighboring practice measure |
| Listen → Free → Tempo, next window/hand and Coda/Fukuda eligibility | `practice_flow`, `TeachingDecisions`, `LessonExecution` | `PracticePresentationSession` and `PracticeChrome` | UI phase-string transition choices |
| Accepted screen/MIDI shortcut action and navigation effects | `control_projection`, locked `PracticeControls` | `ApplicationInputSession`, `PracticeCommandCoordinator`, `CommandSuccessPolicy` | Godot turning a stale button label into Start or Retry |
| Graded and audible musical origin, count-in, exact retry/fixed deadline | `PlaybackCoordinator`, `MusicalScheduler`, `TransportActions` | `ScoreAdmissionGateway` and `MetronomeFrameCoordinator` | Native musical scheduling or alternate countdown clock |
| Sampled immutable source/clip, queue positions, notes strictly in future, suffix retraction | `ScoreStreamQueue`, `ScoreStreamController`, `StreamTakeBinding`, `StreamAdmissionExecutor` | `ScoreAdmissionGateway`, `ScoreRunway` | Python mutating pixels or UI holding an alternate stream |
| Presentation world and authored tempo-map projection | `PresentationTimeline` / `ContinuousScoreFlow` | Native score view/frame adapters | Separate presentation clocks for count-in or Free |
| Semantic Free target, Pause, unready idle, and pending successor motion directive | `ScoreStatePublisher` | `GuidedPresentationSession` only maps target beats to world | Native teaching-phase/expected-note progression |
| MIDI on/off grading, marks, hold and timing policy | `MidiIngress`, `AttemptSettlement` and authoritative assessment | GDExtension input port, `PracticeFeedbackSession` and view effects | Local Godot verdicts, mastery or strike counts |
| Durable attempts, review progress and saved reopen | `LearningLedger` and `LearnerProgress` | Library/lesson screens present accepted results | Godot persistence or implied mastery |
| Full immutable state projection and schema | `SessionReadModels`, `state_projection`, `state_contract.VERSION=5` | `ApplicationStateInbox` | Side-effecting reads, unversioned fallback fields |

The native bridge is `PianoNative` → `inprocess_bus.gd` →
`EngineCommands`, not an HTTP endpoint. Every playback admission
operation is executed on the embedded worker under the application lock.

### Ordered transition/acknowledgement matrix

| Event / prerequisite | Authoritative transition | Cross-boundary receipt / observable state | Failure or non-progress |
| --- | --- | --- | --- |
| Library opens a selected MIDI | `library.open` → `SourceIdentity`, `LessonExecution` | source fingerprint, revision, window, complete sounding tail and one Listen exposure | missing/repaired metadata reported; prior source invalidated |
| Real source fully engraved | `score_ready` acknowledgement → `TransportActions.control_acknowledgement` | same revision; selected score/tempo map, `playback_intent` when timed | stale asset revision rejected; no grading before source |
| Listen / start gesture | `PracticeControls` resolves UI intent → `TransportActions` → `PlaybackCoordinator.request` | `intent_id`, attempt, source and earliest deadline | unavailable controls have non-executed outcome; no clock without authorization |
| Native physical admission | `ScoreTransportReservation` previews, `StreamAdmissionExecutor` arms immutable source; `PlaybackCoordinator.reserve` authenticates physical witness | source/queue generations, exact world and one reservation receipt | wrong source, impossible clearance, stale witness, fixed-deadline overlap rejected |
| Audible/graded playback begins | `playback.present` → `PlaybackCoordinator` commits the one transport | authorized segment, transport ID, downbeat, meter, count-in and audio epoch | expired count-in, mismatched segment/renderer or partial failed commit stops/fails |
| Lost reserve ACK | `playback.status` returns original physical witness | native confirms same intent, take, attempt, queue generation and timestamp; only then binds it | conflict retracts provisional ink; prior active take remains |
| Lost present ACK | `playback.status` / authorized state poll identifies active segment and take | native physically attests still-present source, promotes staged renderer once | absent source reports `playback.failure`; never guesses an authorized take |
| Count-in / Pause / Resume | `TransportActions` requests Pause or Resume; `PlaybackCoordinator` authorizes the resumed take | backend `presentation_directive` frozen/retain/run, source-bound metronome, MIDI grading window | pending Resume cannot unfreeze painted ink; pause retains source |
| Listen completes | `PracticeTimeline`, `LessonExecution` apply accepted practice-flow transition | complete window Free target, backend guided plan source identity | score not ready/paused/incorrect MIDI cannot grant credit |
| Free expected note | `GuidedSession` records actual MIDI; `ScoreStatePublisher` publishes next target | guided plan and `presentation_directive=target`, authentic note feedback | wrong, absent or partial chord retains target; no timed grading |
| Free completes → Tempo | `LessonExecution` selects original notes at starting rung | new timed intent at selected window and hand, native physical source ACK | no notes outside selected measure window admitted |
| Tempo take completes | `AttemptSettlement` evaluates all attacks/extras/releases according to configured policy | accepted clean/fail verdict, persisted evidence | missing/wrong/early/late or optional hold failure blocks clean credit |
| Clean below target | `AttemptProgression` chooses next tempo from target-rung ladder | fixed repeat at full outgoing-time rest, incoming tempo only at new downbeat | physically impossible exact repeat retired, not shifted |
| Failed attempt, repeated floor failure | `TeachingDecisions` chooses same/slower Tempo or return to Free | attempts/streak counters, next source and backend message | messages never alter musical deadline; source/window identity preserved |
| Second floor return | `TeachingDecisions` applies source-safe simplification only if eligible | named changed exercise and durable per-window/hand evidence | no eligible aid: original Free remains; no fabricated original mastery |
| Window/hand mastery | `LessonExecution` selects next original window/hand | one measure alone, then trailing windows up to four; completed hand evidence | empty hand skipped; window progression cannot display neighbors |
| Whole-piece final | `practice_flow` chooses full authentic source, both hands | final-stage identity, two clean target passes and durable record | never infers mastery from simplified or ungraded input |
| Reopen progress | `LearningLedger` / `LessonExecution` restore same window at Free | valid source revision and saved staged progress | partial chord/held key cannot become completed learning |
| Source change during admission | `PlaybackCoordinator.invalidate` / `cancel_pending` | old intent/receipt invalid; native verifies latest fingerprint/revision | no old async callback may present or promote new ink |
| Physical source disappears during active take | native watchdog reports take/segment; `PlaybackCoordinator.fail` decides transport stop | recorded source failure and recoverable visible reason | no unscored/audio-only take; four-frame native grace currently used |

### Native physical admission invariants

A provisional score arm cannot grade MIDI. The backend receipt is
source/attempt/queue-bound, and the native controller must prove that
the same arm still exists before `playback.present` can authorize it.
After authorization the queue may only discard expired head ink or
retract an unexposed maximal future suffix. Future source placements
are immutable. Automatic exact repeats can neither move the deadline
nor print a second rest. The complete sounding tail and closing
barline belong to the selected authored window; additional neighboring
bars may inform internal engraving, not the printed exercise.

**Current software ownership (2026-11-22):** The renderer performs a
read-only physical feasibility preview and reports source/queue identity,
world origin and measured travel. Python's `PlaybackCoordinator` and
`MusicalScheduler` choose the one downbeat before notation is armed. The
native queue then commits the exact authorized placement and attests the
same physical source before grading or sound. A frozen Pause has a stationary physical source world and cannot
retime its already-printed count-in to a later asynchronous reservation.
The native `resume_fresh` route keeps the paused source's unexpired
physical strip immutable, admits new source ink at a backend-selected
future full-bar countdown, and reports that exact queue commit before
transport resumes. The Python transport identity and saved lesson state
remain continuous. The obsolete partial-count-in reuse, receipt flag and paused-origin
selection have now been removed from both backend and native contracts;
a resumed transport preserves the musical take but always needs a fresh
full authored count-in. A terminal failed admission may retain an
older authorized segment for painting history; that history cannot
authorize further scrolling. The Python motion directive publishes
`hold` when the terminal ledger is `failed` or `idle`
without an active take. An admissible successor may still publish
`retain` so the previously authorized rest moves forward.
Lost acknowledgements retain fail-closed, source-bound recovery. The production MIDI corpus and physical piano
verification remain independent acceptance gates; ownership code is
not evidence that every native transition succeeds.

### Reproduction witnesses and acceptance gaps

| Witness | Actual observation | Corrective owner / status |
| --- | --- | --- |
| Missing Pause/Free visual hold, pending Resume deadlock | State changed but painting release/forecast was confused | backend directive, independent held-paint and hypothetical-geometry projection; core checks exist, native acceptance pending |
| Wrong/silent Free moved apparent target | Initial authorized Free ink had not finished reaching the playhead when wrong-note check began | production synthetic-MIDI journey now waits for actually stable printed Free target before injecting wrong MIDI, then measures wrong/silent hold; native outcome pending |
| Extra bars visible | Native pre-engraved neighboring context could leak beyond selected window | renderer clips only the current authenticated window; full-scene physical queue bound assertion added |
| Reservation reply dropped | Godot previously withdrew a physically armed source without checking Python ledger | read-only backend `playback.status.reservation` witness and exact native recovery |
| Original 40→48 BPM retry | Incoming tempo incorrectly shortened the *outgoing* printed rest; native queue reported overlap | `AttemptProgression` now clocks full authored rest at outgoing tempo; full native retest pending |
| Old direct command reply | Native-bridge smoke assumed flat response after `practice.command` introduced `{state,outcome}` | smoke now verifies command outcome before inspecting state; native retest pending |
| Active playback without native renderer | Watchdog checked wrong binding but omitted renderer absence | source-bound physical `playback.failure` reporting includes null/invalid renderers |
| Reopening saved work, final, simplifications | Backend unit/integration paths exist; full physical sequence not witnessed here | actual instrument and separate platform/installation gate open |

**Core evidence:** GitHub Actions 44956785207 passed on the
MIDI-shortcut source-ownership revision. Full native-production
includes real Godot 4.7.2, embedded CPython, a synthetic hardware
MIDI port, production score view, original Moonlight/Peace Piece/Chopin
sources and a relocated package boot. It is **not** a substitute
for a physical Kawai CA49, audio/speaker test, clean second machine
or a full source-specific Pathétique acceptance.

Any change to this matrix should be paired with a real-path scenario
and an actual CI/physical observation, not a test that duplicates
the lesson/transport policy.
