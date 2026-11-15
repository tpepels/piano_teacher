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
than defining their own initial defaults.

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
lesson-step marker alignment, meter grid placement, 40/80/120 BPM velocity,
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
