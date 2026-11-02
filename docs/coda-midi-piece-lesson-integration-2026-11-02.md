# Coda MIDI — whole-piece lesson-generator architecture (2026-11-02)

## Architecture

**Input:** one imported MIDI `Piece` containing original source note
identities, timing, hands, tempo context, and measure boundaries.

```text
                     complete MIDI Piece
                             │
          select LessonGenerator for entire piece
                 ┌───────────┴───────────┐
                 │                       │
     HeuristicLessonGenerator    CodaLessonGenerator
     original focus/bridges      whole-piece note/meter analysis
     + original progression      + independent section selection
                 └───────────┬───────────┘
                             │
                 LessonPlanDefinition
                 ├─ ordered Exercise sources
                 └─ all (exercise,hand) → ExerciseStage sequences
                             │
                         LearningPlan
                   (navigation, tempo, mastery,
                    feedback and saved progress)
                             │
                 existing Score / Listen / MIDI grading
```

`LessonGenerator.generate(piece) -> LessonPlanDefinition` is the
whole-piece boundary. It receives the full original MIDI piece **once**;
neither generator receives preselected passages from `LearningPlan`.

The definition is constructed and validated before teaching starts. It owns
the ordered source passages and every hand-specific executable stage.
Its stage mapping is read-only, and the original source notes must appear
as the final stage for each playable hand/exercise. Coda-produced stages
must also have unique, source-backed MIDI attack identities.

## Implementation

- `piano_teacher/lesson_generators.py`: `LessonGenerator` protocol,
  `LessonPlanDefinition` contract, `HeuristicLessonGenerator` and
  `CodaLessonGenerator`. Unlike the previous design, this module
  constructs **complete** lesson plans and does not mutate a teaching session.
- `piano_teacher/lesson_source_planner.py`: previous source-preserving
  heuristic passage selection, bridge construction and legacy note subsets.
  No new default behavior for existing heuristic strategies.
- `piano_teacher/learning.py`: `LearningPlan` now **consumes** the
  generated definition. It no longer chooses Coda passage boundaries or
  creates stages when a student navigates to another step. The generator
  can also be injected for other research strategies and comparison.
- `piano_teacher/application/coda_midi_curriculum.py`: Coda
  Score/Part/Voice note isolation (where representable), a genuine
  half-speed tempo stage, eligible chord blocks and alternating dotted
  rhythms, and the original MIDI notes as the final stage.
- `piano_teacher/exercise_strategies.py`: the selected `coda-midi`
  setting identifies the piece-level generator, retaining the same
  Settings menu and saved strategy profile.
- `piano_teacher/server.py` and Godot practice screens continue to
  use the existing `LearningPlan`. There is **no separate Coda
  session**, special transport, Listen backend or grading implementation.

### Coda passage selection

`CodaLessonGenerator` examines the complete piece's **global attack
density, bar grid and meter changes** before choosing musical practice
sections. It uses a global density-derived target, with a maximum of
eight source measures per learning section and shorter sections when the
material is denser. It includes one terminal **complete-piece**
performance containing every original note and the full measure span.

This is currently a **bounded, independent MIDI-first planning policy**,
not a claim that Tang's original MusicXML Coda backend prescribed this
segmentation. The optional Coda rhythmic transformations still operate on
the selected source sections, but **those sections now belong to Coda's
whole-piece generator**. It can later choose entirely different exercise
lengths, ordering, repetitions or transformations without changing
`LearningPlan` or teaching transport.

### Compatibility and persistence

- Other strategies retain the existing heuristic section generator and
  original **course version 3** keys, preserving saved progress.
- The new whole-piece Coda generator uses **course version 4** keys to
  prevent stale progress from the previous passage-first Coda implementation
  from being credited incorrectly.
- Original `Piece` and MIDI note-on/off identities remain unchanged.
- Built-in warmups preserve their original hand tabs, including absent
  hand material.
- Coda is selected under **Settings → Exercise strategy**. The prior
  per-lesson `coda_try` / `coda_exit` controls remain removed.
- The normal lesson step selection, right/left/both hands, tempo ladder,
  recovery, Listen, engraving and MIDI grading consume the plan.

## Verification

`tests/test_lesson_generator_architecture.py` explicitly checks:
- Coda never calls `build_exercises` or accepts heuristic-preselected
  passages.
- Both generators receive the **entire MIDI piece**.
- A custom generator can supply an entirely different lesson sequence.
- The definition is immutable; navigation does not regenerate it.
- Existing heuristic passage boundaries and stage-key profile remain.
- Malformed definitions with missing hands or a missing original final
  stage fail before the session starts.
- A longer MIDI recording alternating sparse and dense regions generates
  **different practice-section lengths** from global piece analysis,
  covers every original note exactly once across learning sections, and
  finishes with the complete performance.

`tests/test_coda_piece_curriculum.py` also checks the normal engine,
score identity, Coda slowdown Listen and grader, strategy switching,
and built-in warmup preservation.

- [Fast application CI](https://github.com/tpepels/piano_teacher/actions/runs/41447685719): **398 passed, 6 skipped** (baseline prior to the longer new test).
- [Bounded Coda research CI](https://github.com/tpepels/piano_teacher/actions/runs/41447685621): **198 passed, 1 skipped** (baseline prior to the longer new test).
- Subsequent change-specific bounded runs must pass before the latest
  implementation should be considered checked.

**Not yet verified:** graphical native Godot + physical MIDI input on the
user's computer, exhaustive real repertoire, correctness of inferred
musical phrase boundaries, educational improvement, or exact original
Coda backend lesson-selection parity.

## Try

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
./run.sh
```

Open a MIDI piece, use **Settings → Exercise strategy → Coda · MIDI
whole-piece lessons**, and open **Lesson**. All generated sections and
stages belong to the same piece. The original complete piece remains
the terminal performance step.
