# Continuous score: immutable online FIFO and recoverable offline FIFO

This is the authoritative architecture for the continuous moving piano notation.
There is **one forward-only presentation clock**. The fixed playhead, note
assessment, MIDI grading, rendered ink and lesson decisions share absolute
musical deadlines but never seek the visual clock. Coda/Fukuda decides musical
progression; the queue decides which already-engraved passage can be shown.
The integrated Play/Pause/Resume/Retry and spoken-cue ownership contract is
specified in [transport-and-countin](transport-and-voice-contract.md).

## Ownership and invariant boundaries

| Layer | Allowed responsibilities | Forbidden operations |
| --- | --- | --- |
| `ContinuousScoreFlow` | Monotonic visual world time | Seeking backward to retry or pause |
| `ScoreTransportReservation` | Pure validation and planning of the next user-command admission against a preview of retractable queue suffix | Changing live queue, score pixels or backend grading |
| `NativeView.reserve_transport_action` | One preflighted commit for Play/Resume/Retry, verifying identical remaining queue and exact future world deadline | Independent preparation fallback or unplanned withdrawal |
| `ScoreStreamAdmission` | Calculate the next completely offscreen start using actual printed ink bounds; identify a candidate without modifying it | Overlap, independent source/rest timing, excluding an existing owner to make space |
| `ScoreStreamQueue` | Append a complete source/rest owner, retract maximal safe future suffix, expire from front, whole-score teardown | Inserting in the middle, changing committed world origins, out-of-order expiration, silently dropping content |
| `ScoreStreamArchive` | Durable offline FIFO, append-only checked journal, musical source reuse at a newly assigned location | Replacing original source content, consuming a plan before successful enqueue, cross-score reuse |
| `StreamLifecycle` | Validate exactly one source + optional paired rest; allocate, stage and project pre-engraved Godot CanvasItems | Scheduling a passage, deciding success/retry, changing source coordinates or removing arbitrary online entries |
| `ScoreRunway` | Chronological queue of outgoing renderers, pre-engrave the next step, release only the oldest fully exited layer | Stopping the clock, moving old notes, deleting a newer layer before an older live layer |

On an empty strip (nothing of this queue or a live peer layer printed
right of the playhead), Play and Resume instead place the opening one
count-in bar ahead of the playhead, so Play to first note takes one bar
(owner decision 2026-11-08; see rule 8 of
[transport-and-countin](transport-and-voice-contract.md)). The queue admits
such ink inside the viewport only after verifying that strip is empty, and
records `admitted_on_empty_strip`.

Fresh READY ink remains outside the right viewport edge, including
the exact clef/key/time-signature clip geometry. The additional offscreen
margin is 0.12 beat and the READY travel cushion is 0.30 beat. At 31 BPM
this adds about 0.81 seconds until the first printed ink reaches the screen
edge; a larger arbitrary travel allowance must not be reintroduced. While
idle, a hidden READY reservation is **not** continuously replaced just because
it approaches the right edge. Its physical world origin remains immutable; on
Play, an expired reservation is withdrawn and replaced once with an equally
offscreen slot, using the pre-engraved source. This avoids subsecond idle
re-enqueue loops. Remaining musical lookahead and already committed older ink
can still take longer.
All four original Japanese spoken Ogg clips are tracked repository
assets. Runtime practice and startup perform **no network acquisition**.
`CountInVoicePlayer` is owned by the application root and survives score and
countdown UI changes; `CountInCueTimeline` deduplicates all voice/click
preparation events against the same authoritative beat.

The online queue is ordered by **physical world time**, not by when the
backend returned a request. `enqueue()` rejects content that starts inside the
viewport (except a user Play/Resume onto an empty strip, above) or overlaps the
last printed pixel of any existing source/rest slot.
A logical take is represented by **adjoining immutable source strips**, one
per measure boundary, sharing a `take_owner` and transport identity.
Each strip has its own queue owner and journal event. Printed cut points
are source beats; contextual clef and terminal ink margins are retained
in staff-space units so reflow cannot change the musical boundaries.
The final strip can carry one authored rest as part of its atomic admission.
No individual strip may change its original source range or world origin.

