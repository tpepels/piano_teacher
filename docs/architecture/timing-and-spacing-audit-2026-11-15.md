# Timing and notation-spacing architecture audit (2026-11-15)

## Verdict

The backend has one authority for choosing graded musical deadlines:
`piano_teacher/application/musical_scheduler.py`. It receives source
durations, meter, actual renderer clearance and existing reservations, and
returns absolute monotonic times. `PracticeEngine` decides the teaching
progression and stores those decisions. `VisualTransport` holds scheduled
results rather than implementing a second deadline planner.

There are deliberately two other **different** roles, not additional
MIDI-scheduling authorities:

- `godot/continuous_score_flow.gd` advances the presentation world beat
  **forward** even when grading is paused, the upcoming score is empty or
  the learner restarts. It can switch velocity (including delayed slowdown
  reconciliation) without subtracting from the published world position.
- `godot/tempo_timeline.gd` and `visual_transport_clock.gd` interpolate
  the backend's authored source tempo-map segments, count-in and passage
  epoch for display; this is a cross-language presentation implementation.
  They must not choose the next graded deadline.
- `godot/score_stream_queue.gd`, `score_stream_admission.gd` and
  `notation/native/view.gd` maintain immutable source ink placement
  against true glyph clearance. Infeasible positions are rejected, not
  silently shifted to a new graded time.

The backend's recovery projection can have a **negative local rewind
velocity** while preparing the next passage. That is separate from
`ContinuousScoreFlow`'s never-rewinding world axis; calling both of these
"the clock" without distinguishing their coordinate systems is misleading.

## Changing the visual scale

`godot/notation/shared/spacing_policy.gd` now owns four related defaults:

| Parameter | Effect |
| --- | --- |
| `DEFAULT_PIXELS_PER_BEAT` | Initial preferred horizontal beat density; changing it scales ordinary measure widths and beat-separated notes on the **next** score load |
| `MAX_STAFF_GAP` | Largest staff-line separation considered during authentic score fitting |
| `MIN_READABLE_STAFF_GAP` | Lower legible limit for preferred viewport-fitting choices |
| `MIN_LOOKAHEAD_BEATS` | Shared minimum reading horizon for viewport fitting and new-source admission |

The semantic timeline, lesson-step markers, native viewport fitter, real
glyph-ink clearance and stream admission now reference these values rather
than defining their own initial defaults. The authentic clef/key header's
86/17-space origin and 14/17-space key-column increment are also computed
once by `ContextPainter.clef_lead_pixels()`; note painting, transition-clip
clearance and first-source admission all use that rule.

**Geometry invariant:** for quarter-note beat coordinates `b1` and `b2`,
every note spacing and principal barline spacing is

```text
x(b2) - x(b1) = (b2 - b1) × selected_pixels_per_beat
```

An unchanged staff-space offset for barlines cancels when comparing two
barlines. A 4/4 measure occupies 384 px at 96 px/beat and 480 px at
120 px/beat. A 6/8 measure occupies 288 px and 360 px respectively. Authored
pickup meters and tempo changes do not change those beat coordinates.

**Important limitations:** the requested value is a **minimum preference**.
Actual glyph collision and readability checks may raise the selected density
for a particularly dense score; available viewport width may force a
different staff scale. `set_density` is locked after an attempt begins:
re-scaling already-admitted source strips would violate their immutable
positions. Use a new score load (or a deliberate future redesign with
source-generation replacement and full queue preflight), not a mid-run knob.
Changing the time tempo/BPM affects *movement speed*, not measure width.
Changing source note spacing **nonlinearly** is outside the current model:
it would invalidate the linear quarter-beat axis, MIDI alignment, beat-based
barlines, beam groups and source-accurate inter-note timing.

Some quantities are intentionally **not** in the spacing policy: backend
snapshot latency/settlement delay, one-bar count-in by authored meter,
offscreen admission safety margins, staff-specific authentic glyph metrics,
source tempo maps and audio synthesis rate. Treating these independent
physical or temporal constraints as one number would break ownership.

## Existing proof and gaps

