# Individual note status and subtle authentic ink glow

## Ownership

| Component | Sole responsibility | Must never do |
| --- | --- | --- |
| Python `practice.evaluate` / live assessment | Grade pitch, onset and release; decide every status | Read Godot coordinates or UI state |
| `LiveInputView` | Provisional key-down (onset) and key-up (release) evidence, bound to a source note | Award credit or change a grade |
| `LiveAssessmentPublisher` | Publish each new or changed per-note assessment of the running take | Grade; it forwards `_live_feedback` / final marks unchanged |
| `FeedbackEventLog` (`feedback.events`) | The only note-feedback channel: one sequence space, retention until acknowledged | Drop an unacknowledged event silently |
| `FeedbackEventInbox` (Godot) | One acknowledgement cursor; skip repeats, report gaps and overflow | Validate events against a state snapshot |
| `NativeScoreFeedback` | Ingest events into the ledger; buffer events of a not-yet-bound engraving | Draw, or record grades from `state.snapshot` |
| `NoteStatusRegistry` | Per physical note: pitch/onset/release observations, precedence, settlement | Grade or move ink |
| `NoteStatusLayer` (child of each retained source strip) | Recolor that strip's heads from the ledger | Repaint per frame, copy the queue, or draw outside its strip |

### One acknowledged channel

Every feedback event is self-describing:

```text
{sequence, kind: attack|release|assessment,
 piece_fingerprint, revision, transport_id, mode, graded, ...}
```

The take key `fingerprint|revision|transport|mode` is exactly the key the
renderer assigns to the source strips of that take. Godot therefore never
compares an event with `last_state`: a Play/Resume/Retry attack that arrives
before the first snapshot of its new transport is applied to its own take.
`main.gd` requests `feedback.events` with the last acknowledged sequence,
dispatches each new event once (ledger, then stage reaction for attacks) and
acknowledges it only after both returned. The backend keeps every
unacknowledged event, so a failed or late read loses nothing; an overflow of
its bounded log (8192 unacknowledged events) and any sequence gap are
reported as errors. An event whose engraving revision is newer than any bound
renderer is buffered in `NativeScoreFeedback` and replayed, in order, when
that revision binds; events of an engraving no renderer still shows are
ignored. Ungraded (preview/listen) events never record a status.

The state snapshot's `midi_recent_keys` only drives the on-screen keyboard.

### Continuous assessment

On every engine clock update while a graded take runs (the native worker
ticks at 20 ms independent of UI polling), the engine computes its normal
incremental live assessment (settled notes after their release grace, and
expired-attack misses) and publishes each per-note result that is new or
changed. Missed notes and release grades therefore appear during ordinary
playback. Rolling recovery and take completion publish their marks through
the same publisher, before any transition starts another transport. The
snapshot's `feedback_marks` reuse the marks computed by that update.

### Independent dimensions and precedence

Python keeps one grading `status` (onset error first, then release) for
pass/fail and progression; that is unchanged. Each projected mark also
carries `dimensions`:

| Dimension | Values |
| --- | --- |
| pitch | `correct`, `wrong`, `missed` |
| onset | `on_time`, `early`, `late` (absent when no attack matched) |
| release | `on_time`, `short`, `long`, `unreleased` (key still held) |

A notehead shows one color, chosen by explicit precedence (highest first):

1. wrong or missed pitch → `missed` (coral)
2. late onset → `late` (amber)
3. early onset → `early_onset` (orchid pink)
4. observed early key-up → `early_release` (lavender)
5. late key-up or still held → `late` (amber)
6. otherwise → `hit` (mint)

The ledger keeps every dimension, so a combined early-onset/early-release
note stays recorded as both while showing orchid pink.

### Provisional and settled evidence

A matched key-down records `{pitch: correct, onset}`; its key-up (paired FIFO
per pitch, like the Recorder) records `release` using the grader's own
duration tolerance, so lavender can appear the moment a key is released
early. Both are provisional. A settled `assessment` replaces the whole record
and locks it against provisional evidence; a later settled result (for
example after the real key-up of a held note) may replace it again.

**Pause/Resume (R1 F2).** The Recorder and `LiveInputView` time key events
on one graded musical clock, `PracticeEngine._musical_seconds` (seconds since
`run_at`). It stands still from the Pause moment until grading resumes after
Resume's lead. A key held across the pause is measured on that clock, so the
paused interval and the lead do not count. A key-up while paused or during the
lead counts as released at the pause moment and is never dropped. A paused
take therefore grades every note exactly as the same performance without the
pause, and the live release verdict always agrees with the settled one.

