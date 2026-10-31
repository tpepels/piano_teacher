# Research reproduction — Gate 2: Coda symbolic system

> **Product scope revised 2026-10-31:** Piano Teacher now targets a MIDI-only
> user library. Original MusicXML authoring metadata is unavailable for the
> user's music, so source-XML preservation and exact upstream Coda parity are
> excluded from the product roadmap and mandatory CI. The work described
> below is historical, isolated research. Retain only MIDI-operable exercise
> concepts (part selection, tempo changes, chord blocks, dotted pairs) with
> verified source-note identity and the same notation/Listen/grading timeline.
> Internally generated lesson MusicXML remains an engraving format, not an
> external score dependency. No research-only Coda feature is promoted by
> this scope change.

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

## Actual Coda notation → Listen → grading pipeline (2026-10-31)

The first **source-backed research projection**, separate from production
curriculum flags, is implemented at
`piano_teacher/research/coda_score_projection.py`. One immutable original
`Piece` plus one source-indexed Coda `TimingPlan` produce
`CodaProjectedStage` containing:

- A private, source-owned, **new** `Piece` and `Phrase` whose note
  onsets/releases exactly follow the transformed `TimingPlan`;
- A uniquely fingerprinted `ScoreSelection` consumed by the
  **production** `ScoreArtifacts` MusicXML → semantic-score → Verovio
  engraving path, with canonical `source_id` note and actual glyph binding;
- A `ListenSelection` consumed by **production** `ListenSession` and
  `DemoAudioCache`, with the same selected `ExerciseVariant` and
  constant `TempoMap`;
- `grade()` that calls `assess_timed` with the same plan and clock,
  rebinding the outcome to the immutable original event identities **without
  granting original-piece mastery**.

It supports both author dotted patterns, equal-run chordification and
written slowdown factors 2 and 4. Crucially, slowdown **expands written
beats and rebars the excerpt**; it does not substitute an arbitrary
tempo-map ramp. The source context's key, meter and clef positions are
mapped to the transformed timeline. Explicit source rests, including the
fixture's RH rest-only voice, survive by scaling a private source-XML
projection for x2/x4 while preserving the original immutable XML.
The two-measure genuine MusicXML test has a right-hand key change
from fifths 0 to -1 at original beat 4: it appears at transformed
beat 4, 8 and 16 for ordinary, x2 and x4 notation respectively.

**Fail-closed scope:** only complete bar-1 excerpts of the supported
source-partwise subset are currently accepted. Altered rhythms with
directions, lyrics, tuplets, ties, slurs, ornaments, beams or mid-measure
attributes are rejected instead of discarding original annotations.
For written slowdown, changing bar lengths/meters, authored special
barlines/repeats and source XML chord notes also require new validated
projection logic. Source-wide fingering edits remain under the original
piece; no fingering is fabricated for the new exercise.

### Executed evidence at source revision `99c33563`

- Fast semantic/Listen/grading tests:
  https://github.com/tpepels/piano_teacher/actions/runs/41194677205
  (**218 passed, 6 skipped**; 10/10 old supported MusicXML semantic
  fixtures pass as separate independent coverage).
- Bounded **real Verovio rendering** and actual audio/live event test:
  https://github.com/tpepels/piano_teacher/actions/runs/41194677252
  (**6 passed**, 1.63s tests; separate short opt-in job).
- Artifact `13039764876` contains **five independently produced**
  MusicXML scores and their actual production Verovio SVGs, plus JUnit,
  captured WAV cache and revision marker. For each of the 5,
  source-to-ink mapping verifies **16/16 note identities**, resulting
  in 80 selected-note glyph checks. The source rest-only voice and
  key change were independently checked in the produced XML and in
  the retained graphics; SVG visual samples were manually reviewed.
- In the 6th real-tool test, `ListenSession` synthesized an actual
  8000-Hz WAV from a dotted-stage `DemoAudioCache` (not a test fake).
  Playback duration equals the canonical `TempoMap`. A simulated
  *physical-format* note-on enters the normal `LiveInputView`
  on-time and retains its original `source_id`. Omitting one
  right-hand note from the right-hand take produces a `missed`
  mark attached to the exact Verovio note ID in the selected
  engraving layout.
- Original MusicXML remains intact in the original `Piece`;
  the working score is a **separate** research stage. No production
  strategy or mastery gate is automatically enabled.

