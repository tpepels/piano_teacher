# Continuous score: immutable online FIFO and recoverable offline FIFO

This is the authoritative architecture for the continuous moving piano notation.
There is **one forward-only presentation clock**. The fixed playhead, note
assessment, MIDI grading, rendered ink and lesson decisions share absolute
musical deadlines but never seek the visual clock. Coda/Fukuda decides musical
progression; the queue decides which already-engraved passage can be shown.

## Ownership and invariant boundaries

| Layer | Allowed responsibilities | Forbidden operations |
| --- | --- | --- |
| `ContinuousScoreFlow` | Monotonic visual world time | Seeking backward to retry or pause |
| `ScoreStreamAdmission` | Calculate the next completely offscreen start using actual printed ink bounds; identify a candidate without modifying it | Overlap, independent source/rest timing, excluding an existing owner to make space |
| `ScoreStreamQueue` | Append a complete source/rest owner, retract maximal safe future suffix, expire from front, whole-score teardown | Inserting in the middle, changing committed world origins, out-of-order expiration, silently dropping content |
| `ScoreStreamArchive` | Durable offline FIFO, append-only checked journal, musical source reuse at a newly assigned location | Replacing original source content, consuming a plan before successful enqueue, cross-score reuse |
| `StreamLifecycle` | Validate exactly one source + optional paired rest; allocate, stage and project pre-engraved Godot CanvasItems | Scheduling a passage, deciding success/retry, changing source coordinates or removing arbitrary online entries |
| `ScoreRunway` | Chronological queue of outgoing renderers, pre-engrave the next step, release only the oldest fully exited layer | Stopping the clock, moving old notes, deleting a newer layer before an older live layer |

The online queue is ordered by **physical world time**, not by when the
backend returned a request. `enqueue()` rejects content that starts inside the
viewport or overlaps the last printed pixel of any existing source/rest slot.
Its source and rest have one immutable owner ID. Every placement has exactly
one prepared musical source interval and optionally one authored rest, which
shares its origin and piece duration.

## Exactly two online removal directions

1. **Dequeue from the front.** `expire_front()` pops only fully departed
   source/rest entries. A later entry may be expired but remains queued until
   the older head has gone. A corrupt source and its paired rest are retired
   together when they reach the front, never from the interior.
2. **Withdraw from the back.** `withdraw_tail()` works on complete owners,
   newest first. It stops at the first owner whose ink has entered the viewport,
   or whose placement is no longer safely speculative. Once any printed ink is
   visible, `ever_visible` remains true. The admitted source's coordinates,
   source range and musical identity are never rewritten. An unsuccessful
   user command may retract only its own unacknowledged rearmost owner.

The online queue can retain visible A while withdrawing speculative B, then
append a rest and retry A. There is no insertion before visible ink and no
repainting of previously committed notes to reflect a later lesson decision.
If the backend's proposed deadline is too early to fit the retry offscreen,
the renderer rejects it rather than fabricating an onscreen note.

Pause stops speculative admission; the absolute visual axis continues.
Retry and changed Coda/Fukuda decisions retract safe future material and then
append exactly the engine-selected source. Resume cannot repurpose a different
source interval. A successful source/transport bind changes only transport
status; never immutable source geometry. Failed controls restore provisional
status or atomically remove a newly inserted rearmost owner.

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

At enqueue, the offline FIFO is checked for a matching source interval,
duration and rest under the same musical score key. The source plan is
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
`ScoreRunway.offline_history` has been removed. All source/rest admission is
through `ScoreStreamQueue.enqueue`; visual CanvasItems are owned by
`StreamLifecycle` only. Score changes retain still-visible old renderer
layers and retire those layers chronologically, from the front.

## Verification gates

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
- Embedded production UI/real-MIDI scenario and three-score framebuffer CI:
  verify the real Godot 4.7.2 and Python bridge execution path

These tests must be updated to preserve the architecture, not weakened to
permit direct insertion, coordinate mutation or separate legacy rendering.
