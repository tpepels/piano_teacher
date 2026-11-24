# Application architecture

This document describes only the **live** architecture. Audit checkpoints,
superseded designs and phase logs are history: read them in Git (this file
before 2026-11-23, and `ROADMAP.md` checkpoints). The learner-visible
behaviour is specified in [practice-flow.md](practice-flow.md).

## Runtime shape

One Godot 4.7 desktop process with embedded CPython:

    Godot UI, native score surface, local audio
            |  in-process requests / replies (EngineCommands)
    native C++ bridge (PianoNative GDExtension)
            |  command worker: serialized requests + monotonic tick
            |  asset worker: score bundles, engraving, fingering
    Python PracticeEngine -> PracticeSession (one serialized event boundary)
            |
    lesson · assessment · transport · score · persistence · projection

- `godot/main.tscn` loads `main.gd`; `InProcessBus` loads `PianoNative`,
  which starts CPython and constructs `piano_teacher.inprocess.EngineCommands`.
  There is no network service, second engine or headless transport.
- The command worker serializes every request and the clock tick. Expensive
  MIDI import, Verovio engraving and fingering inference run on the asset
  worker, outside the application lock, under a source-mutation guard.
- Real MIDI arrives through `MidiConnection` callbacks with arrival
  timestamps and enters the same `PracticeSession` boundary.

## One event boundary

`PracticeSession.apply(event)` is the single write path. Events are typed
(`session_events.py`): user commands, clock ticks, physical MIDI and MIDI
shortcuts, playback reserve/present/withdraw/failure, source and fingering
commits, settings, device, preload and history events. Each event is
validated against fresh state under the application lock, executed by the
owning domain, and published as one versioned state snapshot
(`state_contract.py`, mirrored by the generated `godot/state_contract.gd`).

`PracticeSession` only serializes: it looks up the event's handler in the
one routing table (`session_routes.event_handlers`), runs it under the
lock and, after the outermost event, publishes the committed MIDI epoch.
Adding an event or command family means adding its type and one entry in
`session_routes`; PracticeSession does not change.

- `CommandRouter` validates the displayed score, resolves UI intents,
  prepares the lesson decision and runs the command family's route
  (`session_routes.command_routes`).
- `TickWorker` runs `PracticeTimeline.update_transition` in a bounded
  same-tick loop, replays MIDI deferred during the handoff, publishes
  through `TickPublisher` and chooses the next tick interval.
  `PracticeTimeline` only orders one tick: `TickObservations` (device,
  calibration, Listen failure, evidence phase), `TakeProgression`
  (bar checkpoints, completion) and `PreAssessmentTransitions` (Free,
  Listen end, feedback, rewind).
- `MidiEpoch` is the stale-key gate: a physical key counts only for the
  device, source, revision, stage, hand, take and cancellation it arrived
  in (or a later automatic repeat of the same source after its start).

## Entry points and state writers

Every state change enters `PracticeSession.apply` as one typed event:

| Origin | Operation / callback | Event |
| --- | --- | --- |
| Learner gesture, MIDI shortcut | `practice.command` | `UserCommand` / `MidiShortcut` |
| Native worker | `tick` | `ClockAdvanced` |
| MIDI callback | arrival-stamped message | `PhysicalMidi` |
| Score admission | `playback.reserve` / `present` / `withdraw` / `failure` | `PlaybackReserved` / `Presented` / `Withdrawn` / `Failed` |
| Library, fingering | `library.open`, `fingering.correct` | `SourceCommitted`, `FingeringCorrectionCommitted` |
| Settings, devices | `settings.update`, `midi.devices`, `midi.device.select`, `hardware.action` | `SettingsChanged`, `MidiPortsRequested`, `DeviceSelected`, `HardwareRequested` |
| Successor score | `score.stage_ready` / `score.stage_failed` | `PreloadReady` / `PreloadFailed` |
| History | `learning.export` / `delete_piece` / `delete_learner` | `HistoryExported` / `PieceHistoryDeleted` / `LearnerHistoryDeleted` |
| Shutdown | `close` | `SessionClosed` |

Reads take the application lock and never mutate session state:
`state.snapshot`, `lesson.overview`, `library.catalog`,
`library.health_status`, `settings.snapshot`, `learning.status`,
`learning.statistics`, `score.bundle`, `score.semantic`,
`score.native_layout`, `score.next_stage`, `playback.status`,
`feedback.events`, `listen.audio`, `performance.diagnostics`.
`library.health.start` only starts the background library scan.

## Domains and their sole owners

Each stateful domain is one object with a narrow interface: read-only
properties for facts and named operations for changes. Its internal state
holders are never referenced outside the domain's own modules; other
domains and workflows depend on the domain object only.