The above verifies actual SVG and synthesized WAV behavior for a small
source excerpt. **Not** yet verified: native Godot score drawing, real
MIDI hardware, changing meters with written slowdown, tuples/beams/ties,
arbitrary unvoiced directions, broad published author example parity,
student-model integration or teacher-study outcomes. Do not accept Gate 2
as complete on this evidence alone. The next technical step is
source-annotation-preserving projection for a broader real-score set
followed by bounded Verovio/Godot rendering and device tests.

## Coda source annotation preservation — 2026-10-31

**Verified current revision:** `3ddeb00e01774542b8b5594ee1ac611e49365105`.
The research-only `coda_annotation_guard.py` extends the
`CodaProjectedStage` contract to preserve authored notation only if its
source event timing and identity are unchanged. It checks the *generated*
`build_lesson_score()` XML before allowing a selected research stage:

- **Paired source slurs:** explicit authored end identities, complete
  source-voice interval protection, unchanged original attacks, exact
  copied slur attributes on the corresponding new noteheads.
- **Articulations:** unchanged staccato/tenuto/accent, source-id matched
  and counted against the generated MusicXML.
- **Beams:** source-authored primary begin/continue/end groups only where
  all member attacks, durations and voice ownership survive. In that case,
  the complete authored 4-eighth grouping supersedes automatically
  inferred 2+2 groups. The generated score must match every source
  member's beam marks and have balanced, uninterrupted beam sequences
  per measure and voice.
- **Simple directions:** dynamics `p, pp, ppp, mp, mf, f, ff, fff`
  anchored at the beginning of an original measure, with a uniquely
  identified original performing hand. The projected direction must
  retain the same hand, measure, symbol and zero offset.
- **Plain cross-bar ties:** complete two-segment unstyled ties over one
  original internal measure boundary, whose sounding source note
  remains unchanged. The start/stop source voice and pitch are linked,
  the original note onset/end must equal the written tie chain, and the
  generated score must retain physical `tie` and `tied` marks on
  exactly one pair of source-owned glyphs at the original barline.
  Source-tie continuations stay a single MIDI attack, never a second
  graded note.

The original `Piece` and its MusicXML are unmodified. Every accepted
mark undergoes direct generated-XML comparison. Unsupported and
incomplete marks fail closed (including malformed or styled ties,
unpaired slurs, changed slur-interior notes, transformed beamed notes
with unverifiable grouping, arbitrary directions, tuplets, ornaments
and x2/x4 scaling of annotated tie/slur structures). No new production
lesson strategies were activated.

### Bounded additional real-score evidence

- Current fast run:
  https://github.com/tpepels/piano_teacher/actions/runs/41196496479
  **226 passed / 6 skipped**. Separate existing semantic smoke:
  **10/10 source scores** and 261 original attack identities.
- Actual SVG/Listen/grade run:
  https://github.com/tpepels/piano_teacher/actions/runs/41196496507
  **9 passed in 1.65 s**, artifact `13040737024`. This includes the
  original five transformed Coda score projections and WAV/live feedback;
  an authored RH slur plus staccato over a differently transformed
  voice, with real Verovio `slur` ink; exact original beam grouping
  from `tests/fixtures/connector_pixels/beams/score.musicxml`; and
  separate sounding ties from two competing voices in
  `tests/fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml`,
  verified as independently anchored real SVG tie groups.
- Negative source tests reject unpaired slurs, incomplete, shortened
  or styled ties, unsupported tuplets and source changes inside an
  authored slur rather than silently dropping their markup.

**Limits of this proof:** the real parallel-tie fixture uses an
unchanged original timing plan to validate the notation projection;
it does not demonstrate Coda's rhythm rewriting through the tie.
The author's broader MMR strategies still need research parity for
complex source repertoire. Native Godot playback rendering and physical
MIDI remain untested in this revision. General tuplets, arbitrary
directions, altered annotation timing and mixed-meter written slowdown
require distinct explicit semantic transformations and tests.
**Gate 2 remains partial.**

## Coda Gate 2 — source tuplets and mixed meter (2026-10-31)

Implementation runs **only in the research-only Coda score projection**;
no production curriculum or mastery settings were changed.

### Complete authored 3:2 eighth-note triplets

