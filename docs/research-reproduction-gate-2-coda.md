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

- Strict source-grid checks now reject missing internal measure boundaries
  rather than mislabeling sections or retiming across an unknown bar.
- Passage splitting conservatively rejects connector links spanning a cut,
  including slurs that began before the current selected phrase. Duplicate
  MusicXML tie/tied declarations are treated as one connector.

## Continuation after the native-notation detour (2026-10-30)

The research handoff and exact notation checkpoint are in
`docs/automatic-lesson-generation-resume.md`. **Primary work has returned
to Gate 2**, with Coda research correctness independent of the existing
native engraving audits.

- `coda_source_connectors.py`: explicit source-ordinal linked slur and
  tie intervals, preserving part, staff/voice, slur number, spelled tie
  pitch, start/end identity and partial-window endpoints. MusicXML
  `tie` and `tied` encode one sounding arc, not two.
- `MatrixScore.source_connectors()` and
  `connector_protected_source_ids()` expose this graph to the Coda
  source model. A rhythm transformation cannot silently change source
  notes inside an authored slur or incomplete/uncertain connector;
  unrelated voices remain independently transformable.
- Both `PolyphonicChordifier` and `ResearchPolyphonicDottedRhythm`
  now consume the same connector protection; `ResearchPartSplitter`
  uses the same links to reject unsafe measure cuts. This replaces
  duplicated ad-hoc boundary interpretation.
- Source-span tests cover independent voices, encoded tie duplicates,
  cross-measure intervals, partial windows, unsupported marks, interior
  notes and an authentic MusicXML tie fixture. First commit `e55b353d`
  passed short CI: **179 passed, 6 skipped in 3.74 seconds**.
- **No Coda research strategy has been promoted to production**, no
  reference-algorithm parity is claimed, and the four complete Coda
  transformations remain research-incomplete. The full thesis still
  cannot be retrieved from the Dartmouth endpoint (403).

The next Coda gate is a complete MMR relationship and notation-preserving
transformation contract, followed by independently validated examples for
each of the four algorithms. Transformed notation/Listen/MIDI feedback
already have a shared timeline for existing experimental app strategies,
but the standalone Coda prototypes are not yet live.

## Gate 2 continuation — source MMR and four-family interoperability (2026-10-30)

Research source check: the Dartmouth abstract confirms the Score–Part–Voice
MMR and the four categories, but its published thesis download still returned
HTTP 403 on 2026-10-30. No alternative reference source was verified. The
following checks establish **engineering correctness, not Coda parity**:

1. `coda_notation_hierarchy.py` groups all original MusicXML direct measure
   elements by **source part → measure → original source voice**, including
   unvoiced attributes, barlines, directions and rest-only source voices.
   Inherited clef/key/meter/divisions and numbered/staff-specific attributes
   from earlier measures have explicit source ordinals and XML subtrees.
   The complete score-wide original XML is kept for source auditing.
2. `MatrixScore.verify_lossless()` compares the *entire* selected original
   MusicXML element inventory (including directions and other non-notes)
   to its matrix, not merely the matrix to its own partitions. Deleting or
   rewriting one original subtree is a failing test.
3. `MatrixScore.context_protected_source_ids()` conservatively prevents
   experimental chordification and dotted re-timing through a mid-measure
   authored notation-context change. A change at a bar boundary does not
   block otherwise eligible source voice pairs. Multiple parts/voices
   remain independently owned.
4. The pinned `tests/fixtures/research/coda_four_families.musicxml` includes
   16 pitched attacks across two piano hands, two measures, a separate
   whole-measure rest voice and a later key change. The bounded test runs
   source-measure splitting, measure-wise tempo shaping, polyphonic
   chordification and dotted alteration **non-vacuously** on the same
   immutable source. It verifies reassembly, source identity, note onset and
   duration invariants, a changed drill distinct from original mastery and
   mapped grading. Both rhythm strategies are also passed through the
   application's actual `ScoreArtifacts.source_model()` contract with
   `transformed_rhythm=True`, without exposing them as completed live Coda
   strategies.
5. Short regression checks also cover selected later measures, inherited
   source contexts, real multi-measure MusicXML, source-scope preservation,
   rest-only voice ownership, and missing/rewritten annotations.

This does **not** complete the original Coda MMR, whose published structure
and detailed semantics cannot be confirmed without the thesis or code. In
particular: full notation-aware rhythm rewriting of nested tuplets and
articulations, score-wide directions over tempo changes, exact author
grouping/eligibility, reference example parity, production UI integration
and measured learning outcomes remain open.

### Completion status, unchanged

- Source-aware MMR: substantial research adapter; **not reference-proven**.
- Part splitting: source-measure prototype; **not author-parity-proven**.
- Tempo shaping: source-grid/shared-time prototype; **not author-parity-proven**.
- Chordification: independent polyphonic prototype; **not author-parity-proven**.
- Dotted rhythms: independent per-voice prototype; **not author-parity-proven**.

Main branch only; no full corpus or long-running CI was initiated.
