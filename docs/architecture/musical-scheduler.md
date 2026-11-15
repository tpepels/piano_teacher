# Musical scheduling engine

The **only** authority for choosing MIDI-graded deadlines is
`piano_teacher/application/musical_scheduler.py` (`SCHEDULER`).
It is a pure calculation module; it owns no engine thread, renderer,
MIDI connection, persistent progress, clock, or mutable transport state.
`VisualTransport` retains the results under the existing engine lock.

## Dimensional model

- **Source beat**: quarter-note beat. Authored meter chooses bar duration;
  the authoritative source tempo map converts beat intervals to seconds.
- **World beat**: monotonically increasing visual location. Godot runs the
  presentation interpolation at frame rate; it cannot grade MIDI or choose
  a later start. It never rewinds on Pause, Retry, stage change or slowdown.
- **Elapsed time**: monotonic seconds. All deadlines are absolute.
- **Engraving clearance**: beats measured by the native Godot/Verovio
  renderer from actual glyph rectangles, clefs, source rest barline,
  source extent, and immutable peer strips. This is **input** to the
  scheduler, not a second start-time calculation.

For constant BPM, `seconds = beats*60/BPM`. For authored tempo
segments, the selected immutable source tempo map provides
`seconds_at(beat)` and `beat_at(seconds)`. The scheduling engine
performs these conversions; the renderer interpolates the resulting
immutable source plan for frame presentation.

Every timing decision uses the **maximum** of independent absolute
lower bounds: score/peer clearance, a full one-bar count-in and its
snapshot latency, an existing absolute reservation, and (where
applicable) future score readiness. Rest and count-in can overlap;
neither can be silently counted twice.

## Routes

| Route | Scheduler entrypoint | Input geometry |
| --- | --- | --- |
| Play / Perform / Listen | `initial` | Renderer-reserved absolute graded deadline |
| Ordinary repeat / disconnected preview | `repeat`, `short_rest`, `automatic` | Source end, one full authored empty measure, header |
| Manual Retry | `reserved_retry_reverse`, `prepare` | Reserved world onset, written rest |
| Failed-take / rolling recovery | `prepare`, `short_rest`, `recovery_rewind` | Last source clearance, future suffix |
| Automatic speedup / slowdown | `tempo_epoch`, `source_seconds`, `short_rest` | Same physical glyphs at changed beat rate |
| Pause / Resume | `shift_epoch`, `shift_passage`, `resume_playing`, `fresh_resume` | Reusable pending copy or earliest fresh safe slot |
| Prepared next lesson | `handoff` | Outgoing rest and incoming full authentic header |
| Future lesson not ready | `late_ready` | Conservative offline lookahead |
| Guided untimed replay | `guided` | Complete passage plus reading horizon |
| Count-in / onset | `count_in_beats`, `resolve` | Authored preparation meter |

All automatic passages are published as the **immutable**
`PassagePlan(from_beat, run_at, bpm)` (a named, typed tuple compatible
with existing state projection), plus the existing plan serial and
score revision. `score_queue_next` is the same plan consumed by the
renderer and MIDI grading. Rebinding changes the identity; re-timing
an acknowledged paused copy changes only its absolute deadline.
An existing announced plan is used unchanged when settlement completes.

## Ownership boundaries

1. **Engraving** computes and reports `continuation_clear_beats`,
   `continuation_header_beats`, the offscreen horizon and immutable
   queue/peer floor. It rejects clips that cannot safely fit. It does
   not decide a new tempo or run_at.
2. **MusicalScheduler** combines these measured constraints and current
   authoritative tempo into one absolute deadline. It preserves a
   one-bar count-in and admits a new source only after previous ink.
3. **PracticeEngine** owns session state, selected teaching decision,
   source and authored tempo, persisted grading, and the transport lock.
   It does not implement alternative time arithmetic.
4. **VisualTransport** stores immutable upcoming passage plans and
   rewind/preparation epochs. It calls the scheduler for every change.
5. **Godot ContinuousScoreFlow** is a frame-rate interpolation of the
   forward presentation axis, not a separate authority for MIDI grading,
   source identity, recovery, or starting a passage. Tempo-map
   interpolation for display uses backend-published `tempo_epoch_ms`
   and exact scored `deadline_at_ms`.

## Acceptance

`tests/test_musical_scheduler.py` exercises all route calculations,
authored tempo maps, count-in invariants, failed boundary recovery,
immutable plan identity, short rest, fallback horizons, pause/resume,
and stage handoff. It runs in the bounded fast CI gate alongside the
existing engine transport/teaching contracts.

`tests/test_continuation_deadline.py` checks production engine
identity and live clock routes, including a final-boundary rolling
slowdown. Godot native screenshot tests check authentic noteheads,
rest ink, header clearance, and overlapping peer clips.

**Release validation is separate:** all four `scripts/ci-full.sh`
shards, the actual MIDI/ALSA + Godot
`tests/test_readiness_continuations.py::test_automatic_rests_are_at_most_about_two_bars`
(with the unchanged 2.25-bar bound), and physical keyboard
acceptance must pass on the same revision. No bounded CI result should
be represented as physical acceptance.


## 2026-11-15 full-tree legacy removal sweep

All previously exposed timing facades have been **deleted**, not forwarded.
The pure scheduler now owns repeat and preview deadlines, manual retry rest
budgeting, speed changes, pause/resume, source rest measurements, and
cross-lesson handoffs. `server.py` retains only two **measurement capture**
helpers (`_collect_rest_measurement` and
`_collect_continuation_measurement`) that report immutable inputs to the
central `SCHEDULER` methods; these helpers do no deadline arithmetic.

The migration also replaced inline beat/BPM time arithmetic in
`assessment_clock.py`, `assessment_service.py`, `exercise_contracts.py`,
`practice.py`, `transport_projection.py`, `state_projection.py`,
`live_input_view.py`, `live_feedback.py`, `feedback.py`, recovery
and Fukuda MIDI calculations, `midi_calibration.py`, `listen_session.py`,
and sample/demo audio synthesis. The score tempo map remains the authored
piecewise definition; it uses the scheduler's common conversions rather
than a second hard-coded 60/BPM expression.

`scripts/audit-musical-scheduler.py` now inspects first-party Python,
GDScript, native bridge, tests and scripts. It rejects obsolete API tokens
and obsolete imports anywhere, and uses a Python AST walk to reject
independent literal-60/BPM conversions across **all production Python**.
It runs in the normal `scripts/ci-smoke.sh` push gate. Historical
third-party addons are excluded; original source notation and score
interpolation are still owned by the renderer and are independently
accepted against physical glyphs.

The additional `musical-scheduler-acceptance.yml` workflow runs all
previously unselected source-clock and grading integration modules and
eight Godot 4.7.2 immutable notation/transport fixtures. It exposed
seven stale generator-API tests that were migrated to immutable
`decide_teaching` decisions and proper two-hand stage fixtures, without
restoring removed engine APIs or skipping assertions.

**Verified on code revision `fa65a114`:** 429 Python integration tests
passed (6 skipped), all eight real Godot fixtures passed, and the
repo-wide audit reported zero obsolete references and zero independent
production BPM conversions. The standard fast gate also passed.
A native bridge scan found no references to the retired APIs.

These results validate the code integration sweep. Full four-shard release
testing, the exact local Godot+ALSA physical 2.25-bar acceptance, and
physical keyboard acceptance remain separate gates.
