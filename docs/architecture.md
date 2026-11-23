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

`PracticeTimeline` advances musical deadlines on worker ticks through an
ordered, bounded in-worker transition loop.

## Domains and their sole owners

| Domain | Owner (Python) | Owns |
| --- | --- | --- |
| Lesson | `LearningPlan` progress installed only from `teaching_course` / `teaching_decisions` decisions via `TeachingDecisions` | window, hand, step, BPM ladder, streak, mastery, Free returns, aid |
| Course rules | `lesson_settings.course_rules` | per-course mastery count, focus and recovery thresholds |
| Assessment | `practice.py`, `AssessmentService`, `practice_assessment` | original-note matching, onset/release evidence, verdict |
| Settlement | `AttemptSettlement` + `CompletionContinuations` | immutable result → one decision → one durable receipt → typed continuation effect |
| Transport (musical) | `VisualTransport` (state), written by `PlaybackSession` | running/paused, run_at, origin, count-in, rest scheduling |
| Transport (session intent) | `PlaybackSession` | mode, automatic continuation, awaited score, pause context |
| Transport (physical) | `PlaybackCoordinator` | intent → reserve → present ledger, receipts, stale/lost-ACK reconciliation, terminal failure |
| Scheduling | `MusicalScheduler` (`SCHEDULER`) | every deadline/count-in/rest calculation |
| Score | `ScoreArtifacts`, `TeachingContinuation`, `FutureScore` | one source/revision-keyed bundle per stage, preloaded successor |
| Persistence | `ProgressRepository`, `LearningLedger`, `LearnerProgress` on one SQLite connection | progress, evidence, history; migrations at the load boundary only |
| Projection | `SessionReadModels`, `control_projection`, `state_projection` | one snapshot and control set from committed state |

`TransportTiming` samples transport facts for commands and reads; it holds
no state and delegates arithmetic to `MusicalScheduler`. `TimedPlayback`
opens the take a physical receipt authorized; it never chooses a deadline.

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
   (`TransportActions.commit_playback_intent` → `TimedPlayback.start`).
4. Grading is enabled only for the presented segment. Stale, duplicated or
   reordered replies fail closed; lost ACKs reconcile through
   `playback.status`; three failed admissions end in a visible failure.

Resume of a running take, automatic repeats, Listen and score-ready starts
all use the same intent → reserve → present path.

## Settlement and failure

A completed take produces an immutable assessment and exactly one lesson
decision. `AttemptSettlement.settle` writes the decision, evidence and
progress in one SQLite savepoint and restores the in-memory plan on
failure. The plan's progress after a durable save equals the decision's
`progress_after`; persistence never edits lesson state.

If saving fails, nothing is credited and Play replays the same retained
result. If saving succeeds but installing the next stage fails, the
learner is told progress was saved and Play continues from the same
receipt without regrading. Stop or opening other music discards an
unsaved result.

## Controls

The backend projects every control. The primary button shows **Pause**
only while learning or playing is running or automatically scheduled
(take, count-in, Listen, Free, scheduled continuation or admission), and
**Play** otherwise, including after a failed save. Godot displays the
projected label and action; it makes no lesson, grading or timing decision.

## Godot

- `ScoreAssetSession` requests one source-bound `score.bundle` per stage
  and publishes readiness only after retained native ink compiled.
- `ScoreAdmissionGateway` / `ScoreStreamQueue` implement reserve → arm →
  attest → present over one immutable forward-only score stream; exposed
  ink is never retimed.
- Presentation, metronome, count-in voice and feedback paint the
  authorized segment only.

## Tests

`bash scripts/test.sh` runs the small behaviour suite: Python journeys
drive the engine exactly as the desktop does (presentation protocol, real
MIDI callbacks, score and audio ACKs), then Godot syntax and behaviour
scenarios. `bash scripts/verify-embedded-production-local.sh` builds the
native bridge, runs the real scene with synthetic MIDI, lost-ACK recovery
and the relocated package. Neither certifies physical MIDI, audio or
visual acceptance at the piano.
