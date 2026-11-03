# Practice Experience Implementation Plan

**Goal:** Repair visible musical playback, implement the approved dark UI and
reduce redundant teaching steps without weakening the adaptive engine.

**Architecture:** Keep backend timing, grading and source events. Repair engraving
geometry and isolate the Godot score projection where needed. Course changes use
stable identities with additive persistence migration.

**Tech Stack:** Python, Godot 4, Verovio, CairoSVG, SQLite.

**Spec:** [practice-experience-design.md](practice-experience-design.md)

## Global constraints

- Visible playback acceptance precedes cosmetic completion.
- One musical clock; no silent-preview/partial-retry mastery.
- No lost saved progress or fabricated metadata.
- Local work based on main 5cb31c4; no shared-branch push without authorization.

## Review focus

- Transparent and opaque scores must crop and project identically.
- Repeated notes, rests and sustained endings must move at musical time.
- Systems/pages must cross without blank or backwards transitions.
- New course grouping must resume legacy sessions at the same music.
- Small windows must keep controls and both staves usable.

## Tasks

- [x] Read roadmap, README, implementation and recent commits; run baseline tests.
- [x] A1: Add failing crop, rest-event and real movement regressions. Repair
  measured staff geometry and alpha-aware raster handling. Own files:
  `score.py`, `score_geometry.py`, `godot/main.gd`, related tests.
- [x] A2: Capture rendered count-in/playback at 30, 40, 80, 120 BPM; assert same
  notehead moves left under fixed rule, reaches it at onset, and keeps its size.
  Cover pause/resume, retries, short and multi-system examples. Replace page
  following if necessary; repeat desktop capture before proceeding.
- [x] B: Apply shared dark theme; build working lesson/settings context and
  simplify practice controls. Verify library, practice, lesson and settings at
  laptop/fullscreen sizes with rendered images.
- [x] C: Add long-course size/coverage and saved-session migration regressions,
  consolidate passages, skip redundant stages and retain target BPM. Verify
  difficult passages, hands, connecting work and complete original performance.
- [x] D: Run pytest, Godot parser, all supplied smoke/render checks and actual
  launcher. Fresh independent review, address significant findings and document
  exact evidence and remaining physical validation.

## Evidence ledger

- Baseline: 163 Python tests pass; existing headless Godot smoke passes.
- Confirmed: transparent black margins are counted as ink in Godot.
- Confirmed: rest events use `restsOn`, which current geometry ignores.
- Confirmed: count-in camera movement can falsely satisfy playback smoke gate.
- Real source fixture: 2,346 notes, 117 phrases, 1,209 lesson steps.
- Current course: 301 stages, 45 learning sections, 44 boundary bridges,
  complete original through bar 237/beat 712; old progress retained.
- Actual X11 desktop/HTTP: 36 rendered samples at all four requested tempos
  pass note-pixel, fixed-line, pause/resume, restart and preview completion.
- Launcher UI review: real MIDI, all screens, 1536×960 / 1024×768 / 800×600;
  automatic canvas shrinking and repeated device-request errors corrected.
- Compound rests/tied durations: all 2,346 full-piece source notes align;
  backward anchors reduced from 32 to zero.
- MIDI lifecycle: deterministic unplug/replug/failure coverage; physical USB
  and speaker latency remain pending.
- Final: 207 tests, parser, all supplied smokes, full original alignment,
  36 live rendered samples and normal-launcher UI verification pass. Independent
  review findings corrected; see `verification-2026-10-15.md`. Physical acceptance
  is explicitly open and no shared branch was pushed.
