# Practice state machine and timeline (plan, 2026-11-18)

**Why.** "Where are we" is today derived from many loose flags in the engine
(`mode`, `phase`, `running`, `paused`, `awaiting_score_revision`, the guided
controller's phase, settlement and continuation state, flow flags) and from a
second state in the Godot renderer (READY copy, armed Play, bound take). Each
transition must set several of them; a route that forgets one gives the
defects the owner met on 2026-11-18: Free notes scrolling away, a Tempo take
with an empty staff. The fix is one explicit state machine whose state is
the only truth, and a timeline that follows from that state.

The learner-facing behaviour stays exactly as in
[docs/practice-flow.md](../practice-flow.md).

## Two layers of state

### 1. Lesson state (where in the piece)

`FlowState` — owned by `piano_teacher/application/practice_flow.py`:

| Field | Meaning |
|---|---|
| `stage` | course step: phrase/link/final, hand (from the course) |
| `step` | `LISTEN`, `FREE`, `TEMPO`, `DONE` |
| `bpm`, `target_bpm` | practice tempo and the original tempo |
| `failures` | failed Tempo takes in a row at this tempo |
| `clean_at_target` | clean takes in a row at the target tempo |
| `free_returns` | times this stage went back from 50% to Free (aid trigger) |

Transitions (the only functions that change it):

| Event | From | To | Effect |
|---|---|---|---|
| open (fresh piece) | — | `LISTEN` of the first stage | "Listen · hand" |
| open (resumed) | — | `FREE` of the saved stage | "Now without tempo" |
| final stage entered | any | `TEMPO` at 50% | "Whole piece · 50%" |
| listen finished | `LISTEN` | `FREE` | "Now without tempo" |
| listen again | `FREE`/`TEMPO` | `LISTEN`, then back to `FREE` | — |
| all Free notes found | `FREE` | `TEMPO` at 50% | "Now in tempo · 50%" |
| take clean, below target | `TEMPO` | `TEMPO` +10% of target | "Faster: N BPM" |
| take clean at target, first | `TEMPO` | `TEMPO` | "Clean! Once more" |
| take clean at target, second | `TEMPO` | next stage `LISTEN` (final: `DONE`) | "Well done" |
| take failed, first in a row | `TEMPO` | `TEMPO` same tempo | "Again" |
| take failed, second, above 50% | `TEMPO` | `TEMPO` −10% | "Slower: N BPM" |
| take failed, second, at 50% | `TEMPO` | `FREE`, `free_returns`+1 | "Once more without tempo" |
| take failed, second, at 50%, final test | `TEMPO` | `TEMPO` at 50% (no Free in the final test) | "Again at the same tempo" |

### 2. Take state (where in the current exposure)

`TakeState` — one per exposure the learner sees:

`PREPARING` (engraving) → `ANNOUNCED` (segment published with its deadline)
→ `COUNT_IN` → `PLAYING` → `GRADING` → next take is `ANNOUNCED`, or the
lesson transition decides the next step. Free has `WAITING(target)` instead
of count-in/playing. `PAUSED` is an overlay that returns to the same take
state.

## The timeline

Every take state that shows music produces one **segment**:

| Field | Meaning |
|---|---|
| `segment_id` | unique and immutable; republishing never moves it |
| `kind` | `listen`, `free`, `tempo` |
| `source` | stage key, source from/end beat, hand |
| `placement` | `deadline_ms` (listen/tempo) or `hold_at_target` (free) |
| `bpm`, `count_in_beats`, `graded` | how it moves and whether it is graded |

The engine publishes `timeline = {current, next}`. Godot draws exactly the
published segments, binds by `segment_id`, and decides nothing itself.

## Invariants (checked in code and by tests)

1. A take in `COUNT_IN` or `PLAYING` always has its segment in the timeline.
2. A `tempo`/`listen` segment is announced at least one count-in bar ahead.
3. In `FREE`, the staff holds the current target note on the playhead; the
   segment is not republished while waiting.
4. Lesson state changes only through the transitions above.
5. Godot has no admission path of its own.

## Steps (each step leaves the app playable)

1. **Lesson state machine** — *done 2026-11-18.* New module with the transitions above; the
   engine and the course decisions call it instead of the scattered flow
   hooks (`_flow_*` in server.py, `flow_assessed_progress`, the rewrites in
   `PracticeFlowLessonGenerator.decide_teaching`). Status line and messages
   come from the machine.
2. **Take state and segments in the engine.** One owner of the take state;
   `score_queue_next` is replaced by the published timeline segments, with
   the invariants as runtime checks.
3. **Godot shows segments only.** Bind by `segment_id`; remove the READY
   staging and armed-Play path in `notation/native/view.gd` and the queue
   inference in `main.gd`.

Then the remaining practice-flow items (Coda/Fukuda aid, ghost note, Listen
lighting, dimmed hand and neighbour bars).

## Testing

Invariant tests walk the machine through every transition and assert the
invariants (owner request 2026-11-18: guarantee instead of patching).
Behaviour details beyond the invariants get tests only after the owner has
confirmed them at the piano. `bash scripts/debug-session.sh` logs state
changes and `TAKE_WITHOUT_SCORE` defects during manual testing.
