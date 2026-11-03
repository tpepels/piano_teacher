# Composable MIDI lesson generators

**Implemented:** 2026-11-02. **Main selectable strategy:** `coda-fukuda-midi`.
The new-install default is `coda-fukuda-midi`; existing saved selections are kept. Independent learner-outcome evidence is still required to support a
different choice.

## Responsibility boundaries

The `LessonGenerator` protocol owns complete whole-score analysis and returns
one immutable `LessonPlanDefinition`: ordered `Exercise` objects plus a
`(exercise.key, hand) -> ExerciseStage[]` mapping. Each stage carries an
`ExerciseVariant`, optional `TempoStrategy`, rhythm-transformation
metadata, and explicit immutable `origin`, `technique`, and
`display_name` fields. The shared teaching selector chooses by actual
source-note removals, authored timing changes, and tempo-map changes; the
application never guesses the producing algorithm from a stage-key prefix. `LearningPlan` owns navigation, BPM ladders, mastery, persistence
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

The combined policy uses **course version 3** after source-audited stage
selection. The desktop Coda-only route uses version 8; direct research
`CodaLessonGenerator()` still supplies the original excerpt contract.
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
of independent `LessonGenerator` instances. For adaptive passage curricula,
`AdaptiveComposedLessonGenerator` uses each participant's
`passage_stages(piece, original, kind=...)` interface. The composer owns the
source-preserving segmentation and selects stages by measurable musical effect.
A new generator can contribute its own stages, provenance, and technique
without adding Coda/Fukuda branches. `CodaFukudaMidiLessonGenerator` is
a configured preset of this adaptive composer, not a separate hard-coded
compiler. Its feedback hook provides any
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


## Extensibility verification (2026-11-03)

The generator registration and immutable `LessonPlanDefinition` contract
support additional MIDI algorithms and combinations without edits to the
application root. Stage metadata is producer-owned; future generators can
provide new stage labels and techniques with opaque internal stage IDs.
`lesson_stage_semantics.teaching_sequence` selects by measured reduction,
retiming, and tempo-policy differences rather than Coda/Fukuda name parsing.

`ComposedLessonGenerator.with_feedback(evidence, definition)` now forwards
the complete source-ID -> diagnostic family mapping to participants with a
`with_feedback` hook, while source-ID-only generators continue receiving
`with_mistakes`. A composer retains one unchanged original-score finale,
preserves source note identity, and uses versioned progress namespaces.
The Coda/Fukuda preset is a specialized cached curriculum using the same
stage, session, render and grading ports; its author-specific note-local
repair policy is kept inside that preset rather than the application root.

The bounded focused verification includes opaque third-party stage metadata,
generic error-aware composition, native in-process dispatcher endpoints,
source-bound notation publication, and Godot's lesson picker. Source-level
flexibility is supported by these contracts; physical MIDI timing, native
framebuffer correctness and independent learner-outcome effectiveness still
require separate acceptance. Historical Heuristic/Legacy research
strategies and offline Verovio proof utilities do not run as an alternate
network backend.


### Adaptive registration example

`register_composed_lesson_generator("my-adaptive", ("coda-midi",
"my-new-midi-algorithm"), label="My adaptive practice", version=1,
adaptive=True)` creates an ordinary selectable course and exposes its
MIDI/tempo ownership through Settings. The contributed algorithm must be
registered as a MIDI generator, implement `generate(piece)` for its
full-score research definition and `passage_stages(piece, original,
kind=...)` for bounded teaching. The passage method must end in an exact
original stage. The immutable course validator checks IDs, notes, hands,
timing boundaries and the unchanged final performance.

The named Coda+Fukuda preset now uses those same contributor methods:
nothing in `adaptive_hybrid_curriculum.compile_hybrid_catalog` imports
or calls an algorithm-specific stage builder. Its local Fukuda
source-ID relevance filter remains a specialized option; the general
stage selector works on actual removed notes, written timing differences
and tempo policies, irrespective of author name. Generic composers
forward the full source-ID/error-family mapping when a participant
implements `with_feedback`.
