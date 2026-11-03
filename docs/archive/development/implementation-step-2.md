# Step 2 — SOLID strategy architecture

Tracked against main. Each checkbox is updated only when the corresponding code is committed.
Step 1 baseline: 42 Python tests, Godot main parse, Godot clock and settings checks
passed on the user's Arch/Godot 4.7.2 laptop at b359918.

## Work items

- [x] 2.1 Composable exercise stage pipeline with explicit typed metadata.
      Keep public variant levels, stage keys and saved profiles unchanged.
- [x] 2.2 Active exercise timing chosen by injected strategy, never by a
      substring in a stage name; score artifact selection uses metadata.
- [x] 2.3 Unify transformed and ordinary grading around a single matcher
      with per-note onset/release clock; preserve compatibility API.
- [x] 2.4 Isolate feedback/recovery coordination and learner policy
      behind narrowly scoped injectable components or protocols.
- [x] 2.5 Add focused compatibility regressions, rerun brief CI, and
      report any verification gaps (especially real Godot and physical MIDI).

## Invariants

- No worktrees or new branches; commit directly to main.
- Do not rewrite the public stage key/profile contract or existing progress.
- An unchanged original stage keeps author-supplied notation.
- A retimed stage must not reuse original-timed source annotations.
- Changing BPM does not silently inherit transformed-stage mastery.
- Strategy additions must not require changes in PracticeEngine conditionals.
- No long-running CI/corpus jobs.

## Acceptance

The automated Step 2 architecture gate is accepted only after focused Python,
real MusicXML and Godot 4.7.2 tests pass. Physical MIDI and audible Listen
synchronization remain separate hands-on production acceptance checks.

## Progress checkpoint — 2026-10-30

**5 of 5 work items implemented; automated acceptance passed.**

1. `exercise_pipeline.py` owns source-preserving stage composition and
   `ExerciseStage` attaches explicit transformed-rhythm / tempo-policy
   metadata. `LearningPlan` retains original stage levels and profile keys.
2. `server.py` obtains the live tempo map from the active stage, while
   `ScoreSelection` uses an explicit rhythm flag instead of substring matching.
   `strategy_session.py` now handles strategy-profile restoration separately.
3. `assessment_clock.py` provides one per-note onset/release converter;
   both historical `assess_timed()` and runtime assessment use `evaluate()`
   with that same expectation.
4. `application/practice_assessment.py` holds injectable fixed and
   mapped timing policies for grading, live ink and recovery. Diagnostic and
   learner advisory policies are in `diagnosis_policies.py`; both can be
   selected and persisted via Settings without restarting the lesson.
5. New `tests/test_strategy_pipeline.py` tests composition, unregistered
   tempo-policy injection, source-notation metadata, grader equivalence and
   settings persistence. The automatic fast gate now includes the strategy
   and timing tests. On commit 2a86d82d: **89 passed, 4 skipped in 1.34s**.
   The regular fast gate intentionally skips optional MusicXML imports;
   the dedicated bounded Step 2 gate verifies these with actual dependencies.

### Automated Step 2 gate — passed

- **Full focused run:** [GitHub Actions 41074834536](https://github.com/tpepels/piano_teacher/actions/runs/41074834536), code revision `5cc7ceb7`.
- **Real-source Python:** 48 passed in 1.55s; one Godot-dependent Python
  test was skipped at this stage because the runner had not yet installed Godot.
- **Godot 4.7.2 official release:** headless `main.gd` parsing succeeded;
  shaped transport clock reported `VISUAL_TRANSPORT_CLOCK_FAILURES:0`;
  the separately rerun settings-screen pytest passed (1 passed, 0 skipped).
- The standard lightweight push smoke gate remains unchanged. The dedicated
  verification job is path-triggered only when its workflow definition changes,
  or explicitly invoked; it has a three-minute hard job limit.
- **No failures required implementation fixes.**

### Unverified / subsequent work

- [ ] Manual hardware MIDI, audible Listen timing and live UI feedback during
      transformed exercises — production checks, not covered by headless CI.
- [ ] Further reduce unrelated `PracticeEngine` coordination responsibilities
      in small verified ownership extractions (the class remains oversized).
- [ ] Complete source-annotation remapping for altered slurs, ties, tuplets
      and rests as part of Step 3; the current runtime deliberately avoids
      reusing annotations on a changed clock.

The five scoped Step 2 refactor work items have passed automated acceptance;
this does **not** assert full SOLID compliance or production-ready timing.

**Scope note:** This refactor does not implement the remaining Coda, Fukuda or
Piano Tutor research algorithms; these are Step 4 of the system roadmap.
