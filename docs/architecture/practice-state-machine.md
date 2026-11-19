# Practice state machine and authorized playback timeline

**Implemented in source, 2026-11-19.** The current production contract is
[playback-coordinator.md](playback-coordinator.md). The learner-facing
decisions remain [docs/practice-flow.md](../practice-flow.md).

## Two independent decisions

**Lesson/teaching:** `application/practice_flow.py` and the selected registered
lesson generator choose the next passage, hand, lesson step, tempo, adaptive
aid and mastery decision. They never admit score ink or authorize a timed
transport.

**Playback:** `application/playback_coordinator.py` owns the take identity,
score admission transaction, count-in authorization, running/paused/settling
lifecycle, cancellation and explicit failure states. Every timed origin
(including physical MIDI controls and automatic continuation) uses the same
transaction. The coordinator publishes `playback_intent` and
`playback_timeline`; Godot draws the exact authorized segment identity.

Untimed Free publishes a separate `guided` timeline segment that holds the
next target at the playhead. It has no timed grading deadline.

## Practice-flow transitions

| Learner event | Flow transition |
| --- | --- |
| Open a new piece | First phrase, right hand, Listen |
| Open saved progress | Saved phrase, Free warm-up |
| Listen completes | Free |
| Every correct Free target found | Tempo at 50% |
| Clean graded passage below target | Next attempt, +10% of target tempo |
| First failed graded passage | Repeat at the same tempo |
| Second failed graded passage above 50% | Lower tempo by 10% |
| Second failure at 50% | Return to Free (except final test) |
| Two clean target-tempo passes | Next hand, phrase, link, or completed piece |
| Repeated failure after Free | Explicitly announced Coda/Fukuda aid |
| Final whole-piece test | Tempo from 50% to original; no Free |

Course decisions are independent of whether the physical score can be
admitted at a particular instant. Once the decision is final,
`PlaybackCoordinator.request` makes an immutable intent. Godot's
`ScoreAdmissionGateway` checks all current and predecessor source/rest
geometry, reserves a future segment, obtains a backend receipt and presents
that exact segment. Only `PlaybackCoordinator.present` can authorize the
musical deadline.

The backend and renderer cannot independently publish another timed source
from a guessed deadline. `score_queue_next` remains an explicit headless
projection and is not part of graphical timed playback.

## Non-negotiable runtime properties

- No timed grading or Listen audio without a source- and revision-matched,
  physically admitted segment.
- Count-in and MIDI/audio use the exact authorized monotonic deadline.
- Score layers and rest strips are immutable after exposure. Cancellation
  touches only a safely retractable future suffix.
- Pause never rewinds the world axis. A resumed graded partial take preserves
  its recorder; a newly admitted future segment starts after the frozen
  musical position. Count-in reuse is limited to an original still-safe
  source; otherwise another full authored bar is provided.
- Automatic progression settles the teaching result before negotiating the
  next score. No polling result can retrospectively insert missing notes
  into a running take.
- A lost worker response is reconciled through `playback.status`, not
  assumed to mean failure. A missing or mismatched bound source interrupts
  the take rather than awarding unseen mastery.
- Real native renderer compilation and source identity are preconditions of
  graphical admission; no HTTP process or compatibility score renderer is
  involved.

## Verification boundary

The current CI runs the pre-existing Python tests and Godot checks. No new
tests were written as part of this architectural replacement, per owner
instruction. A passing source/CI check does not establish physical MIDI/audio
latency, speaker output or full long-piece visual behavior. Those are
separate release acceptance checks.
