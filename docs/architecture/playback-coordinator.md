# Playback coordinator — production architecture

The native desktop application has **one timed-playback authorization owner**:
`piano_teacher/application/playback_coordinator.py` (`PlaybackCoordinator`).
Godot owns only the physical admission of immutable notation. A timed
Listen, practice, Perform, preview, automatic repeat, recovery, stage handoff,
Play, Restart or Resume cannot start grading or audio before the admission
protocol has authorized the same source, segment identity and downbeat.

## Ownership

- **Lesson and Coda/Fukuda policy:** chooses an exposure (piece, stage, hand,
  source interval, tempo and whether graded). It cannot authorize timing.
- **PlaybackCoordinator (Python, engine lock):** creates versioned intents,
  validates source revisions, owns the reserve/present/cancel lifecycle,
  authorizes takes and publishes `playback_intent` and
  `playback_timeline`. The coordinator alone commits a graphical timed
  transport through `PracticeEngine._commit_playback_intent`.
- **MusicalScheduler (pure Python):** resolves absolute deadlines from
  count-in, tempo, physical clearance, requested earliest time and latency.
- **ScoreAdmissionGateway (Godot main thread):** chooses the exact prepared
  native renderer, consults all live queue/peer layers, commits the
  physical reservation and sends its receipt to Python. It never grades or
  decides a lesson.
- **ScoreStreamQueue / native view:** immutable strip geometry, maximum
  safe suffix withdrawal, journal, rendering and bound segment identity.
  A failed reservation restores the safe withdrawn suffix if physical time
  still permits it.
- **ScoreRunway:** preloads a next-stage renderer, retains outgoing layers,
  promotes a fully authorized source and never invents a graded deadline.
- **Native bridge:** one main-thread response fanout, one musical worker,
  one read-only asset worker and a shared `steady_clock` monotonic epoch.
- **Metronome/Listen/feedback:** consume already-authorized transport
  epochs and identities; no fallback timed source or independently scheduled
  count-in.

The desktop bridge calls `EngineCommands.require_presentation()` before
accepting any score or MIDI command. Direct Python/headless use is explicitly
the separate non-graphical engine mode: it does not claim to have rendered ink.

## Transaction

1. Engine emits one immutable `playback_intent` with `intent_id`,
   `take_id`, generation, attempt, exact source and starting BPM,
   count-in meter and musical earliest deadline. No count-in or grading
   has started.
2. Godot requires the exact source revision, compiled authentic atlas and
   retained source segments. It preflights real glyph/header clearance,
   viewport, rest and **all live predecessor renderer layers**; it can
   withdraw only a safe future suffix.
3. Godot commits a physically feasible source to its online queue, armed
   but not yet graded. It sends `playback.reserve` with the same intent,
   revision, source, world origin, exact monotonic deadline and queue
   generation. Python rejects inconsistent or expired reservations.
4. Godot binds the returned `segment_id` to that specific retained source
   and acknowledges presentation readiness via `playback.present`.
   Python checks the remaining count-in and commits the selected take at
   exactly that deadline. In a preloaded lesson, Godot promotes the
   prepared renderer after authorization, before showing the new running
   snapshot.
5. All notation, audio, count-in and MIDI grading refer to the authorized
   segment/take and backend deadline. Godot binds a source only when its
   armed segment identity exactly matches `playback_timeline.segment_id`.

An ordinary new take gets one whole authored count-in bar. Pause during a
count-in may reuse the *remaining* part only when its already-admitted,
never-exposed source remains safely ahead; otherwise it gets a fresh full
bar. Pause during graded playing preserves the recorder and frozen musical
elapsed time, and a resumed partial segment cannot advance assessment
until its new admitted opening reaches the playhead.

## Failure and reconciliation

- A missing, stale, physically infeasible or expired receipt never starts
  audio or grading.
- `playback.status` is a read-only authoritative transaction query.
  Because a worker timeout can lose a reply *after* commit, Godot queries
  the backend before deciding whether to retry presentation or withdraw
  ink. `playback.present` is idempotent by segment identity.
- Failed/withdrawn provisional notation is compensated without changing
  exposed prior strips. No automatic new notes are admitted by a state poll
  or by the renderer's previous READY policy.
- A live timed source bound to the wrong segment raises
  `TAKE_WITHOUT_SCORE`; `ScoreAdmissionGateway` issues the typed
  `playback.failure` action. The coordinator stops the take safely,
  rather than grading an invisible passage.
- Stale generations, source revision changes, manual navigation and Stop
  invalidate in-flight transactions. Future work cannot mutate an
  already-exposed passage.

## State projection

In graphical mode `playback_intent` is either the pending admission
request or null. `playback_timeline` publishes the state, active take and
segment, graded source identity, absolute deadline and an optional untimed
`guided` segment. The old `score_queue_next` projection exists only for
the explicit Python/headless adapter and is never used to admit timed
notation in the desktop app.

Untimed Free remains a distinct hold-at-target mode. Its source segment
is drawn on the same retained notation renderer but does not authorize
a timed count-in or MIDI grading.

## Validation and remaining acceptance limits

The existing Python and Godot syntax/component checks run in the normal
CI workflow. No new tests were added for this replacement at the user's
request. CI passing does **not** certify production USB/Bluetooth MIDI,
physical audio latency or full native rendered journeys: those require
hands-on playback and device acceptance. A compiled GDExtension containing
the new native clock method must be installed for a runtime launch.