- `tests/test_musical_scheduler.py`: absolute bounds, changing tempo in
  measured rests, pause/resume, repeats, handoffs, count-in and immutable plan.
- `tests/test_continuation_deadline.py`: production backend future-plan
  binding and exact graded deadlines, including adaptive BPM changes.
- `tests/godot/continuous_score_flow.gd`: forward motion while paused,
  speeding up, slowing down and authored future tempo projection.
- `tests/godot/visual_transport_clock.gd` and
  `tests/godot/tempo_timeline.gd`: jitter tolerance and source tempo-map
  interpolation at concrete beats and seconds.
- `docs/verification/measure-invariants.md`: independent raster checks
  of exact source and preparation widths, authentic barlines, 40/80/120 BPM,
  density-lock behavior and deliberate corrupted-renderer controls.
- `scripts/audit-musical-scheduler.py`: rejects removed scheduling API
  references and independent production Python BPM arithmetic. It does not
  prove that **all** old architectural concepts have disappeared or statically
  reject every GDScript constant repeated under a different name.

**New cross-component regression:**
`tests/godot/timing_geometry_contract.gd`, run by
`tests/test_timing_geometry_contract.py`, checks the shared spacing defaults,
pickup/4/4/3/4/6/8 source widths at four distinct pixel densities, source
note spacing, exact barline clearance, typed rest and source clip extents,
lesson-step marker alignment, header-column clearance, meter grid placement, 40/80/120 BPM velocity,
a forward rate change, a delayed slowdown, source immutability and
piecewise-authored tempo-map roundtrips. It is a deterministic geometry
test, **not** a claim that every hardware/rendering race is covered.

## Remaining release evidence

1. Full four-shard local CI on the same revision, including framebuffer
   fidelity after the most recent fixes. Older passing shards do not establish
   that a later commit passes.
2. End-to-end real Godot + MIDI/ALSA continuous-note acceptance, including
   arbitrary corpus scores, late snapshots, unreadable/failing native
   assets, tempo changes at measure boundaries and next-stage differences.
3. Actual 2.25-bar continuation bound under physical keyboard interaction.
4. If runtime user-adjustable horizontal scale is required, define a safe
   **next-score-only** preference and persist it. Supporting arbitrary
   midstream reflow would require a new transactional admission contract
   rather than bypassing the density lock.

The code changes in this audit centralize only the matching visual-spacing
defaults and add tests. They do **not** alter the tempo scheduler or claim
full hardware/release certification.


## Deeper full-tree policy sweep — same day

The follow-up scan covered all **121 first-party Godot .gd files**, all
**179 first-party non-research Python files**, and both C++ native bridge
source files. The connected repository tree supplied file paths; the audit
then inspected each first-party source file for beat/seconds arithmetic,
constants, horizon, image/clip geometry, source-rest handling and queue
policy. The existing audit also traverses test and script references and
rejects the retired scheduling names. This is a **bounded source-code
inventory**, not a proof that all semantically related policies can be
identified by names or numeric literals.

The changes made in this pass are:

1. **Cross-language beat/time units**: `godot/tempo_timeline.gd` now has
   signed `seconds_from_beats`, `beats_from_seconds` and
   `beats_from_milliseconds`. The continuous world clock, transport clock,
   metronome/reserved count-in, transport admission, native admission receipt,
   stage command latency and score pixels-per-second use these functions.
   Countdown and playback both depend on the same quarter-beat unit.
   `scripts/audit-musical-scheduler.py` now rejects a direct Godot 60/BPM
   formula outside `tempo_timeline.gd`, supplementing its existing
   all-production-Python BPM/60 AST guard. This stops a common form of
   duplicated calculation from returning.
2. **Late slowdown repayment**: the continuous bar's existing one-half
   repayment limit is named `MAX_SLOWDOWN_REPAY_FRACTION` and used in
   `sample`, `project` and authored-future projection. No different
   stop-or-rewind allowance was introduced.
3. **Staff/ledger appearance**: the actual staff rails now read the
   existing `SymbolPainter.STAFF_LINE_WIDTH` and
   `STAFF_LINE_ALPHA` instead of independently typing their numbers. The
   blank idle staff retains its deliberately quieter opacity.
