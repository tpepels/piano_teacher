# Coda MIDI: original excerpt catalog and teaching adapter

**Updated 2026-11-02 — pinned source verified.**

## What Coda actually implements

The original author backend
[`annieetang/coda_backend@a4eb85df`](https://github.com/annieetang/coda_backend/tree/a4eb85dfc2bd418818ca9ff775c0a11ccccb3530)
does **not** choose a sequence of practice passages or progression levels.

- [`api/endpoints.py` `/generate`](https://github.com/annieetang/coda_backend/blob/a4eb85dfc2bd418818ca9ff775c0a11ccccb3530/api/endpoints.py#L215-L240):
  accepts `filename`, `start_measure`, `end_measure`. It passes the
  selected excerpt to `get_all_exercises`, filters missing output and
  returns a category catalog.
- [`music/exercise.py`](https://github.com/annieetang/coda_backend/blob/a4eb85dfc2bd418818ca9ff775c0a11ccccb3530/music/exercise.py#L16-L48):
  returns the original Score, Part, Voice plus dotted, chordified and
  slowed-down voice exercises.
- [`ExerciseLine.generate_exercises`](https://github.com/annieetang/coda_backend/blob/a4eb85dfc2bd418818ca9ff775c0a11ccccb3530/music/exercise.py#L230-L263):
  requests **both** dotted patterns (3:1, 1:3), **all** source-defined
  automatic chord widths, and slowed-down factors **2 and 4**.
- [Coda frontend](https://github.com/annieetang/coda_app/blob/main/frontend/script.js):
  reads selected start/end measure controls, calls `/generate` and
  presents categorized cards for a user to choose. It has no automatic
  teaching-path algorithm.

**Verification:** The bounded
[pinned-source contract workflow 41450764682](https://github.com/tpepels/piano_teacher/actions/runs/41450764682)
checks the real source AST and source-defined catalog parameters
against our independent `coda_author_catalog.py`, without mistaking
the *absence* of an upstream lesson planner for a missing feature.

## Current MIDI application

```text
                    MIDI source Piece
                           │
                CodaLessonGenerator
           caller-selected measure excerpt
             (default = entire piece)
                           │
                 Coda category catalog
         Score / Part / Voice / Dotted /
             Chordified / Slowed Down
                           │
               APPLICATION teaching order
         (source voice, eligible alternatives,
          slowdown x2/x4, source part,
          terminal original score)
                           │
                 LessonPlanDefinition
                           │
                       LearningPlan
         ordinary notation / Listen / grading
```

- The **whole MIDI piece** is the default excerpt; no heuristic
  density-based 2–8-measure segmentation is invoked by Coda.
- `CodaLessonGenerator(first_measure=N,last_measure=M)` supports
  selecting an explicit authored MIDI measure range programmatically.
  This option is **not yet an additional Godot UI control**.
- The builder checks note identities and source boundaries; if a held
  note crosses an explicitly selected excerpt endpoint, it rejects
  rather than inventing a new attack or clipping a release.
- `piano_teacher/research/coda_author_catalog.py` encodes all six
  source categories, the two dotted patterns, the automatic chord-level
  formula (including the author's potentially invalid zero width) and
  both slowdown factors. This is a **request schema**, not proof that
  every operation returns a playable exercise.
- `application/coda_midi_curriculum.py` generates voice-related stages
  where MIDI timing can be represented safely, attempts every automatic
  chord width and both dotted patterns, and adds x2 and x4 slowdown
  playback stages. Unchanged or unsupported variants are omitted,
  without copying known upstream bugs. The `both` hand route retains
  the complete original Score Level.
- **The order in which our application presents these alternatives is
  explicitly our own teaching policy.** Coda's published backend has
  no corresponding automatic order to reproduce.
- A terminal normal-performance stage is also our teaching policy.
  Our MIDI piece, source identities, default practice controls,
  notation/Listen/feedback/grading and course progression remain
  owned by the normal `LearningPlan`.
- New catalog-shaped Coda course keys use **version 5**, preventing
  previous passage-first/v4 Coda mastery being credited to a different
  exercise arrangement. Existing non-Coda version-3 keys are unchanged.

## Parity and limits

| Property | Status |
|---|---|
| Published author endpoint's caller-selected score excerpt model | Source-verified |
| Original six Score/Part/Voice/Dotted/Chordified/Slowed Down category labels | Source-verified |
| Dotted patterns, chord-width formula, slowdown parameter set | Source-verified |
| Full MIDI piece as default input excerpt | Implemented as app default |
| An author's automatic lesson/section selection policy | **Does not exist** |
| App-generated teaching order | **Application-specific**, not upstream parity |
| MusicXML-written note-level output parity for every variant | **Not claimed**; prior strict research subset only |
| MIDI chord width derived from MusicXML notation shortest duration | **Different:** MIDI PPQ-exact grid used |
| Slowdown written notation output | **Different:** equivalent constant slower BPM for MIDI |
| Real device audio/MIDI and full graphical Godot session | Not verified in this change |

## Bounded tests

- [Source-AST verification 41450764682](https://github.com/tpepels/piano_teacher/actions/runs/41450764682):
  passes at the pinned original SHA and retains a machine-readable
  artifact.
- [Coda research and whole-excerpt tests 41450885983](https://github.com/tpepels/piano_teacher/actions/runs/41450885983):
  **203 passed, 1 skipped**.
- [Application regression 41450885883](https://github.com/tpepels/piano_teacher/actions/runs/41450885883):
  **398 passed, 6 skipped**.

The earlier report's assertion that Coda had an independently reproduced
global-density lesson segmentation algorithm was incorrect. It has been
removed. Those tests now assert one entire-score excerpt and an explicit
caller-selected measure range instead.

## Try

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
./run.sh
```

Open a MIDI file and choose **Coda · MIDI whole-piece lessons** in
Settings. The lesson path presents the generated alternatives for that
complete piece, with the original score as its final performance.

The original source has no automatic curriculum ordering. To develop a
genuinely automatic pedagogical lesson selector, that must be designed
and evaluated as a **separate product algorithm**, not called original
Coda parity.
