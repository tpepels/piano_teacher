# Invariant measure widths implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement and verify each task. Backend and independent pixel-verifier work have disjoint delegated file ownership.

**Goal:** Every source, silent and preparation measure uses its quarter-beat duration times one fixed exercise density; image measurements permanently enforce this across repeats and recovery.

**Architecture:** Keep the existing semantic timeline and native compositor. Unify structural barline projection while retaining glyph clearances, source identities and canonical timing. Verify actual PNG strokes independently of renderer diagnostics, using one common clearance per capture sequence and a 1.5 px raster tolerance.

**Tech stack:** Python, GDScript, Godot framebuffers, NumPy/Pillow, pytest.

**Spec:** User request “Enforce invariant measure widths and constant score velocity”, supplied 2026-10-26; final evidence and contract are recorded in `docs/verification/measure-invariants.md`.

## Global constraints

- `measure_width = duration_in_quarter_beats * pixels_per_beat`.
- `x_B - x_A = (beat_B - beat_A) * pixels_per_beat` for musical anchors.
- Forward velocity is `pixels_per_beat * BPM / 60`; pause freezes; recovery has its own derivative and never edits source coordinates.
- One density throughout the exercise, independent of note/rest density and tempo changes.
- Preserve the genuine Peace Piece 0.5-beat pickup and its separate four-beat preparation.
- Preserve notes, hands, attacks, releases, grading, fingerings, overrides, source identities, clefs and meter changes.
- Native renderer only; no image-strip layout, per-measure scaling, padding beats or relaxed visual thresholds.
- Work on main; targeted tests and `./scripts/verify-notation.sh --ci` only. Do not start the 24-shard audit.

## Review focus

- Double/repeat barline strokes must be distinguished from accidental duplicate boundaries.
- Source/preparation junctions own one boundary; recovery replacement must not leave a second old boundary.
- A paused camera seek or viewport change must preserve musical distances and attached feedback.
- Measure grids with holes, overlap, nonfinite endpoints or a false total must be rejected.
- Correctly timed notes cannot authorize a wrongly drawn rest or a camera jump.

## Task 1: Establish semantic and framebuffer failures

- [x] Inspect the timeline, barline ownership, practice descriptors and existing motion/boundary checks.
- [x] Measure retained real PNGs: Ala preparation 268.5 rather than 288 px; four-beat preparation 364.5 rather than 384 px. The previous source measure gains the missing 19.5 px.
- [x] Preserve before PNGs and their input MusicXML/fixtures in the focused evidence directory.
- [x] Add independent stroke/width verification in `piano_teacher/notation/measure_pixels.py`, with focused tests in `tests/test_measure_pixels.py`.
- [x] Observe failures on retained production frames before changing the renderer.

## Task 2: Correct the authoritative boundary and timing contracts

- [x] In `godot/notation/native/barline_layout.gd`, expose one boundary projection used by source starts, terminal boundaries and preparation endpoints.
- [x] In `godot/notation/native/view.gd`, replace separate preparation offsets with that projection; retain genuine styles, note clearances and shared boundary ownership.
- [x] Test that changing the density during an attempt is rejected and that viewport/tempo changes do not silently select a new scale.
- [x] Validate explicit source grids in `piano_teacher/notation/practice_timeline.py` and test malformed grids without changing valid source models.
- [x] Correct `server.py` visual-speed metadata to match the derivative of its existing position function, including paused gaps and ordinary playback.
- [x] Run targeted model, native geometry and transport tests.

## Task 3: Exercise production app frames and corruption controls

- [x] Add `tests/godot/measure_invariant_capture.gd` and `tests/test_measure_invariant_pixels.py`, using the production main handlers, native renderer and visual transport clock.
- [x] Capture Ala, Peace pickup, genuine 3/4, source full rests, simplified lessons, dense/sparse adjacent measures, mixed meter and failed recovery.
- [x] Use 800×600, 1220×780 and 1600×1000 viewports and 40/80/120 BPM without re-engraving between tempos.
- [x] Detect PNG barline strokes and measure actual widths; record successive feature displacements before, through and after silence/repetition.
- [x] Verify pause/resume, clean automatic continuation and failed recovery/preparation/replay with actual backend-derived snapshots.
- [x] Render deliberately corrupted controls: half-width rest, displaced preparation boundary, duplicate boundary, measure-local density, changed speed, wrong rest with intact source notes, and repetition jump. Every control must fail the independent invariant verifier.
- [x] Strengthen the existing continuous-repeat boundary helper so its previous presence-only test cannot pass compressed measures.

## Task 4: Review, verify and deliver

- [x] Save before/after production screenshots, observed width and displacement tables, corruption outcomes and limitations in `docs/verification/measure-invariants.md`.
- [x] Request an independent review of geometry, ownership, oracle independence and transport continuity.
- [x] Run focused regressions, then the fast CI gate and Godot validation.
- [x] Preserve audit captures and historical archives, inspect worktrees/status, commit completed work and push main.