| Canonical status | Note ink | Glyph glow |
| --- | --- | --- |
| `unplayed` | Original score white | None |
| `hit` | Mint `#53E7B7` | Tiny mask-only mint |
| `missed` | Coral `#F17978` | Tiny mask-only coral |
| `late` | Amber `#F0B661` | Tiny mask-only amber |
| `early_release` | Lavender `#BCA4F1` | Tiny mask-only lavender |
| `early_onset` | Orchid pink `#F08FCB` (`Ink.EARLY_ONSET`, one constant; was pale gold, too close to amber) | Tiny mask-only orchid pink |

Records belong to physical note instances: **(immutable take, engraved note
ID)**. A repeated passage is another take, so the same source note can be
mint in one copy and coral in the next. The ledger is pruned only for takes
that no longer have a source strip in any live renderer (the current one or
a scrolling runway tail), except the active take.

## Rendering: status ink inside the source strip

Each `RetainedSegment` (one immutable source strip) owns a `NoteStatusLayer`
child. It shares the strip's transform and its `StreamPassWindow` clip, so a
colored head moves with the source ink and is clipped exactly where the
strip is clipped; a head split across two measure strips is painted in two
clipped parts that form one head. The layer reads the take bound to its
strip and repaints only when that take, the take's ledger revision, the
graded/preview visibility or the strip's compilation changes — never while
the score scrolls.

When the strip compiles, it records for every head the exact artwork it was
painted with: standalone head glyph, or head *n* of a composite Verovio note
or chord template, its anchor, ink color and staff space. A status head is
recolored in place with three passes of that same artwork:

- **erase** (subtractive blend): the template's own head texels
  (`glyphs.head_cutout`, the template restricted to ~1 px around that head;
  touching chord members are partitioned so no texel belongs to two heads),
  drawn with the template's rectangle and the original ink;
- **core** (additive blend): the same texels in the status tint;
- **fill** (mix, hollow half and whole heads only): the enclosed interior of
  the head's own glyph (`glyphs.head_interior`, the glyph's pixels inside its
  outline, antialiased) in the status tint at alpha 0.55, so a hollow head
  reads as its status. It stays inside the head's own mask region: no ring;
- **glow** (mix): the head mask at 1.024× (alpha 0.105) and 1.052× (alpha
  0.045).

A tied continuation head takes the colour of its attack (owner decision C4):
`NativeScoreFeedback.statuses_for_take` expands each attack's status to the
continuation heads that share its `source_id`; the ledger itself stays keyed
by the physical attack.

For coverage *a* over background *b* the strip held *b(1−a)+ink·a*; erase
and core leave exactly *b(1−a)+tint·a*. The white head is replaced, not
overpainted, so no white contour remains. Hollow half and whole heads stay
hollow (outline and interior are both tinted). There is no ring, badge, circle, detached halo, bloom rectangle,
particle or second score renderer, and unplayed notes are not touched.
Projected `drawn_note_instances` carry their `take_key` and strip `clip_x`;
the rendering path never copies the online queue.

## Regression gates

- `tests/test_note_status_framebuffer.py` renders the production NativeView
  with real Verovio assets and two copies of the same source admitted
  through the view's queue, then measures the PNGs: unplayed notation
  pixel-identical; no changed pixel outside colored heads; exact opaque tint;
  in-place recolor without a doubled contour (edge-model error); glow ≤ 40/255
  within 3 px of the head; hollow heads tinted softly inside their own mask; independent colors per copy;
  exact translation with the strip and no repaint while scrolling; ink only
  inside its own strip clip, including a head split across two strips;
  preview shows the original notation.
- `tests/test_status_palette_framebuffer.py`: all six statuses on real filled
  and hollow heads (`tests/fixtures/status_palette.musicxml`); set
  `STATUS_PALETTE_SAMPLE=<png>` to keep the sheet.
- `tests/godot/native_score_feedback.gd` (CI): precedence, provisional versus
  settled, release events, transport-transition events, revision buffering,
  tail retention and pruning, inbox acknowledgement, gaps and overflow.
- `tests/test_note_reactions.py`: a real engine take's event log consumed by
  the production app with a stale previous-transport snapshot, exactly once.
- `tests/test_continuous_note_feedback.py`: continuous publication without
  UI polling, immediate source-bound release, combined onset/release errors,
  published grades equal the final assessment, one sequence space.
- `tests/test_live_input_view.py`, `tests/test_midi_visual_fast_path.py`,
  `tests/test_feedback.py`: release verdicts use the grader's tolerance,
  acknowledged retention, and per-dimension projection.
