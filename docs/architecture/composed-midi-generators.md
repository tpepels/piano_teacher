# Composable MIDI lesson generators

**Implemented:** 2026-11-02. **Main selectable strategy:** `coda-fukuda-midi`.
The default remains `coda-midi` until learner-outcome evidence supports a
different choice.

## Responsibility boundaries

The `LessonGenerator` protocol owns complete whole-score analysis and returns
one immutable `LessonPlanDefinition`: ordered `Exercise` objects plus a
`(exercise.key, hand) -> ExerciseStage[]` mapping. Each stage carries an
`ExerciseVariant`, optional `TempoStrategy`, and rhythm-transformation
metadata. `LearningPlan` owns navigation, BPM ladders, mastery, persistence
identity and resumption. `PracticeEngine` only settles original-note
assessments, stores their source IDs, and sends the complete frozen error set
to generators that implement `with_mistakes(ids, current_definition)`.
It does not branch on algorithm names to select curriculum or refresh errors.

`LessonGeneratorRegistration` binds generator factory, MIDI applicability,
tempo ownership and course-key version. `register_lesson_generator` registers
new generators and can also expose a selectable strategy via `label`.
`LearningPlan` resolves via that registry; unregistered existing heuristic
strategies use the general heuristic generator. Adding an independent
whole-piece generator no longer requires editing the central `LearningPlan`
or practice engine. The immutable output validator enforces complete
source-score terminal notes, unique stage IDs, hand ownership, passage
bounds and source MIDI IDs. Existing saved strategy profile namespaces
remain distinct.

## Reusable combination policy

`compose_lesson_definitions(primary, augmentation, ...)` combines arbitrary
complete lesson definitions, preserving the primary original-score
performance and original MIDI source IDs. Exercises may share stages only
when the entire source note multiset, hand schedule, kind and passage
boundaries are equal. Nonmatching focus exercises are inserted separately.
Extra original performance exercises are validated then de-duplicated.
Colliding keys, stage levels and changed terminal source scores fail closed.

The registered Coda + Fukuda policy:

1. Generate the **complete original Coda whole-piece** score/part/voice,
   both dotted families, all chord widths and 2×/4× slowdown stages.
2. Generate **all applicable Fukuda score-reduction rules** over the same
   whole source and compose them before Coda's practice stages for each hand.
3. On graded original-MIDI mistakes, add **source-specific Fukuda repairs**
   ahead of the existing whole-source lessons. The user's learned Coda
   stages are not removed.
4. End with exactly one original MIDI performance, with no research
   simplifications carried into the final source.
5. Cache the immutable combined full-piece core across mistake updates:
   Coda and whole-score Fukuda are **not re-generated** on each graded
   attempt. Only changed remedial sections are rebuilt. When a new repair
   appears, navigation opens its first stage instead of skipping the
   reduction by jumping to its terminal original exercise.

All generated stages use ordinary native score engraving, Listen playback,
MIDI timing/grading and persistent progress. The composed strategy uses its
own **course version 1**, so it cannot inherit unrelated completion or BPM
credit from Coda-only version 6 or Fukuda-only version 4.

## Validation

- [Bounded selectable strategies, registration, composition, source-identity,
  graded-feedback, persistence, SVG/Listen/grading checks](https://github.com/tpepels/piano_teacher/actions/workflows/composed-midi-lessons.yml)
- [Original-Coda pinned algorithm differential](https://github.com/tpepels/piano_teacher/actions/runs/41485239072)
- [Independent Fukuda original-MIDI behavior](../fukuda-midi-phase4-2026-11-02.md)

The composition does not establish improved teaching effectiveness. Combining
two valid exercise-generation policies can produce redundant or poorly ordered
exercises; user-controlled selection and a future human assessment are required
to choose a pedagogically superior default.


## Extending without adding application branches

The generalized `ComposedLessonGenerator` accepts an ordered collection
of independent `LessonGenerator` instances. The named Coda/Fukuda preset
is a configuration of this same class. Its feedback hook provides any
participant that implements `with_mistakes` with source-identified MIDI
mistakes; new source-specific repair exercises are composed before the
preserved core. The generic `register_composed_lesson_generator` entrypoint
takes any registered generator IDs, a new strategy ID, optional UI label,
and a version for isolated progress keys. Registration also includes
MIDI-only applicability and ownership of the exercise's tempo/rhythm.

`available_strategies()` supplies `owns_timing` and `midi_only`
capability fields. Settings disables independent timing/tempo policies for
**any** registered generator that owns those decisions, including dynamically
installed compositions; the UI no longer special-cases the string
`coda-midi`.