| Domain object | Internals | Owns |
| --- | --- | --- |
| `Lesson` (`lesson.py`) | `SourceIdentity`, `LessonCursor`, `TeachingDecisions` (only progress writer), `GuidedSession`, `PracticeFlowCourseSession` | piece, plan and revision; window/hand/step; BPM ladder, streak, mastery, Free returns, aid; guided Free selection |
| `Transport` (`transport.py`) | `VisualTransport`, `PlaybackSession`, `PlaybackCoordinator` | timeline (running/paused, run_at, origin, count-in, rests), session intent (mode, automatic, awaited score), physical intent/receipt ledger |
| `Take` (`take.py`) | `AttemptRuntime`, `AttemptSettlement` | recorder, feedback marks, review/retry; immutable result → one decision → one durable receipt |
| `Score` (`score.py`) | `ScoreArtifactRegistry`, `ScoreReadServices`, `TeachingContinuation`, `ScoreStatePublisher`, `TempoMapCache` | selected score bundle, successor preparation and reservation, score projection; the settlement's reservation port |
| `MidiInput` (`midi_input.py`) | `MidiConnection`, `MidiIngress`, `MidiKeyShortcuts`, `MidiTapCalibration`, `LiveInputView` | device, timestamped routing, deferred keys, grading gate, shortcuts, calibration |

Pure policy and services outside these domains:

| Concern | Owner | Owns |
| --- | --- | --- |
| Practice Flow course | `practice_flow_course` | the window/hand structure and **every "what happens next" rule**: `decide(event, state)` maps a graded take, a completed Free or a learner command to the next exposure, tempo and progress; `graded_progress` maps the ladder onto saved progress |
| Practice Flow ladder | `practice_flow.take_graded` (pure) | repeat / faster (+10%, or +20% after a secure clean take) / slower / Free / done |
| Assessment | `practice.py`, `AssessmentService`, `practice_assessment` | original-note matching, onset/release evidence, verdict, `secure` timing |
| Scheduling | `MusicalScheduler` (`SCHEDULER`), `CountInPlan` | every deadline/count-in/rest calculation; count-in pulse (subdivided when a click would exceed 1.5 s) |
| Persistence | `ProgressRepository`, `LearningLedger`, `LearnerProgress` on one SQLite connection | progress, evidence, history; migrations at the load boundary only |
| Projection | `SessionCapture`, `ScorePresentation`, `SnapshotExtras`, `SessionReadModels`, `control_projection`, `screen_projection`, `state_projection` | one snapshot, control set and screen model from committed state |

Workflows coordinate domains for one event family each (every class
has at most 10 constructor collaborators):

| Event family | Owners |
| --- | --- |
| Learner commands | `CommandRouter`; `LearningActions` (listening/learning routes); `TransportCommands` (Start, Restart, Pause, Resume); `RouteCommands` (Listen/Learn/reload routes, Practice, Stop) |
| Course and navigation | `CourseFlow` (Listen → Free → Tempo, Free, guided preparation, selected exposure); `LessonNavigation` (skip, place, trouble, section review, weak spots, seek, open measure, stage/tempo change) |
| Exposures | `ExposureWorkflows` (prepare Practice/Listen/Perform), `GuidedExposureInstall`, `TimedExposureInstall`, `ListenOutcomes` (Listen finished/failed) |
| Physical playback | `PlaybackAuthorization` (reserve/present/withdraw/fail, authorized commit, score/audio ACKs, resume); `TimedStart`, `PlaybackContinuation`, `PauseResume` |
| After a take | `TakeGrading` (assess, publish final marks); `TakeCompletion` (immediate consequences of focused/performance takes); `SettlementContinuation` (full passage: feedback, commit, exactly-once effect) |
| Recovery | `SelectedRecovery` (enters Free with the aid on the second return to Free) |
| Teaching | `TeachingDecisions` (inside Lesson) captures the facts and calls `practice_flow_course.decide` |
| Source | `SourcePreparationWorkflow` (off-lock), `SourceInstallation`, `LibraryOpening`, `PlanReinstallation` (adopt a plan at its first step) |
| MIDI | `MidiCallback` (arrival stamp), `MidiDelivery` (ingress routing), `MidiDeviceConnection`, `MidiEpoch` |
| History, settings, devices | `HistoryManagement`, `HistoryReads`, `SettingsWorkflows`, `DeviceWorkflows` |

`TransportTiming` samples transport facts (no state; arithmetic in
`MusicalScheduler`). `TimedStart` opens the take a physical receipt
authorized and never chooses a deadline.

## Physical playback protocol

Production has exactly one transport: physical score presentation.

