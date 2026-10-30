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
- [ ] 2.5 Add focused compatibility regressions, rerun brief CI, and
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

The architecture is complete only when the new strategy paths have runnable,
passing regressions. GitHub fast CI is a smoke gate and does **not** substitute
for the full laptop verification of Step 1.

## Progress checkpoint — 2026-10-30

**4 of 5 work items implemented; local acceptance pending.**

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
   The optional MusicXML cases were skipped by minimal GitHub CI; local
   real-score and Godot verification is still required after Step 2.

### Remaining Step 2 verification / cleanup

- [ ] Rerun Step 1 and new strategy tests on the laptop with the MusicXML
      and Godot extras installed, including headless Godot parse/settings.
- [ ] Manual exercise switch + listen + MIDI practice under transformed rhythm.
- [ ] Review remaining oversized `PracticeEngine` ownership boundaries in
      subsequent small extractions; it still coordinates more than one domain.
      Avoid cosmetic file splitting solely to reduce the line count.
- [ ] Confirm the final fast gate on the latest main commit.

**Scope note:** This refactor does not implement the remaining Coda, Fukuda or
Piano Tutor research algorithms; these are Step 4 of the system roadmap.
