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

The application defaults to `legacy`. Change the exercise strategy in **Settings → Practice tempo → Exercise generation**, without using environment variables or restarting.

Available strategies are `legacy`, `fukuda`, `coda-part`,
`feature-gated`, and `fukuda+coda-part`. The dropdown choices originate
from the backend registry; the preference is persisted in local settings.

Changing selection cancels the active attempt and invalidates the score.
Every strategy maintains its own active lesson position, stage tempo, clean
streak, mastery, and bounded assessment evidence in SQLite. A newly selected
strategy without saved progress begins near the source bars of the previous
selection without receiving its credit. Warm-ups and whole-piece performance
remain intact. Strategy switches must not transfer achieved mastery.

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

Legacy progress keys remain unchanged. Nonlegacy stage keys include strategy
identity; the app also persists the active session separately per strategy.
Stage keys are not a measurement of pedagogical effectiveness.

The timing and adaptive-remediation contracts can be exercised independently
of the live score:

```bash
python scripts/compare_exercise_strategies.py song.musicxml --json \
  --timing-preview dotted-long-short --tempo-preview two-phase-tempo
python -m pytest -q tests/test_exercise_strategies.py tests/test_exercise_contracts.py
```

`GET /exercise/diagnostics` exposes the currently selected stage's recent
assessment category and advisory policy recommendation. It does **not**
automatically change the learner's score, the selected exercise, or earned
mastery.

## New typed contracts and strategy registries

`piano_teacher/exercise_contracts.py` defines interchangeable policies:

- **TimingStrategy**: `OriginalTiming` and `DottedPairTiming` return a
  `TimingPlan` containing exact source-index mappings and a distinct exercise
  timeline. Dotted pairs transform only simple single-voice, nonoverlapping
  equal-duration pairs; unsuitable material falls back to source timing.
- **TempoStrategy**: `ConstantTempo` and `TwoPhaseTempo` produce validated,
  contiguous `TempoMap` segments, with beat-to-second conversion.
- **Timing-aware assessor**: `assess_timed()` grades the exercise timeline,
  with optional tempo maps, and rebinds results to original source notes.
- **AssessmentDiagnosisStrategy**: `ErrorFamilyDiagnosis` diagnoses pitch,
  onset/rhythm and held-duration errors from settled take evidence;
  `AccuracyOnlyDiagnosis` is the control.
- **LearnerStateStrategy**: `RepeatedErrorPolicy` proposes targeted
  remediation after two consistent error-family attempts;
  `RepeatOnlyPolicy` is the baseline.

Each has a resolver accepting a registered strategy name or an injected
implementation. `PracticePolicyService` composes assessment and learner
strategies and stores only fully assessed results, keyed by piece fingerprint
and exact stage. It retains up to 64 attempts per stage and reads an eight-take
window by default. Preview/listen sessions do not create evidence.

**Integration boundary:** Retimed exercise plans and tempo shapes are
**offline-only**. The current Godot score, transport and live note-feedback
still assume original source beats and one current BPM. Timing-based strategies
are intentionally excluded from the live strategy dropdown until all three
consumers use the same transformed timeline. Enabling them sooner would display
or grade incorrect notes.

## Remaining work to complete research systems

1. **Live transformed score and transport.** Teach score engraving and native
   notation about `TimingPlan` while retaining the original source score as the
   authoritative artifact. Make seek, count-in, scroll and Listen audio use
   the same timing map. Ensure ties, beams, rests and fingering retain meaningful
   notation after transformation, including across barlines.
2. **Live timing assessment.** Route bounded retries, onset matching, release
   grading, live feedback and error overlays through the transformed timeline.
   Add independent source/timed mapping tests with MIDI fixtures. Only full
   original performance should grant original mastery.
3. **Coda techniques.** Complete chordification and general phrase-level
   part splitting; add context-sensitive dotted rhythm and speed shaping with
   eligibility rules. Current Coda adaptations are deliberately narrower than
   the thesis system.
4. **Piano Tutor remediation.** Feed the history diagnosis into a tested
   lesson-routing policy, support targeted generated recovery exercises, and
   handle same-pitch timing versus wrong-pitch evidence. The current policy
   is advisory, and existing five-error recovery remains unchanged.
5. **Fukuda and difficulty models.** Add richer difficulty analysis, hand
   biomechanics/fingering costs, phrase semantics, and optionally RubricNet
   model integration; retain interpretable feature-only baselines. The current
   paper-inspired variants are partial adaptations.
6. **Pedagogical validation.** Blind teacher ratings of produced exercises,
   plus controlled learner studies on original-source improvement at matched
   practice time. Existing focused tests establish software invariants, not
   educational superiority.

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