The strict `coda_source_tuplets.py` adapter now accepts exactly one
**complete, unchanged** 3:2 eighth-note triplet per group. It checks
the original XML's part, measure, source voice and source note identities,
the three contiguous 1/3-quarter durations, the source group start/stop
bracket attributes and all three recorded timing events. The independent
other hand/voice may undergo Coda dotted-rhythm transformation. Original
triplet members retain their source IDs and note durations. The
canonical `build_lesson_score` output must contain the same 3:2
`time-modification`, eighth-note values, group boundaries and every
explicit authored bracket attribute. Malformed ratios, partial groups,
overlapping/nested groups, unvoiced, rest-containing and retimed
tuplets all fail closed. This is *not* generic tuplets support; the
existing native renderer already supports broader ratios separately.

A bounded `tests/fixtures/research/coda_authored_triplet.musicxml`
source fixture was imported, exercised with dotted rhythm in a
different voice, engraved with **actual Verovio SVG**, source-identified
and graded against the transformed clock. Explicit output-corruption
controls changed the source bracket and 3:2 ratio in the generated
MusicXML and verified that both cause rejection.

### Source-driven mixed-meter slowdown

The prior uniform-meter x2/x4 restriction was removed for complete
source bars. `_original_metadata` now repeats **each** original
measure's own duration `factor` times and shifts original time, key
and clef changes by the exact same source-beat factor. A source
3/4 → 2/4 change at beat 3 becomes a change at beat 6 (x2)
or beat 12 (x4) with correct repeated meter grids:

- x2: `(0, 3, 6, 8, 10)`
- x4: `(0, 3, 6, 9, 12, 14, 16, 18, 20)`

The source-authored LH quarter rest at beat 2..3 projects to
beat 4..6 at x2 and 8..12 at x4; when x4 crosses a newly
introduced barline, the corresponding printed rests are
split without losing their occupied time. Both new sources
feed production `ScoreArtifacts`/Verovio and the same
`TimingPlan`/MIDI grading clock. Original `Piece` metadata
and original MusicXML are immutable.

This deliberately still **rejects** pickup/partial bars,
mid-bar time-signature changes, arbitrary authored directions,
styled ties, changed or incomplete source tuplets, tempo
markings requiring cross-meter reattachment, and unprojectable
barline/repeat semantics. The thesis-backend source reference
was not differentially executed on this mixed-meter/tuplet
subset, so do not call these two expansions author-parity
verified.

### Bounded verification

- Tested engraving revision: `42ec373a599ba305ba6dad6ef110d2b6cb3aefaa`
- Real Verovio/Listen/feedback gate: **12 passed**, run
  https://github.com/tpepels/piano_teacher/actions/runs/41197917233,
  artifact `13040688876`; includes actual new mixed-meter x2/x4
  and complete source-triplet SVG outputs
- Final fast contract at revision
  `8939fa0e8a4b45708e909851fa334fa3349ca907`:
  **232 passed, 6 skipped**, run
  https://github.com/tpepels/piano_teacher/actions/runs/41198028760
  and still **10/10** established separate semantic source scores
- Both generated-XML corruption controls and malformed
  source-XML/retimed tuplet controls must raise; no xfails added

**Still incomplete:** general tuplets (5:4, 7:4, nested, rest-bearing,
cross-measure), actual time-warping of slurs/ties and expressive
directions, tuplets with Coda source operations changing those notes,
true repertoire-wide research parity, native Godot on these transformed
scores, physical keyboard MIDI and teaching effectiveness.

## Retimed expressive marks and expanded author differential — 2026-10-31

### Research-only supported source transformations

- Authored **slurs** can follow source attacks retimed inside their
  original measure, in the same source voice and hand, only if all
  attacks remain present, strictly ordered and nonoverlapping. The
  renderer attaches the original paired slur by source identity, and
  the research adapter compares each explicit authored endpoint
  against the actual generated XML. A reversed/overlapping
  intervention fails. Real Verovio curves were verified.
- Plain **cross-bar ties** may shorten their final sounding note,
  provided the attack and original tie boundary remain unchanged,
  the note still ends *after* the boundary, and the shortened tail
  does not overlap the source voice's authored rests. The generated
  notation retains its original tie endpoints and the grader still
  owns **one sounding attack**, not two. Retiming a tie before its
  boundary, styling it or moving its start remains unsupported.
