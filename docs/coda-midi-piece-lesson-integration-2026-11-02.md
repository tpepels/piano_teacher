# Coda MIDI — piece-level lesson-generation integration

**2026-11-02.** Active implementation of MIDI-input Coda lesson generation.

## Product behavior

The user selects a **MIDI piece** and, in Settings, selects the
**Coda · MIDI whole-piece lessons** exercise-generation strategy. It is the
default for new installations and for stored preferences that referenced the
former `coda-part` picker option; explicitly selected other available
strategies remain respected.

The normal `LearningPlan` builds a course for the **entire piece**. Its
source passage selection continues to use the existing adaptive focus/bridge
and complete-performance sequence, based on original MIDI measure boundaries.
Coda does **not** replace that phrase-boundary algorithm yet. Within each
normal piece passage and selected hand, it generates:

1. Coda source **Voice / Part** isolations when the source MIDI has distinct
   playable voice groups.
2. A **slowdown ×2** stage using a half-speed tempo map; writing and MIDI
   note positions remain on the same source measure grid.
3. Eligible **chord-block** and **dotted rhythm 3:1 and 1:3** stages
   using the original MIDI PPQ-exact compact quantization and the
   independently verified research transformations. Unsafe/unrepresentable
   groupings are omitted rather than forced.
4. The **complete original notes** for that source passage as the last
   stage. Bridges and full-piece performances remain original by design.

All generated `ExerciseStage` objects live inside the *same*
`LearningPlan` as the original source. They keep original MIDI note
source IDs, piece ownership, practice navigation, transport deadlines,
MIDI grading, Listen, notation, mastery and persistence. They have a
distinct `coda-midi` stage-key profile, so other strategy progress is not
credited accidentally.

No intermediate `LearningPlan` is created for a single temporary
exercise. The older `coda_try` / `coda_exit` commands, backend trial
class, and three Lesson screen buttons have been removed, including their
tests.

## Architecture

- `piano_teacher/exercise_strategies.py`: the `coda-midi` generator
  is a real piece-selectable strategy, displayed in Settings. No separate
  per-passage Coda menu.
- `piano_teacher/learning.py`: for that strategy, its existing passage
  and hand navigation invokes `application/coda_midi_curriculum.py`,
  producing the normal course stages. Warmups retain their fixed original
  progression.
- `application/coda_midi_curriculum.py`: source voice/part decomposition,
  safe reference-based dotted and chord transforms, half-speed tempo policy,
  original-source terminal stage. The same full-piece `Piece` remains
  authoritative, including each phrase's absolute source beat coordinates.
- `piano_teacher/library.py`: new preferred/default strategy and automatic
  reset of independently selected timing/tempo strategies on Coda selection.
  The application refuses a second independent rhythm or tempo transformation
  while Coda is selected; Godot disables those Settings controls accordingly.
- `piano_teacher/server.py`: **no Coda-specific trial session or control
  route**. Opening, selecting, listening, practicing, grading, recovering,
  persisting, and replaying Coda stages uses existing engine ownership.
- `godot/lesson_screen.gd`: no temporary Coda buttons.
  Navigation remains the same Lesson Path and Play/Retry/Listen interface.

## Tests / scope

- `tests/test_coda_piece_curriculum.py` checks piece-selected Coda
  source identity, full lesson step generation, multiple source
  passages, original terminal stages, per-stage half-speed Listen,
  standard note grading, Settings strategy switching, and warmup behavior.
- `tests/test_library.py` checks default and old-preference mapping,
  per-strategy profile isolation and forbidden duplicate timing.
- `tests/godot/coda_piece_strategy.gd` confirms the Coda strategy is
  displayed and selected in Settings, the two independent rhythm/tempo
  policies are disabled, and the Lesson screen has no trial control.
- Bounded CI: fast desktop contract gate, Coda research contracts and
  Godot 4.7.2 syntax/behavior suite. No lengthy workflow or remote
  original-author research was required.

**Boundaries:** The source-passage segmentation still comes from the
existing teaching planner; Coda supplies the note hierarchy and rhythmic
progression within those passages. This implementation is meant to be
tried in the live application. Native full graphical/MIDI hardware
behavior on the user's device remains unverified.

## Run

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
./run.sh
```

Open a MIDI piece. In **Settings → Exercise strategy**, select
**Coda · MIDI whole-piece lessons** if it is not already selected.
Return to **Lesson** to see the generated stages for the piece. Use
normal stage navigation and Play, Listen and Retry.

See [MIDI-first issue #43](https://github.com/tpepels/piano_teacher/issues/43)
for ongoing MIDI/hardware and more sophisticated passage-selection work.
