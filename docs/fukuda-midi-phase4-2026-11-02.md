# Phase 4: Fukuda (2015), MIDI-only implementation

**Date:** 2026-11-02. **Status:** Phase 4 implementation integrated and bounded-test verified; full research replication and physical MIDI verification still open.

## Author reference and mandatory input constraint

T. Fukuda, Y. Ikemiya, K. Itoyama and K. Yoshii (SMC 2015),
[A Score-Informed Piano Tutoring System with Mistake Detection and Score
Simplification](https://sap.ist.i.kyoto-u.ac.jp/EN/bib/intl/FUK-SMC15.pdf),
§3.1–3.4, figures 4–6.

The original system records **piano audio** and derives note candidates from
24-bin-per-octave CQT and an 88-note supervised `β=0.6` NMF basis trained
on the same acoustic piano. It aligns audio/score chroma using DTW,
suppresses spurious acoustic octave harmonics, detects performance mistakes
and simplifies the failed score sections.

**This product takes only MIDI input: imported MIDI scores and performance
note-on/note-off events from a MIDI keyboard or performance MIDI file.**
There is no microphone recording, acoustic spectrum, CQT, supervised
NMF, pretrained piano-sound library or pitch-harmonic octave-error filter.
Building those would create an unused parallel audio input subsystem and
contradict the requested MIDI-only architecture.

A played wrong octave is a **real incorrect MIDI pitch**, not an
acoustic transcription artifact, so it must never be silently ignored.

This is a **source-informed MIDI adaptation**, not exact recreation of the
author's audio transcription system. The three rules are implemented from
the paper's description, which does not specify enough numeric thresholds
or MIDI note-identity conventions to assert an exact reference parity
certificate.

## Whole-piece teaching integration

- `piano_teacher/lesson_generators.py`:
  `FukudaMidiLessonGenerator.generate(piece) -> LessonPlanDefinition`;
  receives the complete original MIDI piece, emits the full-score learn
  and final-performance exercises through the normal lesson contract.
- `piano_teacher/exercise_strategies.py`: selectable
  **Fukuda · MIDI adaptive simplification** (`fukuda-midi`).
  It does not borrow the old partially implemented `fukuda` generator
  or inherit its stage progress; new stages have course key version 4.
- `piano_teacher/fukuda_midi.py`: all three score simplification families,
  deterministic MIDI-onset chroma and offline DTW, source-ID mistake
  classification and selection of original source notes for each stage.
- `piano_teacher/fukuda_mistake_store.py`: atomically stores MIDI source
  IDs and counts from **actually graded original-score takes**.
  Correct notes clear their errors; different imported scores remain
  isolated by source SHA-256. Simplified exercises cannot clear missing
  notes from the full source.
- `piano_teacher/learning.py`:
  `LearningPlan.update_fukuda_mistakes()` regenerates its immutable
  whole-piece stage definition after a graded original take without
  transferring mastery to new stages or losing the unchanged original.
- `piano_teacher/server.py`: observes graded original MIDI take results,
  persists the score-level mistake IDs, refreshes the Fukuda plan and
  score revision, restores the same evidence after restarting/opening
  the piece, and resets Fukuda errors when the piece path is explicitly
  reset. All other strategies preserve their existing behavior.
- `piano_teacher/preprocessing_cache.py`: repairs a pre-existing bug
  that dropped `Piece.source_format` and `midi_ticks_per_beat` on
  cache hits. Cache schema bumped to invalidate incomplete data. This
  matters for **both** Coda and Fukuda whole-piece MIDI strategies.

### Three simplification rules

| Paper pattern | Implemented MIDI transformation | Source-safety rule |
|---|---|---|
| 1. Difficult simultaneous chords | Remove intermediate pitches from chords; keep bottom/bass and top/melody attacks | No pitch retiming; all kept notes preserve source IDs |
| 2. Rapid fingering passages | Thin eligible alternating notes in a fast same-voice run | Keep endpoints, avoid overlapping voices and prominent upper melodic peaks; author's own evaluation warned of damage to melody |
| 3-A. Large returning octave leap | Remove a middle note that jumps over an octave away and back | Leave adjacent source notes and their timing untouched |
| 3-B. One-way octave leap | Apply a nearby chord or fast-run simplification only in the leap's local neighborhood | Never simplify a remote chord simply because some other part of the piece has a leap |

Stage order is app-defined. Every generated source-filtered stage uses
the ordinary MusicXML engraving generated from MIDI, Listen, MIDI
matching, source-note progression, mastery and saved stage keys.

When no real errors are stored, the initial course offers the unchanged
original score. Graded mistakes on the original add eligible simplified
practice stages. Once corrected, the corresponding failed source note
IDs are cleared and those stages can be removed, always retaining the
original complete-performance exercise.

### MIDI DTW and comparative diagnostics

- `align_midi_dtw()` uses a monotone dynamic program over 12-pitch-class
  MIDI onset vectors with cosine similarity, normalized temporal prior
  and explicit insertion/deletion allowances.
- `detect_midi_mistakes()` maps matched score onsets to real MIDI
  pitches and reports missed/wrong/timing/extra events without applying
  the paper's **acoustic-only** octave-artifact suppression.
- `piano_teacher/fukuda_midi_performance.py` parses real recorded MIDI
  note-on/off events, including MIDI tempo changes, into seconds; it
  fails closed on orphan or unreleased MIDI notes.
- `python scripts/analyze_fukuda_midi.py --score original.mid
  --performance recorded.mid --report results.json` performs offline
  actual-MIDI-vs-source DTW analysis.

**Important:** The LIVE teaching engine uses its existing canonical
MIDI transport and assessment clock, not a separate DTW grading clock.
DTW is used for independent offline freely timed MIDI diagnostic
comparison. Introducing a parallel live grader would violate the
single-authoritative-timeline requirement and risks contradictory
feedback.

## Validation

- `tests/test_fukuda_midi_phase4.py`: rule families, source note identity,
  onset chroma DTW with expressive tempo, real wrong-octave detection,
  missing/extra MIDI events, stored per-note mistakes and recovery,
  whole-piece strategy selection, score/Listen/grading per rule,
  real `PracticeEngine` original-take-to-adaptive-stages-to-reopen/reset,
  and recorded MIDI performance analysis.
- Bounded dedicated CI:
  [Phase 4 Fukuda MIDI](https://github.com/tpepels/piano_teacher/actions/workflows/fukuda-midi-phase4.yml),
  short test job and all existing exercise/whole-piece architecture
  contracts.
- Existing fast application regression:
  [Piano Teacher fast checks](https://github.com/tpepels/piano_teacher/actions).

## Run

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
./run.sh
```

Choose **Settings → Exercise strategy → Fukuda · MIDI adaptive
simplification**. Open a source MIDI score. Attempt the original score;
source-identified mistakes can introduce the matching simplified stages
in the ordinary lesson path. Retry and improve the original; a subsequent
correct original attempt clears those error IDs. No native library rebuild
is necessary for the Python-only changes.

Optional offline diagnostic for an independently recorded MIDI take:

```bash
.venv/bin/python scripts/analyze_fukuda_midi.py \
  --score score.mid --performance recorded.mid \
  --report /tmp/fukuda-mistakes.json
```

## Remaining Phase 4 acceptance gaps

1. **Original-paper reproduction** beyond the described MIDI adaptation:
   the paper's acoustic transcription/numeric algorithms cannot be
   reference-reproduced in a MIDI-only product. The original score-rule
   thresholds and figure-level exact expected note outputs need an
   independently specified benchmark before scientific equivalence
   could be claimed.
2. **Native interactive hardware**: complete Godot 4.7.2 graphical
   path plus physical MIDI keyboard, stage changes after assessments,
   meaningful error feedback and musical appropriateness must be
   checked locally. Software tests alone do not certify player behavior.
3. **Free-time MIDI score following inside the live session**: the
   current DTW is a recorded-performance analysis, not the canonical
   live transport clock. Any live score-following feature would need
   integration into that same transport owner and independent latency
   and accuracy tests.

These gaps keep the phase open; a working subset of transformations is
not a full experimental reproduction certificate.