A lesson transition retains outgoing NativeViews with their existing queues.
`ScoreRunway` registers every predecessor as a weak spatial-admission peer
of the incoming queue. Every new enqueue must clear all still-live prior
renderer layers, including rapid manual changes. At equal native density,
their real printed world intervals may adjoin without overlap; at different
densities, the prior ink must leave the viewport before incoming ink enters.
Renderer layers themselves retire oldest-first. This enforces one global
presentation order without transferring live CanvasItems between owners.

## Exactly two online removal directions

1. **Dequeue from the front.** `expire_front()` pops only fully departed
   source/rest entries. A later entry may be expired but remains queued until
   the older head has gone. A corrupt source and its paired rest are retired
   together when they reach the front, never from the interior.
2. **Withdraw from the back.** `preview_tail_withdrawal()` and
   `withdraw_tail()` use an identical predicate for exposure and protected
   owners. A user command preflights its full replacement before any mutation;
   the queued owner count and exact deadline are checked at commit.
   `withdraw_tail()` works on complete **strip
   owners**, newest first. It stops at the first strip whose ink has entered
   the viewport, even when that strip belongs to the same logical attempt as
   later, still-invisible measures. Once any printed ink is visible,
   `ever_visible` remains true. Retraction may remove future strips of an
   acknowledged attempt without mutating any exposed fragment. During Pause,
   the chosen active take is explicitly protected and speculative following
   takes are withdrawn. An unsuccessful user command may retract only its own
   provisional logical take via `withdraw_take_tail()`.

The online queue can retain visible A while withdrawing speculative B, then
append a rest and retry A. There is no insertion before visible ink and no
repainting of previously committed notes to reflect a later lesson decision.
If the backend's proposed deadline is too early to fit the retry offscreen,
the renderer rejects it rather than fabricating an onscreen note.

Pause stops speculative admission; the absolute visual axis continues.
While paused, the existing attempt is protected until a concrete Resume
decision arrives. If the exact source interval is still safely reusable,
Resume preserves it. Otherwise Resume retracts the **maximal still-unseen
suffix, including unexposed measures of the formerly active attempt**, and
appends a new continuation behind only the irreversible visible prefix.
Protecting the whole old take after its source opening had changed caused
minute-scale blank gaps at low BPM; that behavior is forbidden.
Retry and changed Coda/Fukuda decisions retract safe future material and then
append exactly the engine-selected source. The backend publishes
`score_queue_next` with `plan_id`, `source_from_beat` and the absolute
`deadline_at_ms`. This applies equally to graded recovery, automatic
continuations and disconnected-MIDI preview. Godot converts that deadline
through the shared calibrated clock and deduplicates repeated state snapshots
by plan ID. Godot **never** computes mastery, streak, tempo or repeat choice.

**One deadline per continuation (R1 F1, 2026-11-10).** The engine decides an
automatic continuation's graded `run_at` exactly once, when the previous take
ends (clean repeat: take end + the renderer's `continuous_horizon_beats`;
failed take: rewind + preparation rest + the same horizon; manual Retry: the
renderer-reserved world position, with no horizon added). It announces that
value (`VisualTransport.announced_continuation`) as `score_queue_next` for the
whole rest, with the graded `transport_id` and the one `count_in_beats` bar,
and starts the take with that same `run_at`; nothing adds a lead at start.
Godot admits the source offscreen at the projected world position and binds
it to the take named by the plan identity (`NativeView._planned_owner`), not
by comparing two onset estimates against a tolerance. The announcement also carries
the take's start BPM (`LearningPlan.bpm_after`); settlement applies exactly
that tempo, so a tempo-step repeat counts in at its own tempo. Only a take
whose settlement cannot change the route, opening or tempo is announced:
not one that may master the stage, re-engrave from performance feedback, or
plan a remediation (decided at take end and reused at settlement), nor a
response that leaves timed practice. An unannounced continuation gets a
fresh full horizon when it is settled and counts its last bar itself.
Resume in a rest re-announces the next take (new plan identity) no earlier
than the position Godot reports it can still admit offscreen, because the
presentation axis kept moving while paused; the old copy gets no count-in.
Resume cannot repurpose a different source interval. A successful
source/transport bind changes only transport status; never immutable source
geometry. Failed controls restore every strip's provisional status or remove
only the rearmost strips of that newly inserted logical take.