- The original **dynamic** `p/pp/ppp/mp/mf/f/ff/fff` can follow
  a *single exact source attack* inside the same source measure,
  including a changed beat, using a private source XML copy with a
  new cursor-relative `offset`. The original score is immutable.
  The generated music must carry the same hand, measure, symbol and
  newly mapped beat (verified at 10080 ticks per quarter).
  A representative `mf` moved from source beat 1 to exercise beat
  1.5; the real generated Verovio SVG contains the corresponding
  dynamic glyph. Ambiguous attacks, moving across a barline, arbitrary
  source words/wedges or unsupported directions fail closed.
- Source-owned **5:4 quintuplets and 7:4 septuplets** now join
  3:2 triplets in the supported unchanged eighth-note group subset.
  The adapter validates complete groups, actual:normal ratio,
  original source IDs, contiguous durations, start/stop bracket
  policy and actual generated MusicXML values. Another voice may
  undergo the Coda rhythm transformation independently.
  Source time is stored to eight decimal places; strict MMR tick
  comparisons account for that known representation resolution
  without accepting genuinely off-grid attacks.

The new source tests and output corruption controls run in fast CI.
The real Verovio workflow also checks all three tuplet ratios,
retimed slur and note-anchored dynamic, earlier parallel-voice
ties, rest and beam cases, and actual Listen WAV/MIDI feedback.

### Reproducible validation

- Revision `1260b601669d8f4cafb3d6c64b4c05ab520a10a9`:
  https://github.com/tpepels/piano_teacher/actions/runs/41199395502
  **16 selected real Verovio/WAV/feedback tests passed**;
  retained SVG and source files artifact `13041668228`.
- Current semantic regression on `3d5c4abd211866b61d842c07d136d368154c4479`:
  https://github.com/tpepels/piano_teacher/actions/runs/41199689519
  **238 passed / 6 skipped**, separate 10/10 established source
  semantic fixtures (261 original attacks, 288 native events).
- Source and author differential on the same code revision:
  https://github.com/tpepels/piano_teacher/actions/runs/41199689501
  artifact `13042256100`.

### Additional pinned original-Coda comparison (never blanket parity)

The pinned original backend
`annieetang/coda_backend@a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`
was executed unchanged on a bounded selection of actual checked-in
MusicXML. The first two bars only were selected from the longer
multipage source. Each selected reference voice's three
`128 × T` MMR arrays was compared elementwise to our original
unmodified source MMR:

| Sample | Exact original MMR voices | Exact algorithm sequences | Different outputs | Author returns no output |
|---|---:|---:|---:|---:|
| Parallel-voice ties | 2/2 | 0 | 8 | 2 |
| Authored beams | 2/2 | 4 | 5 | 1 |
| Multipage first two bars | 2/2 | 5 | 4 | 1 |
| **Total** | **6/6** | **9** | **17** | **4** |

Every source-voice MMR matched exactly, but **only 9 of 30 author
exercise output cases matched exactly**. Those nine are individual
fixture/parameter observations, **not complete reference parity**.
The original backend sometimes emits multiple written notes at the
same onset where this project retains one sustained source MIDI
identity, including in tied voices; this must be reconciled at the
notation *and* performance levels instead of silently equating their
raw event sequences. The author also returns no exercise for
several requested chordification levels. These 21 outstanding cases
remain recorded in the revision-bound JSON.

The four earlier pinned simple-source parity cases remain green.
New standalone research diagnostics for sixteenth-note runs matched,
while quintuplet and septuplet spacings hit upstream matrix errors.
Those two are explicitly *unverified* author-parity cases.

### Still blocked

This increment does **not** implement nested/cross-measure tuplets,
tuplets containing source rests, remapped tuplet member attacks,
retimed and styled tie starts, cross-measure slur reshaping, arbitrary
text/pedal/hairpin directions, or full MusicXML/music21 tie-event
equivalence. Native Godot physical framebuffer and physical MIDI
verification of these new research projections are also outstanding.
**Coda Gate 2 remains incomplete and research-only.**

## Separate written tie segments, rest-bearing tuplets and broader author diagnostic — 2026-10-31

### An explicit two-clock tie contract

`piano_teacher/research/coda_written_tie_segments.py` establishes
`WrittenTieSegment` and `WrittenTieChain` as immutable research
data. Each written MusicXML note segment has its own original XML
source ID, interval, voice and tie start/stop role. The **one**
imported/graded sounding source ID belongs to the beginning of
the chain. A generated `CodaProjectedStage.written_ties` retains
both **original** and **projected** written segments for verification
without introducing a new MIDI event.

