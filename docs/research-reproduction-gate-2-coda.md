# Research reproduction — Gate 2: Coda symbolic system

2026-10-30. Branch: `main`. Status: **reference thesis and official backend now located; reference-guided subset implemented; complete parity NOT established**.

## Source record

Annie Tang, *Coda: A Digital System for Generation of Piano Practice
Exercises from Symbolic Music Notation* (Dartmouth undergraduate thesis,
June 2025), https://digitalcommons.dartmouth.edu/cs_senior_theses/76/.

The institutional abstract explicitly describes a Music Matrix
Representation (MMR) with Score–Part–Voice hierarchy and four exercise
families: **Part Splitting, Tempo Shaping, Chordification, and Dotted
Rhythms**. The complete 41-page thesis was supplied on 2026-10-31 and is
available in the user's conversation. The author's own public GitHub
repositories were also located and inspected:
`https://github.com/annieetang/coda_backend` pinned at
`a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`, and
`https://github.com/annieetang/coda_app` pinned at
`c5a00ca53c3204fc66bde4cdaba3157ab760e76a`.
This resolves the missing-specification blocker. It **does not**
automatically confer algorithm parity: the thesis prints simplified
methods, and the backend includes TODOs and known non-invertible cases.
Exact executable upstream differential checks are still required.

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
      the original Coda thesis and pinned backend**, with executable reference parity.
- [ ] Complete score/part/voice isolation matching author examples (the old
      measure-splitting prototype is a separate lesson feature).
- [ ] Complete author-specific x2/x4 note-duration/notation slowdown and
      exact beat/second playback across Learn/Listen/grading (the old
      measure-wise tempo ramp is a separate strategy).
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

## Research specification recovered — 2026-10-31

The uploaded thesis is now authoritative alongside the author's pinned
backend. **This section supersedes the older 'thesis unavailable' status.**

| Family | Thesis/backend specification | Previously present | New independent reference-guided implementation |
|---|---|---|---|
| Score/Part/Voice splitting | `get_all_exercises` emits full score, each note-bearing Part and each `voicesToParts()` line | `ResearchPartSplitter` slices source measures, not the Coda algorithm | `original_coda_levels()` emits score, note-bearing hand and note-bearing voice selections with source indices |
| Tempo Shaping | `generate_slowed_down_exercise(factor)`: expand grid, source onset and duration by integer factor 2 or 4; regenerate notation | `ResearchTempoShaper` uses a within-piece measure-wise BPM ramp | `CodaReferenceSlowdown(2/4)` expands source-mapped written rhythm; transformed Listen and score-grid integration still pending |
| Chordification | Find runs of equal quantized durations, group by chord level, form blocked chords of group span; omit overly large/wide groups | Pairwise chord collapse retaining only original note duration | `CodaReferenceChordification(chord_level)` joins eligible discrete groups with longer duration, <=5 distinct tones and <=12 semitones, retaining every source ID |
| Dotted Rhythms | Equal-duration runs, patterns `[1.5,.5]` or `[.5,1.5]`, regenerate onset/duration matrices | Fixed non-MMR pairs | `CodaReferenceDotted` iterates original MMR runs in independent voices with exact source IDs and original total duration |

### MMR, from §2.2 and upstream

The thesis and original `music/matrix.py` use *three*
`128 × quantized-time` matrices: binary `piano_roll` (sounding
occupancy), binary `onset_map` (attack, not sustain) and integer
`durations_matrix` (onset duration). Other fields include
`key_signature`, `time_signature` and `quantization`. The author's
backend calculates the quantization as
`ceil(1 / shortest_quarter_length) * time_signature.numerator` and
uses a `ceil()` onset-time conversion. The new
`coda_reference_matrix.py` deliberately rejects off-grid source
beats rather than silently rounding and merging attacks.

These contracts use **originally sourced IDs**, the existing
lossless notation hierarchy and source-part/voice ownership. The
three matrices are separate research assets, not enabled
implicitly in any production practice stage.

### Author code limitations and deliberate guarded differences

- The backend's `_create_matrices()` contains a TODO for tie
  handling and represents simultaneous pitches as if all have equal
  duration. The reference adapter **fails closed** on same-pitch
  overlaps, unquantizable events and unequal chord lengths.
- The thesis and backend use `Chordification` at selected
  `chord_level` values (quantization, twice and half quantization,
  meter numerator/denominator-derived values). The new adapter
  takes an explicit level; automatic exact level enumeration and
  source output set parity are still outstanding.
- The original backend's chord grouping includes weak edge-case
  handling and its dotted algorithm has TODOs concerning rests.
  The independent adapter refuses source-rest overlaps, authored
  beam/slur/tie/tuplet changes and mid-measure context changes
  unless their transformed notation can be proven. It transforms unmatched odd dotted tails when the new duration fits
  the original bar and does not overlap an authored rest or later attack;
  otherwise the original tail is retained. These are safety
  adaptations, **not claims of bit-exact original results**.
- The full thesis specifies invalid chords as more than five
  notes or intervals wider than an octave and reports most
  generation operations below 500 ms for typical examples.
  Those time and exact-output benchmarks have **not** been
  independently reproduced.
- Upstream source presently shows no LICENSE file, so do not
  vendor/relicense its implementation. Independent
  algorithm-derived code and explicit references are used.

### Bounded evidence

The checked-in `tests/fixtures/research/coda_four_families.musicxml`
(two-hand, 16-note, two-measure, source-rest voice) now exercises
the exact three MMR matrix shapes, author quantization, original
source-id preservation, score/part/voice isolation, x2/x4
slowdown, both dotted patterns and blocked-chord outputs.
Negative cases reject same-pitch collisions, off-grid attacks,
unequal simultaneous note durations, wide chords and invalid
grouping widths. This is a **specification-derived test set**;
the author's functions have not yet been executed against
the same fixture, and no production source stage is switched on.

