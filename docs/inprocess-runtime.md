# Embedded runtime

Technical contract only. The [current owner map](architecture/system.md)
describes source responsibilities; [ROADMAP.md](../ROADMAP.md) records phases.

Piano Teacher is a **single Godot process** using a CPython interpreter
inside a C++ Godot 4.7 GDExtension. There is no alternate application
runtime, HTTP service, UDP listener or port binding.

## Ownership

- Godot owns score painting, user actions, animation, metronome and Listen
  audio. Static Verovio beam texture slices, slur polygons, tie contours,
  chord order, note positions and expression/endings spans are prepared when
  the score/viewport changes. Frames only translate these prepared structures
  and draw visible marks. Source notation and automatic silence now live
  in retained `CanvasItem` command buffers. Repeated copies reuse pooled
  source/rest nodes positioned by transforms; recovery creates precompiled
  source/rest variants when its authored context changes. Fingering and
  transport effects remain on separate overlays. Score publication waits
  until all ordinary retained source/rest buffers have compiled. Current
  segments cover whole passages, so unusually long scores may still need
  finer spatial tiling and GPU/frame-time benchmarking.
  [SourcePassPainter](../godot/notation/native/source_pass_painter.gd) owns
  one-time authored composition; [RetainedNoteProjection](../godot/notation/native/retained_note_projection.gd)
  owns visible notehead indexing. [ScoreEngraving](../godot/notation/native/score_engraving.gd)
  owns layout/asset preparation and [ScorePainter](../godot/notation/native/score_painter.gd)
  owns native canvas composition. [NativeScoreView](../godot/notation/native/view.gd)
  supplies the canvas/lifecycle boundary; [ScoreStreamController](../godot/notation/native/score_stream_controller.gd)
  owns its mutable source/rest ledger and take/recovery collaborators. The source-copy pool
  is sized from the viewport and semantic stride rather than a fixed clone
  count. Fingering labels are sorted during layout and binary-searched by
  their visible source-space interval each frame.
- `PianoNative` owns one worker thread and an in-memory command/response
  queue, with completion callbacks delivered on Godot's main thread.
  Its condition-variable wait has a bounded monotonic wakeup: the same worker
  calls `EngineCommands.tick()` to advance automatic attempts, recovery and
  other musical deadlines even when the UI does not request `state.snapshot`.
  Writes re-evaluate the wakeup cadence immediately. No second clock or
  Python scheduler thread is created.
- [EngineCommands](../piano_teacher/inprocess.py) dispatches typed operations.
  [PracticeEngine](../piano_teacher/server.py) is the locked application/API
  boundary. The selected lesson generator owns progression and tempo decisions;
  [PlaybackSession](../piano_teacher/application/playback_session.py) owns transport
  lifetime, [PlaybackCoordinator](../piano_teacher/application/playback_coordinator.py)
  owns authorization, and existing assessment, MIDI, source and persistence
  services retain their domain state. No helper receives the engine to make
  a second teaching decision.
- Note feedback travels through one acknowledged `FeedbackEventLog`
  (`feedback.events`): provisional key-down/key-up events appended during the
  hardware callback and authoritative per-note assessments published on every
  clock update. Each event carries its take identity. Godot reads the log on
  the next frame and acknowledges events only after processing them; the
  backend retains anything unacknowledged.
- Score asset preparation (`score.native_layout`, `score.semantic`) runs on
  a second native thread. A cold Verovio engraving takes seconds; on the
  command/tick worker it used to delay every musical tick and state read.
  `ScoreArtifacts` serializes itself (engraving lock, then model lock) and is
  called outside the engine lock; the snapshot needs only the model lock, and
  the tick reads the published layout without locking. Current-source timing
  and bridge behavior require the existing native checks; an earlier benchmark
  is not a latency guarantee for a later build.
- The Python GIL is held only while invoking Python; the C++ queues
  use condition variables rather than polling threads.

Godot uses `inprocess_request.gd` for typed operation requests and
`score_asset_queue.gd` for revision-bound `score.native_layout` and
`score.semantic` responses. The native C++ bridge accepts only an operation
name and JSON payload (or returns raw audio bytes); results use internal
status values `0=success, 1=invalid, 2=unknown, 3=failed`. No HTTP
method, URL, socket, network adapter or compatibility route exists.
`listen.audio` delivers PCM bytes directly to Godot's sound owner.

## Presentation and progression boundaries

- [PracticeFlowLessonGenerator](../piano_teacher/practice_flow_course.py) commits
  Free → Tempo at 50% in both the selected progress and exact next exposure.
  Listen/Free use the target tempo. [Exposure preparation](../piano_teacher/application/exposure_preparation.py)
  materializes the chosen source and score gate; [GuidedSession](../piano_teacher/application/guided_session.py)
  owns its single fragment/beat interval and controller. The display flow does
  not choose a replacement BPM after a teaching decision is committed.
- [PlaybackSession](../piano_teacher/application/playback_session.py) applies
  start, pause/resume, score/audio readiness and take-completion lifetime
  effects through the existing transport/input/evidence services.
  [AttemptProgression](../piano_teacher/application/attempt_progression.py) and
  [MusicalScheduler](../piano_teacher/application/musical_scheduler.py) use authored
  meter/source facts. [PlaybackTransition and CountInPlan](../piano_teacher/application/playback_transitions.py)
  retain the authorized source, tempo and deadline across admission.