The real independent parallel-tie fixture has two voices on the
same pitch C4. Original voice 1 has written segments 0..4 and 4..6
for one sounding 0..6 attack. Original voice 2 has written segments
2..4 and 4..5 for a different sounding 2..5 attack. A safely
shortened voice-1 continuation becomes 4..5.5 while its first
0..4 segment and sounding attack remain unchanged. Generated
MusicXML must have exactly the expected segments, written
durations/pitches, tie/tied roles and the correct `is_attack`
boolean on each glyph; a false second attack or changed tie
stop fails validation. The source piece remains immutable.

The contract deliberately supports only complete two-segment ties
over one original internal measure boundary with an unchanged
start and unstyled source connectors. It does not reinterpret
the author's duplicated/off-grid written note events as correct
MIDI playback. Source tie continuations are *not* independent
MIDI attacks.

### Authored rests inside tuplets

The strict Coda tuplets adapter now supports **one interior
written rest** in complete, unchanged eighth-note 3:2, 5:4
and 7:4 groups. The original rest is independent of the pitched
attack set; its source XML remains a written rest and it never
becomes a graded note. The generated MusicXML must preserve
its beat, duration, ratio and **the same generated voice as the
group's source-owned noteheads**. Explicit notehead, time-
modification, tuplet start/stop and original bracket attribute
checks remain in force. Other voices may undergo Coda rhythm
rewriting. Missing or misvoiced rests fail; endpoints with
rest marks, multiple interior rests, nested groups and retimed
tuplet members remain rejected.

Real Verovio exercised source-authored middle rests for all
three supported ratios, in addition to the earlier tie/slur/
dynamic source notation and WAV/feedback samples.

### Six genuine MusicXML fixtures compared against original Coda

The bounded original backend still uses the exact pinned
`annieetang/coda_backend@a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`.
`scripts/probe_coda_upstream_scores.py` compares the actual
three 128-pitch MMR arrays for each source voice and tries five
reference operations for each of these six source samples:

1. Two parallel tied voices
2. Authored source beams
3. First two bars of a longer multipage source score
4. Complete source triplet score
5. Source triplet with interior rest
6. Authored 3/4 → 2/4 changing-meter source

**12/12 sampled source-voice MMRs matched exactly.**
Of 60 attempted author-versus-adapter output sequences,
**23 exact matches**, **33 different sequences**, and **4
upstream-none**. The report records, for tied notes, the
distinct source written segments and sounding attack IDs.
For this sample, reference event tuples are `music21`
*written* events, whereas the research adapter reports
canonical *sounding MIDI attacks*. Raw disagreement in
those event representations does **not** by itself explain
whether two musical performances are equivalent.
No differing output was waived as a parity success.

The four simple, declared reference parity cases remain
green. The more complex source scores are diagnostics only,
not passed reference cases. The initial 3-score reference
comparison had 9/30 exact; this expanded 6-score report has
23/60 exact. The expanded denominator must not be
misrepresented as a software regression.

### Bounded checks and evidence

- **Written tie, source rest and projection contracts:** 
  `111 passed`, dedicated Coda gate
  https://github.com/tpepels/piano_teacher/actions/runs/41202193428
  (under 3 seconds for tests).
- **Actual Coda SVG/WAV/live-feedback tests:**
  `20 passed` at
  https://github.com/tpepels/piano_teacher/actions/runs/41202109324,
  retained artifact `13042897860`. This includes written
  parallel-tie reduction and rest-bearing 3:2/5:4/7:4 groups.
- **Original author six-score differential:**
  https://github.com/tpepels/piano_teacher/actions/runs/41201534395,
  retained artifact `13042587409`.
- After a separate commit changed general fast CI to a
  desktop/MIDI-only scope, the short
  `.github/workflows/coda-research-contract-smoke.yml`
  was added instead of undoing that independent change.
  Coda source/timeline tests still run on Coda paths, and
  the real Verovio test remains a bounded separate job.

**Open:** arbitrary/three-plus-segment ties, written note
reduction by the original author backend, rest-bearing tuplet
endpoints/multiple rests, nested/retimed tuplets, arbitrary
directions, physical MIDI/native Godot results for this
research stage, wide repertoire and real teaching outcomes.
No production Coda lesson family was enabled. Gate 2 is
**not complete**.