4. **Unloaded 4/4 placeholders**: `UNLOADED_METER` derives the default
   visual-gap/count-in durations in both Python transport and state snapshot.
   A loaded piece still replaces those placeholders from the *authored*
   incoming meter; its actual rest is never assumed to be four beats.
   Godot's meter grid explicitly names its separate **empty-staff-only**
   visual fallback.
5. **Future engraving**: the two-stage waiting-queue capacity now derives
   from the same two-stage lookahead capacity. A next-stage handoff without
   an outgoing renderer now uses `StreamAdmission.automatic_horizon` for
   its shared offscreen clearance; the older conservative five-beat minimum
   is kept as an explicit fallback.
6. **Authentic header geometry**: the clef/key column spacing established
   earlier in this audit is now also covered by a cross-component test.
   `ContextPainter` supplies the actual paint offset to the native viewport's
   clip and source-opening measurements.

### Similar numbers that must remain separate

| Similar-looking values | Why not merged |
| --- | --- |
| `StreamLifecycle.EXIT_MARGIN_PIXELS=60` and `ScoreStreamQueue.PEER_MARGIN_PX=60` | One controls retirement of already-exited ink, the other prevents a new peer from colliding on screen |
| `PEER_REST_MARGIN_PX=6` and `OFFSCREEN_MARGIN_BEATS=0.12` | Pixels vs quarter beats; separate margin directions and source/rest policies |
| `MusicalScheduler.SNAPSHOT_LATENCY_SECONDS=0.4` and `ListenSync.START_GUARD_SECONDS=0.40` | Backend command latency and an independent audio seeking guard |
| `MusicalScheduler.SETTLEMENT_SECONDS=0.20` and `CountInCueTimeline.LATE_CUE_BEATS=0.2` | Wall seconds vs musical beats, which are tempo-dependent |
| `Timeline.MAX_PIXELS_PER_BEAT=480` and `MAX_SCORE_PIXELS_PER_BEAT=8192` | User-selected preferences vs emergency source-authentic collision fitting |
| `Admission.MIN_READING_BEATS=3`, `automatic_horizon`'s four-beat floor and the authored count-in measure | Minimum offscreen reading room, automatic repeat preparation, and actual source meter are different obligations |
| `SymbolPainter.STAFF_LINE_WIDTH=1.15` vs `InkGeometry`'s more conservative ledger collision envelope | The painter's exact stroke width and the solver's safety rectangle intentionally differ |

### New verification gates

`tests/test_timing_geometry_contract.py` now includes mutation examples
which reject direct `60000/BPM` and `60/BPM` formulas, the shared rail
appearance contract, one lookahead/queue capacity, unloaded meter
consistency and runway fallback reuse. The native GDScript fixture verifies
signed unit conversions at 12–240 BPM, negative count-in beats, full
quarter-beat widths and the monotonic late-slowdown repayment limit.

The first-party GDScript numeric-conversion inventory was rescanned after
these edits; the targeted source-level pattern reported **zero remaining
matches** outside the owning tempo module. The repository was not built or
executed here. Local tests, independent captured-frame acceptance and
physical keyboard acceptance remain required before release.

**Scope caveat:** Identical numbers can represent different policy, and
identical behavior can be encoded using unrelated names and expressions.
The source audit does not automatically detect every semantic alias,
multi-line formula, third-party implementation or runtime synchronization
fault. Those cannot be certified away by declaring the search exhaustive.


### Late-discovered dead spacing estimator

The final source-to-engraving comparison uncovered a second native
note-spacing heuristic:

- `Geometry.required_density()` inferred a rhythm-only candidate from
  consecutive note durations, but the renderer discarded that candidate
  except when it exceeded the absolute score-density ceiling. This was a
  stale readability policy that could disagree with actual glyph fitting.
- `InkSpacing.readable_density()`, followed by
  `InkGeometry.minimum_density()`, actually selects the single retained
  per-score density from authored attacks and rendered glyph rectangles.