## Offline queue and lossless journaling

`ScoreStreamArchive.pending` is the **offline FIFO of available source plans**.
`ScoreStreamArchive.history` is a separate **append-only event journal**.
Pending entries are actual reusable material, not copies of every online note.
The journal records every successful enqueue, withdrawal, completion and score
reset, including exact source/rest geometry, originating owner and replay
source ID.

The journal is stored under `user://score-stream-journal`, keyed by a SHA-256
of the musical score content (excluding transient backend transport revisions).
Each event is a complete JSONL row containing a checksummed payload, flushed
before the corresponding online source/rest owner is withdrawn or freed.
A failed journal append blocks the corresponding destructive queue operation.
No Godot CanvasItem, resource or UI state is serialized.

At enqueue, the offline FIFO is checked for an exactly matching strip source
interval, total piece duration, rest and relative printed clip geometry,
including staff-space margins, under the same musical score key. The source plan is
materialized **into a new owner at a new future world coordinate**; the old
archived plan is unchanged. The successful enqueue and consumption of the
old offline ID are represented by the same journal event. A failed enqueue
does not consume the offline source. Reopening a score reconstructs the
available FIFO, including unclosed online plans from an interrupted session,
without restoring an obsolete on-screen position. Score teardown archives
the originally admitted whole passage even when only its trailing rest remains.

## Explicitly obsolete APIs

The architecture contains no `StreamLifecycle.reposition`,
`StreamLifecycle.widen_source`, `StreamLifecycle.prune`,
`StreamLifecycle.discard_owner`, `StreamLifecycle.release_all`,
`_stream_extend_offscreen` or independent source/rest addition process.
`ScoreRunway.offline_history` has been removed. The superseded SVG-based
score overlay, its notehead/feedback painter, its companion staff renderer
and independent preview-motion module have been deleted with their obsolete
overlay-specific test. The retained native renderer is the sole score path.
All source/rest admission is
through `ScoreStreamQueue.enqueue`; visual CanvasItems are owned by
`StreamLifecycle` only. Score changes retain still-visible old renderer
layers and retire those layers chronologically, from the front.

## Verification gates

- `tests/godot/transport_reservation_integration.gd`: native command
  preflight without side effects, Play/Pause/Resume and future-only binding
- `tests/godot/countin_cue_timeline.gd`: one audio cue per authored beat
  across changed phase epochs and delayed snapshots
- `tests/godot/countin_voice_assets.gd`: actual four Oggs, persistent root
  audio service, playback and frame-coordinator-to-speaker scheduling
- `tests/godot/stream_score_queue.gd`: real CanvasItems, offscreen placement,
  unique owner, safe tail withdrawal, head-only expiry, durable offline replay,
  source isolation, reload and score teardown
- `tests/godot/stream_retained_lifecycle.gd`: immutable source/rest projection
  and compilation, no direct element insertion or source widening
- `tests/godot/stream_rendered_note_overlap.gd`: READY, Play, Pause, Resume,
  Retry, cancellation and notehead non-overlap on one moving world axis
- `tests/godot/seamless_score_runway.gd`: pre-engraved step promotion and
  oldest-first exit across overlapping renderer layers
- `tests/test_retained_score_pipeline.py`: structural rejection of
  superseded methods and duplicate ownership
- `tests/test_continuous_practice_loop.py`: backend-selected plan ID and
  absolute graded deadline survive preview and recovery transitions
- Embedded production UI/real-MIDI scenario and three-score framebuffer CI:
  verify the real Godot 4.7.2 and Python bridge execution path

These tests must be updated to preserve the architecture, not weakened to
permit direct insertion, coordinate mutation or separate legacy rendering.