- [AttemptSettlement](../piano_teacher/application/attempt_settlement.py)
  retains the selected assessment/decision and commits evidence and course
  progress together. A failed publication retries the same receipt; it does
  not select another successor or grade the take again.
- [Session snapshot builder](../piano_teacher/application/session_snapshot_builder.py)
  receives explicit capture facts and named read ports. Its detached payload
  cannot mutate the live course, capture, renderer or clock.
- [Main](../godot/main.gd) composes services and signal connections.
  [PracticeCommandCoordinator](../godot/practice_command_coordinator.gd) owns
  request sequencing/results; [ApplicationStateInbox](../godot/application_state_inbox.gd)
  accepts state, [ApplicationPollSession](../godot/application_poll_session.gd)
  owns polling, and [PracticePresentationSession](../godot/practice_presentation_session.gd)
  reconciles state, clock sampling and renderer readiness. Navigation, input,
  settings and audio lifetimes have dedicated sessions.
- [PresentationTimeline](../godot/presentation_timeline.gd) owns forward visual
  projection/rate epochs. [ScoreAdmissionGateway](../godot/score_admission_gateway.gd)
  admits an exact source/revision/deadline; [ScoreSceneController](../godot/score_scene_controller.gd)
  promotes renderers. Retained note/rest ink stays on one world axis, while
  the backend musical timeline remains authoritative for MIDI grading.
- [PracticeFeedbackSession](../godot/practice_feedback_session.gd) consumes
  the acknowledged note-event channel; [LiveMidiFeedback](../godot/live_midi_feedback.gd)
  uses the layout's note-ID lookup. Provisional feedback cannot award mastery.

## Hot-path optimization

- `TempoMapCache` retains the active immutable exercise tempo map by stage
  identity and BPM. A shaped-tempo stage can transform every note to construct
  this map; the embedded 20 ms worker now reuses it until either input changes.
- The native view accepts structural score/recovery state on backend replies.
  Each display frame calls only `present_clock()`, avoiding full practice
  timeline comparisons and recovery-data copies at 60 FPS.
- One monotonic frame timestamp drives the score beat, count-in, and visual
  scroll projection. Busy-button state is updated only on transitions.
- Snapshot projection generates the shifted tempo segment list once for both
  MIDI-time and visual-rest transport fields.
- `performance.diagnostics` exposes bounded `engine_tick` latency
  alongside `midi_callback` and `full_state` latency. These measurements
  exclude physical MIDI hardware and actual display latency.

## Building

Arch developer machine:

```bash
sudo pacman -S --needed godot python base-devel scons git
python -m venv .venv
.venv/bin/python -m pip install -e '.[godot,test]'
bash scripts/build-inprocess.sh
./run.sh
```

The build generates `godot/native/piano_bridge.gdextension` and a
versioned `libpiano_bridge.*.so`. The GDExtension is linked to the
same CPython ABI as the developer's interpreter.

The build imports the Godot resource index and runs
`scripts/verify-native-bridge.sh`: the class must register, embedded
Python must load, and the typed `library.catalog` operation must return a JSON
catalogue. A broken extension must prevent the app from opening.

Godot loads native extensions with local symbol scope. The extension
promotes its linked `libpython` to `RTLD_GLOBAL` before importing
CPython extension modules such as `math`, `python-rtmidi` and
`verovio`.

## Release packaging

`scripts/package-inprocess.sh` bundles Godot, the compiled extension,
CPython and all runtime wheels, and a private Node runtime for offline
fingering inference. The resulting Linux application starts one
process and asks the host only for the OS, MIDI/ALSA drivers, GPU/display
drivers, and standard runtime libraries.

The packager now invokes `scripts/verify-phase5-architecture.py --package`
on the assembled directory before emitting the tarball. Source-only runs
(`python3 scripts/verify-phase5-architecture.py`) check the canonical
Python relative-import graph and absence of deleted compatibility modules.
An audit of the source tree is not proof that a release archive starts.

The package build must still be checked on a clean target machine.
Developer compilation and Python contract checks alone do not certify
a portable release or physical Bluetooth latency.

## Tests and performance

Run `bash scripts/test.sh` (core tests and Godot check). The native
bridge smoke runs with `bash scripts/verify-native-bridge.sh`.

These checks have different meanings: core/Godot checks cover their existing
software contracts; the native smoke exercises embedded startup/typed IPC;
the production and relocated-package scripts exercise the built application
and assembled runtime. Results apply to their recorded source revision.
Phase 5 source review and existing core/native checks pass. The full existing
production workflow passed at `9654d2a3`, including Moonlight Retry/Listen/
navigation/tempo/reopen, Peace Piece, Chopin and the strict relocated archive
build/boot under an empty environment and clean HOME. The archive was built
from tracked current source and isolated bundled dependencies, without global
host site-packages. This is same-host software acceptance, not a clean-machine
desktop session. Phase 6 remains incomplete for physical CA49 USB/Bluetooth,
audible speakers, measured latency, visual/real-performance acceptance and
clean-machine desktop testing. See the remediation tracker for exact evidence.
