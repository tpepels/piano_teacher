# Piano Teacher - Phase 2A: Musical correctness and score fidelity

Work on `tpepels/piano_teacher`. Start from the latest `main` and create a new branch named `codex/phase2a-musical-fidelity`. Do not merge into `main`.

Read `ROADMAP.md`, `README.md`, and both verification documents dated 2026-10-15. Inspect the actual implementation before changing anything. Phase 0 and Phase 1 are already substantially implemented and software-verified. Do not rebuild the playback engine, curriculum, or interface.

## Objective

Make imported MIDI and MusicXML reliably produce **musically correct, readable, source-traceable exercises**. Every note displayed to the student must correspond unambiguously to a required event that the grader evaluates.

## Implementation

**1. Establish canonical source-note identity**

- Give imported note events deterministic, unique identifiers that survive course generation, simplification, engraving and feedback.
- Distinguish repeated notes, simultaneous unisons and overlapping voices.
- Keep tied continuations associated with their original attack.
- Replace ambiguous nearest-pitch/onset matching with explicit mappings wherever feasible.
- Reject or clearly report unmappable required notes rather than silently estimating positions.

Inspect and update `music.py`, `score.py`, `exercise_generator.py`, `lesson_score.py`, `score_geometry.py`, `lesson_validation.py`, `feedback.py` and related consumers as needed.

**2. Improve musical time representation**

- Preserve quarter-beat timing across MIDI and MusicXML import, exercises, engraving and evaluation.
- Handle explicit pickup measures, changing meters, rests, tuplets, repeated attacks and notes crossing barlines.
- Retain precise source timing for assessment while allowing conventional notation quantization for display.
- Never let display quantization shift the intended onset or create an extra assessed attack.
- Do not infer information that the source file does not contain.

**3. Improve notation readability**

- Stop assuming every right-hand part needs treble clef and every left-hand part needs bass clef. Choose readable clefs based on actual material without changing pitches.
- Preserve explicit MusicXML key signatures and pitch spelling where possible.
- Avoid falsely inventing a musical key for MIDI files without that information.
- Reduce unreasonable ledger-line usage, especially for unusually high left-hand parts.
- Keep the existing dark UI, moving preparation bar, timing beam and score-strip behaviour.

**4. Build a meaningful regression corpus**

Create at least 20 small, deterministic musical fixtures covering different meters, pickups, chords, voices, ties, rests, keys, registers, hand assignments, tuplets and unusual MIDI timing.

Test actual MIDI/MusicXML import and production engraving, not only mocked models.

For each supported fixture verify:

- Required source notes map to precisely the intended displayed attacks.
- Their pitches, hands and onset beats are correct.
- Tied continuations are not counted as new attacks.
- No required notes disappear or become duplicated.
- Evaluation and feedback use the same mapped events.
- Meaningful errors are returned for unsupported or ambiguous input.

Run actual Verovio-to-PNG integration checks on representative fixtures. Include at least one multi-page exercise.

**5. Protect existing behaviour**

Do not regress:

- Continuous score movement and the audible count-in.
- The single authoritative musical clock.
- Deferred two-bar recovery and 10% slowdown.
- Three consecutive clean target-tempo performances for mastery.
- No mastery during silent previews.
- The existing compact curriculum and saved progress.
- Score revision acknowledgements and pause/resume.

Retain the 2,346-note full-piece regression and verify that all original required notes remain represented. Changes to IDs or course structure must not silently invalidate existing progress.

## Verification

Run:

```bash
python -m pytest -q
./scripts/check_godot.sh
python scripts/smoke_phase0.py
python scripts/smoke_godot.py
python scripts/smoke_adaptive_godot.py
```

Also run the real engraving, full-piece alignment and visible playback checks documented in `README.md`.

Do not substitute synthetic approximations for production rendering. If an integration test cannot run, explain exactly why.

## Deliverables

1. Working implementation on the new branch.
2. Automated tests with fixtures that expose the problems before the fixes.
3. A short before/after explanation of the musical correctness improvements.
4. Evidence from actual engraving, including representative score PNGs.
5. Exact test results, remaining limitations and instructions for reproducing them on Arch Linux.

Do not merge. Do not wait for CI to finish; run available checks locally and report their results.

Focus on correctness and readability, not additional UI features. Complete and verify this milestone before moving to input calibration, piano synthesis or new teaching mechanics.