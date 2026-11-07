# Rest-to-next-bar hitch: whole-path investigation (2026-10-31)

The observed symptom is a momentary stationary score/playhead immediately
before the first note of the next attempt. A single user-visible hitch
can originate from an intentionally stopped musical transport **or** from
a Godot frame that was not delivered in time. The checks below are based on
the actual single-process code paths, not measurements on the user's GPU
or Bluetooth keyboard.

## Confirmed code mechanisms and changes

1. **Python visual projection was clamped at the gap boundary.**
   `transport_projection.project_visual_motion()` returned the terminal
   `visual_target_beat` with speed zero once the preview/automatic feedback
   gap elapsed. A pending state transition, even one delayed by a few
   milliseconds, left the score stationary. **Fixed**: automatic gaps
   continue at source BPM until a real state change; manual/paused phases
   still stop.
2. **Godot duplicated that clamp.**
   `visual_transport_clock.visual_beat()` previously used `minf(target,
   projected)` for idle forward motion. If the engine reply was late,
   the bar froze while the UI waited for a new transport ID. **Fixed**:
   automatic feedback and preview gaps keep projecting through their
   deadline. A Godot regression simulates a next-take state reply 220ms
   late and checks both velocity and position continuity.
3. **Frame-rate power management could make the hitch worse.**
   `main._update_visual_frame_rate()` dropped to 30 FPS and enabled
   33ms low-power sleeps whenever running was false and snapshot speed was
   zero. At an auto-gap boundary that condition was possible even though
   another attempt was imminent. **Fixed**: automatic feedback/preview
   gaps are treated as active transport until acknowledged.
4. **A synchronous CPython/GIL call occurred on Godot's render thread
   every frame.** `PianoNative::live_events_json()` acquired the GIL
   and `PracticeEngine.lock` to read live notes. Heavy score/assessment
   operations holding those locks could block the entire renderer, even
   though regular commands were queued. **Fixed**: one outstanding
   `/midi/live?since=N` command runs on the native worker queue; Godot
   consumes completed note data only, without waiting for Python on
   its draw thread. The original synchronous C++ method was deleted.

## Remaining potential causes, requiring real runtime evidence

5. **Queued engine transitions.** `PracticeEngine._advance_pending_feedback()`
   is triggered by engine state updates. The Godot poll timer is about
   80ms with MIDI and 150ms while disconnected. A scheduled transition
   is processed on the next request/MIDI callback, not by a dedicated
   sample-accurate event scheduler. Continuous visual projection now
   masks that normal scheduling interval, but the actual grading/
   MIDI clock can still transition slightly later.
6. **New lesson step rebuild.** If `_commit_pending()` changes the
   stage identity, `score_revision` advances, sets
   `awaiting_score_revision`, and intentionally waits for Godot's
   `score_ready` acknowledgement. Loading Verovio-derived beam, slur,
   chord and tuplet fragments is expensive on a cache miss. This is a
   genuine transition wait. It cannot be eliminated by interpolating
   an old score into a different lesson step. Prefetching the next
   stage is a separate architectural optimization.
7. **Main-thread asset installation.** `ScoreAssetSession._complete_layout()`
   installs symbols/atlases and `_complete_model()` calls
   `_renderer.load_score()`, which builds the score index and fits
   glyph-ink density. Those methods run in Godot's main thread and
   can miss frame deadlines on complicated scores.
8. **Heavy engine callbacks and serialized requests.** Full state
   projection includes note matching, learner snapshots and live marks.
   The native worker serializes requests, while physical MIDI callbacks
   use the engine lock. Large source preparation, persistence, engraving,
   or MIDI-device scanning could delay the next response. A late response
   by itself should no longer freeze the bar, but may delay real score
   changes or grading events.
9. **GPU/driver or operating-system frame scheduling.** A frame may be
   delayed by the compositor, OpenGL driver, or CPU contention. The
   source alone cannot attribute stalls to this layer.

## Measuring on the physical machine

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
bash scripts/build-inprocess.sh
PIANO_TEACHER_TIMING_DIAGNOSTICS=1 ./run.sh --frame-diagnostics
```

The diagnostic flags are opt-in and don't alter scoring or tempo.

Relevant log markers:

- `PHASE8D_FRAME_INTERVALS`: delivered-frame p95 and worst latency.
- `TRANSPORT_TRANSITION`: actual phase/transport/revision transitions,
  queue state-request age and whether the score was ready.
- `SCORE_ASSET_MAIN_THREAD`: main-thread layout/model installation
  cost, split by type.
- `INPROCESS_COMMAND_SLOW`: queued Python commands taking at least
  24ms, including `/state`, `/score/layout` and `/control`.

Interpretation: A long frame with a long asset installation confirms
main-thread layout work. A slow `/state` or `/control` with normal frame
times suggests backend queue/engine latency. A transport change with a
different score revision and `awaiting_score_revision` indicates an
intentional asset gate. A normal state/asset path with long frame intervals
points toward renderer/GPU scheduling. If the cursor is stationary while
both active score projection and frame times remain normal, investigate
the remaining phase/presentation gate separately.

**Not yet verified:** hardware MIDI/Bluetooth and the user's actual
rest-to-bar stall. CI's parser and source regressions do not establish a
smooth 60 FPS session. Do not remove the score revision acknowledgement
or mask real loading with fabricated grading events.
