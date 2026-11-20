# ADR-0001: One owner for lesson decisions and playback admission

**Status:** Accepted, implemented in stages beginning 2026-11-19.
**Supersedes:** Main-owned transport reservation, retrospective score_queue_next
admission, preloader-owned handoff timing and message-derived teaching outcomes.

## Context

The previous runtime allowed several independent decision-makers to choose
the next lesson, graded source, count-in, visual deadline and renderer.
Those overlapping responsibilities permitted an accepted playback deadline
with no physically admitted notation and teaching progress changes inferred
from learner-facing text.

## Decision

- A pure teaching reducer selects an immutable PracticeWindow and
  TeachingEffect. Its course progression never parses displayed text.
- The selected generator commits BPM and reset counters together with the
  exact next exposure. Practice Flow enters Tempo at 50%; Listen/Free use
  the target tempo. Its display session consumes those choices and cannot
  mutate the committed plan to choose another rate.
- The selected AssessmentPolicy produces one versioned AssessmentVerdict
  used by progress and persistence.
- PlaybackTransition and CountInPlan are immutable, source-bound intent
  values, not separately recomputed control-layer decisions.
- PlaybackCoordinator alone authorizes timed take lifecycles; PlaybackSession
  owns their mutable mode, flags, take epoch, readiness and pause/resume
  effects. The native
  ScoreAdmissionGateway admits physical note/rest strips and returns a
  source/revision/deadline-bound receipt before the backend can start.
- The forward visual axis uses one versioned PresentationTimeline; it is
  separate from the music/assessment clock but never retroactively
  repays a tempo change or moves exposed notation.
- ScoreRunway prepares and retains future assets; it does not calculate
  transport lead or commit a stage by itself.
- The score rendering view exposes read-only geometry/capability ports and
  delegates engraving/layout, painting, stream identity/recovery and the
  physical admission transaction to dedicated collaborators. The stream
  controller owns the single mutable source/rest FIFO; retained layers do
  not become another ledger.
- Main composes the scene and wires signals. Command coordination, accepted
  state, polling, presentation, navigation, settings, input and audio each
  have dedicated owners. Engine methods retain the locked application/API
  boundary and apply selected domain effects rather than receiving another
  progression decision from presentation code.
- GuidedSession's selected fragment owns the guided beat interval used by
  teaching, notation and evidence; the engine keeps no duplicate interval.
- The distinct headless adapter is not evidence of rendered notation.
  It must not be selected in the native desktop product.

## Practice-window order

For each new authored bar `n`, learn `n` alone, then each trailing
window `n-1…n`, `n-2…n`, `n-3…n` where those bars exist, in that
order. Every routine window contains at most four authored bars. Its
original source IDs and complete sustained releases are preserved.
The separate whole-piece final examination is exempt from the window cap.

## Enforcement and limitations

The source entrypoint is the [current owner map](../system.md). All current
behavior and remaining integration must be checked against
[the implementation tracker](../ownership-and-practice-progression-remediation.md).
This ADR is the architectural decision; it is not a claim that all prior
internal code has already been migrated. Phase 5 remains pending final source
review; current-source production/package verification and physical
Kawai/real-device acceptance remain Phase 6 gates. Neither a green core check
nor a headless rendering/IPC run certifies acceptance at the piano.
