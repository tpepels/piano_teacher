# Gate 2 — MIDI input first (2026-11-02)

**Product input:** Standard MIDI files (`.mid`, `.midi`). Generated
MusicXML is an **internal engraving representation**, not a score the
learner must provide. Native MIDI performance attack/release timing,
source IDs, track/channel, velocity, original PPQ, bar/meter events and
the deterministic hand-splitting policy are the input contract.

Original notation facts **cannot** be recovered uniquely from MIDI:
slurs, articulations, editorial tie segments, authored beams, staff
voices, rests and graphic directions are usually absent. Do not
invent a requirement to preserve them from non-existent source XML.
The notation generator must instead produce readable score notation
consistent with the same exact exercise/performance timeline.

## Implementation

- `piano_teacher/music.py`: immutable imported `Piece` now records
  `source_format="midi"` and original `midi_ticks_per_beat`.
  MusicXML source imports are explicitly labelled but are not part of
  the current MIDI user-flow acceptance scope.
- `piano_teacher/research/coda_midi_grid.py`: select an **exact
  original-PPQ grid** (double the grid for dotted half-tick durations),
  fail on invented/rounded source ticks, invalid provenance or bounded
  128-pitch matrix capacity. This is separate from the historical
  author's `ceil(1/shortest_written_note) * time_numerator`
  quantization, which was designed for MusicXML.
- `piano_teacher/research/coda_score_projection.py`: accepts genuine
  MIDI source pieces **without any original MusicXML**. Creates a
  new derived notation/Listen/grading stage from one `TimingPlan`.
  Original `Piece` stays immutable. MIDI input fingerprints are
  derived from the original canonical imported source events and
  meter/PPQ; they no longer hash an empty XML string.
- Existing source-authored XML obligation guards are not invoked on a
  MIDI source. No fabricated authored slurs/tuplets/rests are attached.
  Native `build_lesson_score` still generates performance-aligned
  notation internally.

## Bounded verification

| Verification | Evidence |
|---|---|
| All **16 independent supported SMF fixtures** imported, with original note IDs and exact PPQ; no source attack/release lost from the per-voice Coda research matrix | `tests/test_coda_midi_corpus.py`; [bounded CI](https://github.com/tpepels/piano_teacher/actions/runs/41374997761), passed |
| MIDI PPQ/half-tick grid, 997-PPQ case, capacity rejection, invented off-grid tick rejection, source provenance | `tests/test_coda_midi_grid.py`; same bounded CI |
| Seven MIDI-generated Coda exercise variants (slowdown, dotted, chord; 4/4, 3/4, changing meter, sparse rests, triplets), actual SVG noteheads tied to grading IDs | `tests/test_coda_midi_pipeline.py`; [real engraving CI](https://github.com/tpepels/piano_teacher/actions/runs/41374811238), **31 tests passed** (including older authored-XML research cases) |
| MIDI dotted exercise -> actual synthesized Listen WAV, `LiveInputView` correct source/onset feedback, transformed `stage.grade` software note-on/off | Same real engraving CI; software only |
| Existing app contract gates | [fast application CI](https://github.com/tpepels/piano_teacher/actions/runs/41374811375) and [MIDI matrix CI](https://github.com/tpepels/piano_teacher/actions/runs/41374997811), both passed |

The import and generated-exercise checks cover **software** data and actual
Verovio/WAV output. They do not constitute a physical keyboard test,
native Godot framebuffer/transport verification, or evidence of improved
learning.

## Reprioritized blockers

1. **Real user MIDI repertoire, longer passages and difficult performances:**
   validate high-PPQ and unusual subdivisions, multiple tracks and voices,
   repeated overlapping same-pitch attacks, pickups, changing meters,
   independent hands and extreme register. Distinguish true matrix
   limitations from ordinary acceptable MIDI performances. Matrix resource
   limits must reject explicitly, never alter source beat timing.
2. **Practice passage selection:** the research
   `project_coda_score()` currently accepts a complete source excerpt
   starting at bar 1. It is not yet a generalized selectable passage within
   an arbitrary longer imported MIDI file; that should be addressed before
   enabling it for ordinary lessons.
3. **Generated *MIDI-derived* notation:** verify inferred stems, voices,
   rests, rhythmic beams, ties split by bars, tuplets, clefs and note
   spelling by independent semantic/visual rules. Since there is no authored
   notation, evaluate legibility and temporal equivalence, not equality
   to an imagined source score.
4. **End-to-end runtime:** validate generated notation, Listen and grading
   on the real Godot application and a physical MIDI keyboard (including
   pauses, rest boundaries and retries). A bounded software test alone
   cannot establish correct hardware behavior.
5. **Product activation, once verified:** select the supported exercise
   strategy in-app and feed all three consumers the identical transformed
   stage. The Coda research algorithms remain research-only until runtime
   and user-facing lesson behavior are verified.

## Historical research parked (not MIDI product blockers)

The two independent source-MMR mismatches, three Coda-grid exclusions,
and authored-notation preservation backlog identified in the previous
MusicXML comparison are **MusicXML-source research tasks**. They do
**not** block a MIDI-input lesson. Similarly, the original author's
24-case exact output subset and original automatic chordification
width enumeration remain reproducibility evidence, not the acceptance
criteria for MIDI input.

Upstream Coda parity remains documented under
[issue #42](https://github.com/tpepels/piano_teacher/issues/42) separately.
No legacy MusicXML input fallback has been added to the MIDI exercise
path; the original MusicXML import capability is left unchanged rather
than deleted as an unrelated change.

**Status:** MIDI-first research path functional and bounded verified;
complete Gate 2/product exercise selection and physical MIDI readiness
remain open.