1. A lesson decision or learner gesture requests playback;
   `PlaybackCoordinator.request` publishes a `playback_intent` (source,
   stage, revision, hand, BPM, count-in plan, earliest/fixed deadline).
2. Godot's score admission measures physical clearance and calls
   `playback.reserve`; Python alone chooses the deadline.
3. Godot arms immutable ink and calls `playback.present` with its
   attestation; Python validates source, stage, revision, hand, mode, BPM,
   rate map and transport epoch, then starts the take
   (`PlaybackAuthorization.commit_playback_intent` → `TimedStart.start`).
4. Grading is enabled only for the presented segment. Stale, duplicated or
   reordered replies fail closed: a failed reply cancels the provisional
   admission, and the next state frame decides whether another attempt
   exists; three failed admissions end in a visible failure.

Resume of a running take, automatic repeats, Listen and score-ready starts
all use the same intent → reserve → present path.

## Settlement and failure

A completed take produces an immutable assessment and exactly one lesson
decision. `AttemptSettlement.settle` writes the decision, evidence and
progress in one SQLite savepoint and restores the in-memory plan on
failure. The plan's progress after a durable save equals the decision's
`progress_after`; persistence never edits lesson state.

If saving fails, nothing is credited: the fault is shown and the take is
discarded, so the learner plays it again. If saving succeeds but starting
the next step fails, automatic playback stops, the learner is told
"Progress saved, but the next step could not start", and Play continues
from the saved lesson. Stop or opening other music discards an unsaved
result.

A finished full take plans exactly one continuation
(`AttemptProgression.plan_full_passage`): **stop** (not automatic),
**ready** (Free, next hand/window, done) or **announce** (the same step
again, after the printed one-bar rest at the outgoing tempo).

## Controls

The backend projects every control and the screen itself. The primary
button shows **Pause** while learning or playing is running or
automatically scheduled (take, count-in, Listen, Free, scheduled
continuation or admission), **Resume** when paused, and **Play** (or
**Listen**) only when the flow waits for the player. **Listen again** is
the other visible control; Retry, Slower/Faster, hand and bar choices are
shortcuts and the Pause sheet.

`screen_projection` decides what the practice screen shows
(docs/practice-flow.md, On screen): the status line (window · hand ·
step), one problem notice while the flow cannot continue by itself (no
piano, failed admission, next step could not start), and the keyboard
(the wrong-note hint in Free, otherwise hidden). Godot displays the status
label, puts the notice and command messages on the score banner and
composes no lesson text of its own.

## Godot

- `ScoreAssetSession` requests one source-bound `score.bundle` per stage
  and publishes readiness only after retained native ink compiled.
- `ScoreAdmissionGateway` / `ScoreStreamQueue` implement reserve → arm →
  attest → present over one immutable forward-only score stream; exposed
  ink is never retimed.
- Presentation, metronome, count-in voice and feedback paint the
  authorized segment only.

## Remaining complexity and why it stays

- **Three transport internals behind one `Transport`.** Timeline facts,
  session intent and the physical receipt ledger are disjoint; the domain
  object is the only access path.
- **Two completion vocabularies.** Focused/performance takes settle
  immediately (`CompletionEffect`, applied by `TakeCompletion`); full
  passages settle at their successor boundary (typed, source-bound
  effects, applied only by `SettlementContinuation`).
- **Publication lease and source-mutation guard.** Scoped guards that keep
  a durable receipt alive through its own successor installation and keep
  expensive source preparation outside the application lock.
- **Persistence migrations.** Saved-progress and ledger upgrades live only
  in the repository/ledger load paths.
- **Godot admission files.** `ScoreAdmissionGateway` is the one adapter to
  Python; the renderer (`view.gd`) is the one physical score surface it
  drives (reserve, arm, bind, cancel); `ScoreRunway` prepares the
  successor renderer; queue and stream files implement the immutable
  forward-only ledger.

`scripts/audits/coupling.py` reports constructor fan-in and any access to
domain internals from outside a domain (must stay zero). Constructor
fan-in is at most 10 for every application class.

The composition root builds the graph in six ordered stages (session
state; devices, library and score; persistence and settlement; workflows;
transport and completion; event boundary and its routing table). Every service receives explicit
constructor dependencies; no service locator is injected.

## Tests

`bash scripts/test.sh` runs the small behaviour suite: Python journeys
drive the engine exactly as the desktop does (presentation protocol, real
MIDI callbacks, score and audio ACKs), then Godot syntax and behaviour
scenarios. `bash scripts/verify-embedded-production-local.sh` builds the
native bridge, runs the real scene with synthetic MIDI, the Moonlight
navigation journey, 16 repertoire pieces, the Pathétique and the
relocated package. Neither certifies physical MIDI, audio or
visual acceptance at the piano.
