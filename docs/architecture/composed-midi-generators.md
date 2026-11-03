# MIDI exercise generator architecture

**Technical contract only.** Phase status, priorities and completion gates are
defined exclusively in [ROADMAP.md](../../ROADMAP.md).

## Immutable source contracts

A registered `LessonGenerator` receives a canonical imported MIDI `Piece`
and returns a `LessonPlanDefinition`: ordered exercises, source-safe
`ExerciseStage`s per hand, and one unchanged final whole-piece performance.
`LearningPlan` owns navigation, tempo ladder, stage identity and mastery.
`PracticeEngine` owns commands, transport and assessed results, not the
algorithm-specific transformations.

Stages carry `ExerciseVariant`, source MIDI IDs and optional rhythm/tempo
changes. `origin`, `technique`, `display_name` are producer-owned metadata.
The selector measures retained notes, timing, pitch/dynamics and effective
tempo; it does not decode generator-name prefixes.

## Generator composition

- `ComposedLessonGenerator` combines independently registered complete
  whole-piece curricula with source-ID and hand checks.
- `AdaptiveComposedLessonGenerator` compiles passage stages from each
  participant's `passage_stages(piece, original, kind=...)`. Its common
  passage/bridge policy selects meaningful transformations without importing
  Coda/Fukuda-specific stage builders.
- `CodaFukudaMidiLessonGenerator` is a preset of the adaptive composition.
  It compiles Coda dotted/chord/slowdown and Fukuda MIDI-source reductions,
  selects a small purposeful sequence, responds to graded source-note
  errors, and ends at the unchanged original MIDI.
- `register_composed_lesson_generator(..., adaptive=True)` registers a new
  selectable adaptive combination; versioned course/stage keys isolate saved
  progress. Custom contributors may use opaque stage IDs.
- `with_feedback(evidence, definition)` is the only generator feedback
  interface. Contributors receive graded source-ID error families and can
  select musical transformations using whichever error distinctions matter.
  Unknown generators fail at registration/selection rather than silently
  falling back to a heuristic course.

The desktop `coda-midi` strategy uses bounded source-safe passages.
Direct `CodaLessonGenerator()` is the research contract for the pinned
original author-style requested excerpt. The new-install product default is
`coda-fukuda-midi`; explicitly saved user selections remain unchanged.

## Validation and current limitations

Source-identity-preserving generation, stage uniqueness, score/Listen/grader
projection, registration, and source-local feedback are covered by focused and
corpus suites. These results predate the latest canonical engraving + native
typed IPC refactor and **must be rerun** before accepting the current build.

Passing generation contracts does not prove that the live Godot score is
visible at READY, that real audio/MIDI timing is aligned, or that combining
the algorithms teaches better. See [the only active roadmap](../../ROADMAP.md)
for the required native/physical/learner-study gates.

Historical implementation and differential evidence:
[original Coda Phase 3](../coda-midi-phase3-completion-2026-11-02.md),
[Fukuda MIDI Phase 4](../fukuda-midi-phase4-2026-11-02.md), and
[physical MIDI verification](../verification/coda-fukuda-physical-midi-checklist.md).