The unused rhythm-only estimator has been **removed**, rather than
forwarded or preserved as a duplicate facade. The only needed rejection
from it survives in `InkSpacing.source_attack_intervals_fit()`: a pair of
distinct attacks in the same staff/voice that are physically closer than
`MIN_SOURCE_ATTACK_SPACING_PX` even at the absolute maximum score-wide
density fails closed. This source constraint does not impose an additional
readability curve on otherwise representable material. `InkSpacing` now
also names the existing minimum repeated quick-attack interval count,
interval band, target spacing and quick-attack maximum density instead of
burying their numbers in the density chooser.

The Phase C Godot regression now tests normal eighths, sixteenths,
64ths, coincident chord attacks, different voices, unrenderably close
same-voice attacks and nonfinite clocks. The renderer-level assertion is
updated to check the **actual** `InkSpacing.readable_density` floor and
global maximum, not a computed value the renderer never consumed.

This last case is why a mechanical scan of equal constants is
insufficient: the two policies had *different numbers and names* but
overlapped in their claimed responsibility. Correctness still depends on
the local Godot acceptance suite and on real-score image/physical
tests, not merely on removing duplicate code.


### READY-reservation scale lock

A further ownership mismatch was in `NativeView.set_density()`:
the shared base renderer freezes density only after transport becomes active,
but the native renderer can reserve a hidden READY source/rest strip **while
still idle**. Calling `set_density` in that interval previously rebuilt
the source's retained ink at a new pixels-per-beat value while the FIFO still
held its earlier immutable position and admission metadata. The resulting
note motion/clearance was no longer guaranteed to agree with the reserved
physical source.

The native renderer now refuses a density change while its online FIFO has
**any** reserved strip, even before Play. An unchanged density is a no-op,
so it does not recompile already-committed ink; after all strips are removed
a new preference may be installed. A Godot regression checks the hidden
READY, unchanged-density and empty-owner cases. This extends the original
transport-only density lock to the queue-immutability boundary; it does
not introduce a new policy owner.


### Fixed playhead fraction and projected lesson markers

A later cross-module check found that `RenderPass` independently defined
`PLAYHEAD_FRACTION=.33`, matching but not referencing
`ScoreView.PLAYHEAD_FRACTION`. This affected which physical head among
multiple instances is registered as nearest the fixed playhead.
`Spacing.PLAYHEAD_FRACTION` now supplies both, while step markers inherit
the same position. A single pure `Timeline.project_world_beat()` handles
both score note positions and lesson marker positions, eliminating a
second hand-written `(beat-world_beat)*density` projection.

The local regression checks these ownership relationships and varying
densities directly. The rendering code still requires the normal native
Godot acceptance suite: source-clock equality alone does not establish
the absence of glyph-mask errors.

### Follow-up shard-1 failures reported at 29c26c5f

- `test_frontend_has_time_driven_native_beam` used two different
  monotonic samples to assert one renderer clock position. At 240 BPM,
  `0.01` beats is just 2.5 ms. Re-sampling *after* a complete render
  incorrectly classified a normal slow frame as clock drift. The
  production frame itself still samples once and routes that stamp to
  every consumer. The fixture now compares the renderer with the
  transport clock at `Main.frame_ms`, that exact frame sample, with a
  tighter `1e-5`-beat tolerance and explicit per-phase failure evidence.
  This is a test time-base correction, not a relaxation of production
  clock synchronization.
- `test_recolor_replaces_the_white_head_without_a_doubled_contour`
  exposed a disagreement between the original whole-note source
  texture and the independently reconstructed cutout used to erase
  and recolor it. An isolated whole-note template contains no stem or
  flag, so it can be erased and recolored with the **exact source
  template** through the existing `paint_note` function. Half-note
  and composite heads retain their separate head-only cutouts, since
  erasing the complete half-note would erase its stem. The framebuffer
  thresholds, tinted-core requirement, and negative residual-white
  control remain unchanged. The direct whole-note template check is
  added to the status framebuffer regression.

Neither fix is claimed tested until a local Godot run passes.
