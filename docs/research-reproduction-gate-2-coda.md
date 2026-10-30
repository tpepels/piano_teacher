# Research reproduction — Gate 2: Coda symbolic system

2026-10-30. Branch: `main`. Status: **partial, reference parity NOT established**.

## Source record

Annie Tang, *Coda: A Digital System for Generation of Piano Practice
Exercises from Symbolic Music Notation* (Dartmouth undergraduate thesis,
June 2025), https://digitalcommons.dartmouth.edu/cs_senior_theses/76/.

The institutional abstract explicitly describes a Music Matrix
Representation (MMR) with Score–Part–Voice hierarchy and four exercise
families: **Part Splitting, Tempo Shaping, Chordification, and Dotted
Rhythms**. The download endpoint returned HTTP 403 from our available
source and a public implementation/algorithm reference could not be
verified. The abstract alone does not specify transformation formulas,
grouping heuristics or their reference examples. Therefore do not call
these methods an exact recreation. Obtain the complete thesis and
reference source before accepting research fidelity.

## Implemented this increment

- `piano_teacher/research/coda_matrix.py`:
  immutable `MatrixScore` / `MatrixPart` / `MatrixVoice` /
  `MatrixAttack` partition, preserving imported attack IDs, original
  track/channel/voice, measure ownership, pitches and key releases.
  `verify_lossless()` independently verifies that each original attack
  occurs **exactly once** with identical musical facts.
- `piano_teacher/research/coda_polyphony.py`:
  independent **experimental** per-voice adjacent-chord transformation,
  returning a `TimingPlan` and explicit decisions. Distinct voices
  (including both hands) can be transformed independently, including
  existing multi-pitch chords. Refuses repeated-pitch collisions,
  incompatible durations, overlapping events and cross-bar grouping.
  Retains original `ExerciseVariant` and source identities. Protects
  authored ties, tuplets, slurs and beamed anchors when original XML is
  supplied. **Not enabled in production strategy settings.**
- `piano_teacher/notation/rhythm_safety.py`: independent detector of
  source-authored beam anchors for chordification eligibility.
- `tests/test_coda_matrix_research.py`: checks synthetic two-hand
  polyphony, cross-bar/duplicate sources, five checked-in MusicXML
  cases, authored beams and exact timing identity, in routine fast CI.

The production `coda-part` and `coda-chord-blocks` options still
represent the previously documented *limited adaptations*. They are
not relabeled research-complete by this work.

## Remaining Coda gates

- [x] Base lossless source-backed Score/Part/Voice attack hierarchy.
- [x] Standalone cross-voice-capable chordification prototype with
      reversible mapping and source-annotation safety.
- [ ] The **complete published MMR**, including authored rests, voices
      spanning measures, articulation/directions, notational tuplets,
      meter/key changes and compositional grouping, with reference parity.
- [ ] Full chordification eligibility and combinations **as documented in
      the original Coda thesis**, with reference example parity.
- [ ] Complete part-splitting algorithm matching author examples.
- [ ] Complete tempo-shaping patterns and exact beat/second playback
      integration across Learn/Listen/grading.
- [ ] Complete dotted-rhythm transformations, including polyphony, rests,
      tie segmentation, and notation-level reference examples.
- [ ] Independent non-vacuous real-score correctness/performance benchmark,
      real Godot view and MIDI hardware verification.
- [ ] Controlled learner/teacher evidence of original-score learning gains.

No claim of exact Coda reproduction or verified pedagogy is justified.
No long-running full-corpus audits or background work were initiated.

## Follow-up: written-rest source sidecar

- The matrix now optionally accepts original MusicXML and records authored
  rests using immutable `MatrixWrittenRest` events. Every rest retains its
  source XML ordinal, part/staff/voice, selected measure, onset, duration,
  written note type, dots, visibility and whole-measure designation.
- Backup/forward moves and MIDI release gaps never create authored rests.
  Rest-only voices remain explicitly identified by their source XML voice;
  no hand or synthetic MIDI attack is invented.
- The MusicXML source must have a complete selected measure grid; invalid
  divisions, negative cursors and rests outside that grid fail closed.
- Tests cover mixed voices, hidden rests, a division change, measure-relative
  extraction and real imported MusicXML.
- **Not accepted as full MMR**: XML rest events are an explicitly separate
  source-notation sidecar, not yet integrated into the MMR's part/voice
  transformation rules. Other source annotations and Coda reference parity
  remain open. No production behavior is switched on.


## Follow-up: written rests become voice-owned transformation constraints

- Pitch-bearing `MatrixVoice` objects now attach exact authored rests
  by imported source part/staff/voice identity; `rest_only_voices` groups
  remaining rests without inventing hand ownership or MIDI attacks.
- `verify_lossless()` checks that every authored rest appears exactly once
  across attached and rest-only voice groups, alongside pitched attacks.
- The experimental `PolyphonicChordifier` now passes original MusicXML
  to the matrix and refuses pairing when an authored rest in that same voice
  overlaps the candidate block. Unrelated rests in other voices and later
  rests do not inhibit eligible note pairs. The rest sidecar never changes.
- Fast tests cover cross-voice isolation, rest-only provenance,
  conflicting same-voice intervals, and a real MusicXML fixture.
- These are **conservative engineering guards**, not yet a reproduction
  of Coda's published rhythm-transformation rules. Production remains
  unchanged, and the full symbolic metadata graph remains incomplete.

## Source-notation inventory (research-only)

- New `coda_source_metadata.py` records **every direct MusicXML measure
  element** by original part/measure/ordinal ID, ordered source position,
  voice when explicitly knowable, and complete XML subtree. This retains
  source key/meter/clef changes, directions, articulations, slurs, ties,
  beams, tuplets, lyrics and unknown markup without reinterpreting them.
- Selected later measures inherit divisions; chord timing and backup/forward
  cursor behavior are retained. The score matrix validates rest identities
  against the independent written-rest ledger.
- This is a source-aware **inventory**, not a transformed score or full MMR:
  linked slur/tie graphs, expressive offsets, score-wide global metadata,
  cross-staff routing and arbitrary MusicXML playback semantics still require
  independent verification. No new annotation is silently applied to a
  transformed exercise.

## Research-only transformation contracts (not reference parity)

- `coda_research_strategies.py` includes deterministic source-measure
  splitting with source-index reassembly and conservative held-note/slur/tie
  boundary rejection. Rest-only measures remain represented.
- Measure-wise tempo steps generate an existing shared `TempoMap` so
  `assess_timed` can consume the *same* beat-to-second conversion used
  for demonstration. Playback/Listen GUI integration is still pending.
- Independent voice-level 3:1/1:3 dotted timing supports chords and
  polyphonic voices without changing source identity; written rests,
  authored beams, ties, tuplets and expressive note marks are guarded.
- Focused synthetic and MusicXML contracts cover source partitions,
  tempo conversion/grading, polyphony and protected annotations.
- These are **new research prototypes only**. No production strategy is
  enabled or described as a faithful Coda implementation.
