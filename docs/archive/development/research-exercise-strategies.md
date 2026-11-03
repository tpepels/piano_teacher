# Research-inspired exercise strategies

## Status and scope

This is an experimental **strategy-pattern comparison harness** for source-preserving
note-selection exercises. It does not claim to reproduce complete research systems
or to establish pedagogical superiority. The legacy curriculum is unchanged by default.

All strategies operate on one existing learning passage and selected hand. They
return `ExerciseVariant` with original `Phrase` boundaries, original `Note`
objects, and exact `source_indices`. Note-selection strategies never invent
pitches or move beats. Separate timing strategies may alter exercise note
onsets while preserving original source identities; the original score and
mandatory final stage remain intact.

## Adapters

| Key | Concrete behavior | Research relationship |
| --- | --- | --- |
| `legacy` | Original skeleton/outline/original with authored-group constraints and dense one-bar fallback | Pre-existing app; experimental control |
| `fukuda` | Source-safe outer-note chord thinning, protected authored-group notes, isolated returning-leap omission, and restoration stages | Adapted from Fukuda et al., *A Score-Informed Piano Tutoring System* (SMC 2015). Does **not** implement their audio transcription, DTW or general fast-passage thinning (which their evaluation found problematic) |
| `coda-part` | Progressive, nested source-onset prefixes with atomic chords, beams and slurs | Inspired by Coda's part splitting; separate rhythm strategies implement restricted dotted pairs, two-phase tempo, and safe chord-block practice rather than its full exercise system |
| `feature-gated` | Injected `DifficultyEstimator` with explainable chord size/span, melodic leaps, rapid/irregular attacks and voice overlap; chooses Fukuda, Coda or baseline | Interpretable baseline inspired by RubricNet. **No trained RubricNet weights or learned accuracy claims** |
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
python scripts/compare_exercise_strategies.py path/to/song.mid --json > comparison.json
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
python scripts/compare_exercise_strategies.py song.mid --json \
  --timing-preview dotted-long-short --tempo-preview two-phase-tempo
python -m pytest -q tests/test_exercise_strategies.py tests/test_exercise_contracts.py \
  tests/test_timing_live_integration.py tests/test_timed_real_scores_and_recovery.py