One exact pinned-backend differential sample has now PASSED as detailed
below. Remaining: broaden to mixed rhythms/voice cases and exact source
exercises beyond the trivial uniform fixture; account for reference
errors without claiming invented parity. Follow with offline transformed
notation and Listen/MIDI/grade integration. No full-corpus audit
is warranted for this gate.

## Executable author-source differential, 2026-10-31

**First constrained reference parity demonstrated** on current
`main` at `20b7ba9f954dfe08a176042c02d46e2cc44051f5`.
The separate, explicit-only GitHub workflow
`.github/workflows/coda-upstream-parity.yml`
uses a short, isolated runner and obtains the author's public,
unmodified checkout at SHA
`a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`.
Only the database service initializer unused by the symbolic
generation is stubbed; the author's actual `ExerciseLine`,
`_create_matrices`, `generate_slowed_down_exercise`,
`generate_dotted_exercise` and `generate_chordify_exercise`
execute.

Run: https://github.com/tpepels/piano_teacher/actions/runs/41192215147

Result **PASS**. On the pinned 2-measure, 2-part,
16-note `coda_four_families.musicxml` fixture, all three
`128 × T` arrays match the original code in both voices
(**6 exact array comparisons**). All **10** nontrivial
output event sequences match (2 hands × 5 algorithms):
written slowdown ×2 and ×4, dotted ×(1.5,.5),
dotted ×(.5,1.5) and chordification level=8.
Events are independently normalized from the actual
music21-generated `Part` as
`(onset in quarter beats, MIDI pitch, written duration in beats)`,
not compared using this project's own transformations on both sides.
The original code's return values are neither mocked nor substituted.

Current-revision retained artifact: `13039805435`;
revision-bound fast contract gate:
https://github.com/tpepels/piano_teacher/actions/runs/41192215134
(**207 passed, 6 skipped**).

**Limit of evidence:** this is parity on one deliberately small,
representable, straight-quarter-note fixture using 4/4, one
pitch-bearing voice per hand. It does not cover source beaming,
ties, rests interacting with transformed rhythms, odd-length
runs, multiple simultaneous source chord notes, multiple
time signatures, unusual quantization, varied grouping levels,
the author's optional UI/pipeline variations, or generated
MusicXML visual appearance. Never generalize the above
6+10 comparisons to those cases. The published implementation
itself has open TODOs for ties/rests.

All four Coda strategies remain opt-in research code, not
completed production exercises. Gate 2 is still **partial**.

## Expanded executable differential and corrected edge cases — 2026-10-31

A new **explicit-only**, bounded comparison against the pinned,
unmodified author backend is provided by
`scripts/probe_coda_upstream_edges.py`. It uses the same
`music21` reconstruction of note onsets and written duration as the
initial author comparison. The four input cases have source-identifiable
notes and independent 4/4 score construction:

1. `even-mixed`: four eighth notes followed by two quarter notes.
   Quantization=8; equal-duration runs at different rhythmic values.
2. `odd-equal-run`: three quarter notes followed by unoccupied time.
   Quantization=4; both 3:1 and 1:3 patterns change the last unpaired
   source event, as the author code demonstrates.
3. `block-chords`: simultaneous two-note source chords at four beats.
   Quantization=4; per-source pitch duration and blocked grouping agree.
4. `mixed-with-gap`: two eighth notes, a silent beat, then two
   quarter notes. Quantization=8; the following rest padding does
   not lengthen the chord formed from the first pair.

The expanded run **PASSED all four declared parity cases** with
three exact matrix comparisons and five generated exercise event
comparisons per case: **12 exact arrays + 20 exact sequences**.
The original uniform two-hand fixture remains separately checked:
**6 exact arrays + 10 exact sequences**. Together these selected
proofs provide **18 matrix comparisons and 30 exercise-output
comparisons**, but they must not be reported as source-corpus coverage.

- Tested revision: `7026db235c5916f2c68e6fedfc899a9bc028d3f9`
- Author revision: `a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`
- Run: https://github.com/tpepels/piano_teacher/actions/runs/41193216063
- Artifact: `13039732356` (includes `edge-cases.json`, reference
  sequence report and comparison terminal output)
- Fast CI: https://github.com/tpepels/piano_teacher/actions/runs/41193216091
  **211 passed, 6 skipped**, independently audited notation semantic
  baseline still 10/10 supported MusicXML scores.

Two actual first-run mismatches were identified and corrected instead
of being waived. In the reference's equal-duration run extractor,
the reported range ends at the next *different* written duration,
possibly beyond its last note. Our grouping previously rejected that
padded span, then mistakenly used the padded end for note duration.
The corrected adapter uses the exact summed sounding duration and
preserves the following silence. An odd-length dotted run changes its
final single note in the original backend; our adapter now reproduces
this when the new interval stays inside the original measure and does
not cross later source attacks or authored rests. The original backend
can produce questionable cases beyond the bar; our adapter's explicit
limit remains a **documented intentional nonparity guard**.

**Still not verified:** the reference's complete autogenerated chord
level set, source-authored rests/ties/tuplets and musical directions
through transformation, multiple meters, non-grid original onset
rounding, note overflow, complete transformed MusicXML engraving,
Listen/grade integration for all three timing families, real piano
hardware and teaching effectiveness. Do not promote research
strategies to production or close Gate 2 based on this sample.
