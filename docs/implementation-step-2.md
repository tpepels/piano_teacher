# Step 2 — SOLID strategy architecture

Tracked against main. Each checkbox is updated only when the corresponding code is committed.
Step 1 baseline: 42 Python tests, Godot main parse, Godot clock and settings checks
passed on the user's Arch/Godot 4.7.2 laptop at b359918.

## Work items

- [ ] 2.1 Composable exercise stage pipeline with explicit typed metadata.
      Keep public variant levels, stage keys and saved profiles unchanged.
- [ ] 2.2 Active exercise timing chosen by injected strategy, never by a
      substring in a stage name; score artifact selection uses metadata.
- [ ] 2.3 Unify transformed and ordinary grading around a single matcher
      with per-note onset/release clock; preserve compatibility API.
- [ ] 2.4 Isolate feedback/recovery coordination and learner policy
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
