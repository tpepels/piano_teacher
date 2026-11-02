# Composable MIDI lesson generators

**Implemented:** 2026-11-02. **Main selectable strategy:** `coda-fukuda-midi`.
The new-install default is `coda-fukuda-midi`; existing saved selections are kept. Independent learner-outcome evidence is still required to support a
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

The selectable **Coda + Fukuda · MIDI combined lessons** now uses a
progressive, error-aware application teaching policy, separate from the
pure, published Coda algorithm catalog:

1. Split the original imported MIDI piece into manageable focus passages,
   normally one or two measures. Sparse passages can expand to eight.
   Extend passages when a sounding note crosses their final barline, so
   no source MIDI note is truncated or duplicated. Add bridge exercises
   between adjoining passages when they have attacks on both sides.
2. Compile **every available Coda dotted, chord and slowdown** candidate
   and all **Fukuda chord, fast-note and leap** reductions for each
   applicable source hand once. These form an immutable full candidate
   catalog. The pure Coda-only strategy still provides the author's
   full-score exercise catalog, unchanged by this product sequencing.
3. Start each passage with a small supported set of simple exercises,
   followed by its exact original notes. After graded original-note
   mistakes, select source-matched Fukuda reductions for wrong/missed
   pitches, Coda dotted exercises for timing errors and Coda slowdown
   stages for early releases or excessive sustain. Mixed-error stages
   combine the relevant candidates.
4. The complete original piece remains the sole final performance step.
   No simplified pitches, altered rhythm or slowdown can be credited as
   successful performance of the original.
5. Replanning updates only the selected stage sequences; full Coda/Fukuda
   candidate compilation is cached. Preserve unchanged source-derived
   mastery, per-stage tempo, streak and the selected stage. After a
   failed original take, focus the appropriate source passage and
   introduce the relevant adaptive scaffold. Completed feedback can
   remove unneeded stages without reinterpreting unrelated progress.

The combined policy now uses **course version 2** because the original
version-1 whole-piece stage route is replaced by a passage-based route.
Saved Coda-only and Fukuda-only progress remains isolated; no incompatible
whole-piece mastery is silently applied to the new lesson structure.

Read [adaptive workflow and acceptance evidence](adaptive-coda-fukuda-workflow.md)
for the full route, feedback ownership and unresolved hardware validation.

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
of independent `LessonGenerator` instances. The named Coda/Fukuda strategy is a specialized subclass which supplies
its own progressive passage and error-selection policy. Its feedback hook provides any
participant that implements `with_mistakes` with source-identified MIDI
mistakes; the combined strategy chooses source-specific existing passage stages
from the cached catalog, without rebuilding the original-score candidates. The generic `register_composed_lesson_generator` entrypoint
takes any registered generator IDs, a new strategy ID, optional UI label,
and a version for isolated progress keys. Registration also includes
MIDI-only applicability and ownership of the exercise's tempo/rhythm.

`available_strategies()` supplies `owns_timing` and `midi_only`
capability fields. Settings disables independent timing/tempo policies for
**any** registered generator that owns those decisions, including dynamically
installed compositions; the UI no longer special-cases the string
`coda-midi`.


## Additional completed refactor

The Coda/Fukuda preset now subclasses the general-purpose
`ComposedLessonGenerator`, rather than owning its own independent
composition engine. `register_composed_lesson_generator(name, members,
label, version)` accepts any already registered whole-piece generator
IDs and constructs the combined policy from those factories. Duplicate
IDs, unknown components and self-referential compositions fail closed.
All compositions emit ordinary immutable exercise stage definitions.
The selected generator's capabilities, including `owns_timing` and
`midi_only`, are advertised through the Settings API and consumed
directly by the native Godot strategy controls.

The separate offline MIDI-performance analysis improves note-off
handling and matching speed, while the live application retains
its one authoritative playback/assessment clock. See the
[completed MIDI-only Fukuda implementation](../fukuda-midi-phase4-2026-11-02.md).


## Desktop selection vs research-author generator

The registered `coda-midi` desktop course uses source-safe focus passages
and filters objectively unchanged/duplicate stages. Direct
`CodaLessonGenerator()` is reserved for the author-style complete-excerpt
research contract. The combined `coda-fukuda-midi` course retains all
source candidates in its immutable catalog but selects a bounded ordered
lesson using measured note/timing/tempo differences. Its current source-ID
error evidence drives adaptive Coda/Fukuda stage selection. Both routes end
with unchanged original MIDI notes. The stage provenance is carried to
`state_projection`, lesson overview and the Godot practice/step-picker UI.
