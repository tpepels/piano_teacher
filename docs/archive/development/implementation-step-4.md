# Step 4 — exercise algorithms and adaptive remediation

Working branch: `main`. Short focused tests; no worktrees or broad corpus runs.

## Gates

- [x] 4.1 Extract transparent difficulty features and a replaceable estimator.
      Keep the heuristic default honest; no claimed pretrained RubricNet model.
- [x] 4.2 Extend Coda-style part splitting into progressive source-valid
      stages; add guarded chordification as a separate rhythm strategy.
- [x] 4.3 Improve Fukuda source-safe simplification, applying musical groups
      and preserving complete source on the final stage.
- [x] 4.4 Turn consecutive assessed errors into a bounded actual remediation
      route using existing exercise/guided paths. Keep partial results from
      awarding mastery and retain student navigation/control.
- [x] 4.5 Add exact-source, mixed-voice, recovery, progress and Godot
      regressions; run a short CI gate and report unsupported research areas.

## Invariants

- Every exercise maps to imported note identities and valid source bars.
- Remediation only follows actual assessed MIDI takes; never preview/Listen.
- The original stage must still be graded independently for mastery.
- No stage-key migration, destructive progress reset, or background jobs.
- Policy baselines remain selectable; "repeat-only" must not remediate.
- Unavailable trained research models must not be misrepresented as implemented.
- No multi-minute corpus audit or worktrees.

## Automated acceptance — 2026-10-30

**5 of 5 scoped implementation items are merged on `main`.** All
research-inspired strategies remain explicit adaptations, not complete
reimplementations of the published systems.

- `piano_teacher/difficulty.py`: immutable, inspectable chord size/span,
  melodic leap, rapid/irregular attack, overlapping-voice and density
  features; `DifficultyEstimator` protocol with injected rule-based default.
  The feature-gated generator selects a concrete plan using this policy.
- `exercise_strategies.py`: Coda progression now offers nested
  `coda-part-a` and `coda-part-b` where eligible. Fukuda retains authored
  group-anchored inner chord pitches.
- `exercise_contracts.py`: Coda-inspired `coda-chord-blocks` is selectable
  under independent rhythm strategies, with original source identities and
  explicit eligibility. The pipeline protects authored ties, tuplets and slur
  endpoints from being collapsed unsafely.
- `remediation.py`: after consecutive assessed error-family mistakes,
  `RemediationPlanner` chooses the affected source two-bar chunk. Pitch
  remediation generates an exact source note/chord subset for guided
  key-finding; timing and sustain errors generate bounded partial timed
  reviews. The application auto-routes only regular MIDI-driven practice;
  preview, performance and manually controlled attempts never auto-route.
  `repeat-only` remains a true no-remediation baseline.
- Session integration keeps original stage identities, saves per-stage history,
  never credits guided/partial remedial attempts as full-source mastery and
  lets the student leave the remedial flow using existing controls.
- New tests: `test_step4_algorithms.py` and
  `test_step4_real_scores.py`. The latter exercises chordification against
  checked-in sixteenth-note MusicXML and verifies all required source IDs.
- **Fast contract gate at `f3b97494`: 100 passed, 4 optional skips in 1.72s.**
- **Focused [Step 4 verification](https://github.com/tpepels/piano_teacher/actions/runs/41087812099)**
  at `ad77097a`: 99 Python tests passed, one Godot-dependent Python
  test skipped before installing Godot, then the separate Godot settings
  test passed. Godot 4.7.2 parsing, visual transport clock and Listen drift
  passed with zero failures. No long corpus suite was run.

### Known limitations / next acceptance

- [ ] Physical MIDI/device and audible Listen verification, and real-time
      visual placement for Coda chordification and remedial sessions.
- [ ] More advanced Coda transformations, learned RubricNet inference,
      complex Fukuda/audio-following components, and broader Piano Tutor
      student modeling are **not** implemented. These require model assets,
      independent benchmarks and validated algorithm designs.
- [ ] Teacher/learner comparison: verify whether any transformed or targeted
      exercise improves performance on the unchanged original piece.

Scoped Step 4 automated engineering acceptance is complete. This does
not certify full research-paper reproduction or pedagogical effectiveness.
