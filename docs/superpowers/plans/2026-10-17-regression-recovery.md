# Regression Recovery Implementation Plan

**Goal:** Restore constant musical travel and accessible drawers on main.
**Spec:** User's Regression Recovery Handoff, 17 October 2026.
**Architecture:** Keep backend transport and grading intact. Project its beat at nominal BPM; correct layout at its container ownership boundary. Use real MIDI/Verovio images and settled Godot controls for regression checks.

Constraints: Work directly on main; preserve MIDI grading, progression and Listen; no cosmetic redesign. Keep playtest.py as the hardware diagnostic entry point.

Review focus: Count-in/downbeat continuity; HTTP sampling bias; all passage intervals including rests and joins; nested scrolling and hidden lessons; resizing/navigation after minimum-size invalidation.

- [x] Inspect history and run baseline tests; capture desktop drawer frames.
- [x] Add failing constant-tempo sampling-bias and lesson visibility tests.
- [x] Remove presentation tempo slew; retain backend resets, pause and resume.
- [x] Give lesson content one scroll owner; verify drawer sizing after navigation and responsive changes.
- [x] Audit real imported MIDI and warm-up score spacing, exact note arrival and rendered notation; repair demonstrated geometry faults.
- [x] Run full tests and preflight; capture before/after frames and timed desktop motion; measure idle CPU before considering optimization.
- [x] Record evidence, limitations and offending changes; review focused diff and commit.
