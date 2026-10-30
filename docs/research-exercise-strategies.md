# Research-inspired exercise strategies

## Status and scope

This is an experimental **strategy-pattern comparison harness** for source-preserving
note-selection exercises. It does not claim to reproduce complete research systems
or to establish pedagogical superiority. The legacy curriculum is unchanged by default.

All strategies operate on one existing learning passage and selected hand. They
return `ExerciseVariant` with original `Phrase` boundaries, original `Note`
objects, and exact `source_indices`. Pitch and beat timing are never synthesized
or moved. The existing engraving, MIDI grading, tempo ladder, source alignment,
and progress engine therefore remain applicable.

## Adapters

| Key | Concrete behavior | Research relationship |
| --- | --- | --- |
| `legacy` | Original skeleton/outline/original with authored-group constraints and dense one-bar fallback | Pre-existing app; experimental control |
| `fukuda` | Drop inner pitches in chords, keep lowest/highest voice pitches; optionally omit a single isolated returning octave outlier when not covered by authored beam/slur; restore notes in stages | Adapted from Fukuda et al., *A Score-Informed Piano Tutoring System* (SMC 2015). Does **not** implement their audio transcription, DTW or general fast-passage thinning (which their evaluation found problematic) |
| `coda-part` | Source-onset-aligned prefix practice with atomic simultaneous attacks and authored beams/slurs | Inspired by the Part Splitting category in Tang's *Coda* (2025). **Does not** implement Coda's rhythm alteration, tempo shaping, or chordification |
| `feature-gated` | Explicit chord/large-leap/rapid-onset descriptors choose Fukuda, Coda-part, or original legacy plan | Interpretable descriptors inspired by RubricNet (Ramoneda et al., ISMIR 2024). **Not** RubricNet's trained classifier or weights |
| `fukuda+coda-part` | Construct nested cumulative note subsets from the two proposals, optionally starting with common retained notes; end with exact source | Composition strategy, not a published algorithm |

More combinations are available, e.g. `feature-gated+coda-part`. A composite
never changes source pitches or timing, and monotonically adds notes. Neither
single-strategy results nor combinations should be assumed educationally effective
without teacher/learner evaluation.

## Selecting and comparing

The app defaults to `legacy`. To try a strategy during a local practice session:

```bash
PIANO_EXERCISE_STRATEGY=fukuda ./run.sh
PIANO_EXERCISE_STRATEGY=coda-part ./run.sh
PIANO_EXERCISE_STRATEGY=fukuda+coda-part ./run.sh
PIANO_EXERCISE_STRATEGY=feature-gated ./run.sh
```

You can also inject a strategy directly into the application logic:

```python
plan = LearningPlan(piece, exercise_strategy="fukuda+coda-part")
```

A custom strategy implements `ExerciseStrategy.generate(context, baseline)`
and exposes a stable `name`. The `baseline` callback provides the existing
fully-filtered generator, allowing adapters to delegate without depending on
internal curriculum code. Immutable `ExerciseContext` contains the source
phrase, hand, authored beam/slur groupings, and attack cap.

Generate a reproducible side-by-side report (no score rendering or MIDI input):

```bash
python scripts/compare_exercise_strategies.py path/to/song.mid
python scripts/compare_exercise_strategies.py path/to/song.musicxml --json > comparison.json
python -m pytest -q tests/test_exercise_strategies.py tests/test_exercise_generator.py
```

Text reports list stages, hand, source bar range, note count, and attack count.
JSON adds every retained pitch/onset/duration/source ID for independent review.

Changing strategy requires restarting the backend. Legacy progress keys are
unchanged. Nonlegacy stage keys include strategy identity to prevent earning
mastery or transferring tempo from unrelated exercise definitions. Stage keys
are not a measurement of pedagogical effectiveness.

## Grounding / limitations

- Fukuda, Ikemiya, Itoyama, Yoshii (2015), *A Score-Informed Piano Tutoring
  System with Mistake Detection and Score Simplification*:
  https://sap.ist.i.kyoto-u.ac.jp/EN/bib/intl/FUK-SMC15.pdf
- Annie Tang (2025), *Coda: A Digital System for Generation of Piano Practice
  Exercises from Symbolic Music Notation*:
  https://digitalcommons.dartmouth.edu/cs_senior_theses/76/
- Ramoneda et al. (2024), *Towards Explainable and Interpretable Musical
  Difficulty Estimation: A parameter-efficient approach*:
  https://arxiv.org/abs/2408.00473
- Dannenberg et al. (1990), *An Expert System for Teaching Piano to Novices*:
  https://www.cs.cmu.edu/~rbd/papers/Piano-Tutor-JNMR-1990.pdf

The CMU Piano Tutor's *performance-error-triggered remediation* is a distinct
strategy axis requiring an assessment-history and retry adapter; it is not part
of this source-note-selection implementation. Similarly, Coda's dotted-rhythm
transformation and tempo shaping require introducing explicitly authored
exercise event timings and a corresponding score/grader contract. Pretending
those were implemented by simply deleting source notes would be misleading.

For manual assessment, evaluate teacher-rated musical coherence, technical
relevance, attack/source coverage, complexity progression and, ultimately,
performance improvement on the unchanged original score at matched practice
time. These are currently experimental variants.