```

`GET /exercise/diagnostics` exposes the currently selected stage's recent
assessment category and policy recommendation. After two assessed attempts
with the same dominant error family, `RemediationPlanner` can create a
source-bound remedial exercise. In automatic practice it routes pitch
errors into a targeted, untimed guided exercise, and timing/sustain errors
into a bounded timed section review. These partial routes cannot earn
original-stage mastery; repeat-only policy disables them.

## New typed contracts and strategy registries

`piano_teacher/exercise_contracts.py` defines interchangeable policies:

- **TimingStrategy**: `OriginalTiming`, `DottedPairTiming`, and
  `ChordBlockTiming` return a
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

## Live timed exercises (experimental)

The Settings screen now has five independent strategy selectors:

- **Exercise generation:** existing note-selection and combined strategies.
- **Rhythm exercise:** original, dotted long–short, dotted short–long,
  or Coda-inspired sequential note-pair chordification.
- **Tempo pattern:** constant, two-phase (80% for first half, target BPM for
  second half).
- **Error assessment:** error-family diagnosis or accuracy-only baseline.
- **Learner recommendation:** repeated-error policy or repeat-only baseline.

Diagnosis and learner policies are independently persisted without resetting
the current lesson. With repeated-error selected, two consistent assessed
mistakes may route automatic practice to a targeted note-isolation or timed
section-review exercise. The repeat-only baseline leaves the current lesson
unrouted. Partial work never grants original-score mastery.

The active learning passage receives additional selectable stages for eligible
rhythm and tempo drills, followed by an untouched **original** stage.
When both axes are enabled, an additional combined dotted-plus-tempo stage
is available. A rhythm rule that cannot safely transform the passage does not
create a duplicate drill. Built-in warm-ups, connections, and full-piece
performance retain original timing and do not inherit experimental mastery.

Dotted drills produce real retimed note events in the native score model and
MusicXML engraving, with unchanged pitch/source identity. Their MIDI input,
feedback and Listen WAV use those same note events. The source annotation
projector now preserves identity-bound slurs, articulation, fingering and lyrics
on eligible dotted stages. It reuses safe authored rests, tie-mark styling and
unaltered tuplet marks; note-anchored directions follow their shifted attacks.
Rhythmic beams and tuplet groupings are regenerated from the changed clock.
The pipeline refuses retiming that would alter an authored tie-chain attack
or a marked tuplet attack. The original stage remains unchanged.

Two-phase drills use `TempoMap` as the authoritative time-to-beat map for
backend deadlines, final MIDI assessment, Listen audio, Godot playhead
extrapolation and metronome ticks. Count-in uses the normal initial BPM, then
the shaped tempo begins at the first note. Stage-scoped progress keys and
independent saved sessions prevent transformed drills from granting completion
of the original stage.

**Live tempo-aware feedback and recovery:** The `timed_assessment`
adapter now shares exact per-note onset and release times with the final
grader. Shaped practice displays settled notes and expired misses against the
source-bound noteheads and applies the same five-wrong/missed-notes rolling
recovery threshold over authentic two-measure windows. Partial retries and
paused measure seeking keep their own absolute tempo-map origin; the Godot
clock receives the remaining local tempo segments. All timing judgments use
seconds, rather than pretending the passage has a single BPM.

**Verification and remaining limitations:** A short Step 3 GitHub gate now
checks imported MusicXML with beamed fast notes, tuplets, slurs, authored rests,
tied source attacks, dynamic relocation and source IDs; it also checks Listen
PCM time positions against piecewise tempo grading and Godot 4.7.2 transport
and audio-drift contracts. Run 41076832890 passed (66 Python tests, 1 skipped
before Godot installation, then the Godot-dependent settings test passed).
Complex cross-staff and multi-voice semantic notation still needs larger,
manual real-score inspection. Physical MIDI, speakers, and visual playback of
representative transformed scores require device verification before
production use.


## Remaining work to complete research systems

1. **Broaden transformed source annotation support.** Identity-anchored
   slurs, note expressions, safe rests, ties and unchanged tuplets now survive
   eligible dotted transformations. Next: complex cross-staff/overlapping
   voices, nested and overlapping tuplets, ambiguous non-note-anchored
   directions, and end-to-end pixel inspection on large real scores.
2. **Prove the timing integration on actual devices.** Timed live marks,
   five-error recovery, partial retry and pause/seek are now wired to the
   tempo map. Verify their pixel placement against real Verovio/Godot
   renderings, physical MIDI note-on/off events, latency, Listen audio and
   the metronome at tempo boundaries. Include mixed meters, fast tuplets
   and held/tied notes as independent cases.
3. **Broader Coda techniques.** Progressive source-safe part splitting,
   restricted chord-block timing, dotted rhythm and two-phase speed shaping
   are implemented. General chordification, cross-bar/multi-voice rewrites,
   pedagogically optimized pattern choice and the complete thesis algorithm
   remain unimplemented.
4. **Broader Piano Tutor remediation.** Automatic routing now exists for
   consecutive classified errors, with generated source-bound guided note
   targets and bounded timed reviews. Future work: extra-note-only evidence,
   mixed error families, interval-specific drills, personalization and
   teacher validation. Five-error immediate rewind remains a separate policy.
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

The Piano Tutor-inspired adaptation now generates source-bound remedial
exercises after repeated classified errors. It is narrower than the original
expert system and does not use a learned student model. Coda-inspired
dotted rhythm and tempo shaping now have interactive, separately graded
stages and shared timing contracts, subject to the limitations above.

For manual assessment, evaluate teacher-rated musical coherence, technical
relevance, attack/source coverage, complexity progression and, ultimately,
performance improvement on the unchanged original score at matched practice
time. These are currently experimental variants.
