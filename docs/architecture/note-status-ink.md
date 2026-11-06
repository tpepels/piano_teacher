# Individual note status and subtle authentic ink glow

## Ownership

The Python assessment engine is the sole source of grading decisions.
`NativeScoreFeedback` consumes its authoritative `feedback_marks` and
low-latency, explicitly provisional `midi_visual_events`. It never infers
scores from camera coordinates or MIDI pitch alone.

`NoteStatusRegistry` records the status of each **(immutable transport take,
original note ID)** pair. The take key consists of score fingerprint,
engraving revision, transport ID and mode. It retains status for notes in
old, still-visible source strips after the next take starts, while identical
notes in later, unplayed copies remain untouched. On each repaint, the
renderer supplies the physical `drawn_note_instances`: their
`pass_index` resolves to a specific immutable source strip's `take_key`.
The registry prunes results only after the corresponding strip has left the
queue (except the current take, which remains available for late feedback).
A new engraved score resets the ledger.

The raw backend categories are mapped as follows. Early *onset* and early
*release* are deliberately distinguished; the latter is Python's `short`
grade, rather than treating all early-key events as early release.

| Canonical status | Backend evidence | Note ink | Glyph glow |
| --- | --- | --- | --- |
| `unplayed` | No applicable event | Original score white | None |
| `hit` | `correct`, live `on_time` | Mint `#53E7B7` | Tiny mask-only mint |
| `missed` | `missed`, `wrong` | Coral `#F17978` | Tiny mask-only coral |
| `late` | `late`, release `long` | Amber `#F0B661` | Tiny mask-only amber |
| `early_release` | release `short` | Lavender `#BCA4F1` | Tiny mask-only lavender |
| `early_onset` | `early` | Pale gold `#EBCF81` | Tiny mask-only pale gold |

Extra/unmapped notes, `assisted` without a timing verdict, and estimates
never color an arbitrary score note. Live note-on may provisionally set hit,
late or early-onset; an authoritative settled mark overrides it, including
a later short/long release. Subsequent snapshot polls cannot change a
settled note based on provisional MIDI. Records are presentation-only:
they cannot alter practice grading, Coda/Fukuda progression or the monotonic
score clock.

## Actual glow

`NoteStatusInk` paints **the original Verovio notehead texture** three
times at the **same musical anchor**:

- outer glyph contour, 1.052× scale and 0.045 alpha;
- inner glyph contour, 1.024× scale and 0.105 alpha;
- colored core glyph, 1.000× scale and 0.97 alpha.

Only the masked notehead pixels change. The effect is approximately
1 pixel at ordinary staff size. Hollow half and whole note contours stay
hollow. There is no ring, badge, circle, detached halo, GPU bloom rectangle,
shadow loop or frame-dependent glowing particle. **Unplayed returns without
painting anything**, preserving the existing native notation unchanged.
The background, stem, beam, barline and hit-testing positions stay in the
original retained source and are never rebuilt for feedback.

The original `NativeView` continues to scroll immutable source ink and
compute actual physical notehead positions. `NativeScoreFeedback` is now
only a status-dependent mask compositor above it. No new renderer,
camera, source queue, clock or score glyph imitation has been added.

## Regression gates

`tests/godot/native_score_feedback.gd` is required in
`.github/workflows/godot-startup-check.yml`. It verifies:
- all unplayed notes are unchanged;
- exactly one accepted physical hit changes to mint immediately;
- missed, late, short release and early onset are recorded distinctly;
- hollow half/whole heads retain their authentic glyph contours;
- three identical, low-intensity glyph masks and no generic glow object;
- the same source note in an old graded take and a new unplayed take has
  two independent rendered colors at the same time;
- settled grades persist after their feedback window disappears;
- preview/listen never applies earned grades to an ungraded screen;
- a new engraving revision does not inherit stale note statuses.

The suite intentionally uses the actual `NoteStatusRegistry` and
`NativeScoreFeedback` implementations, not a legacy SVG overlay.
