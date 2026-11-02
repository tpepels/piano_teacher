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


## 2026-11-02 — passage, long MIDI, notation and Godot contract work

**Status: bounded software verified; physical hardware and in-app Coda
activation remain UNVERIFIED and disabled.**

### 1. Arbitrary practice measures

`piano_teacher/research/coda_midi_passage.py` adds:

- `select_midi_passage(piece, first_bar, last_bar)` (one through eight
  measures), with original source `Piece`, original selected note indexes,
  absolute beat span and attack IDs stored in `MidiPassage`;
- a local-zero `Piece` and `ExerciseVariant` with the source tempo,
  active meter/key/clef and exact imported note identities;
- `project_midi_passage(... family="tempo-shaping"|"dotted-rhythms"|
  "chordification")` producing the existing single-stage Coda
  notation/Listen/grading contract from that excerpt, independent of
  source MusicXML.

The selection **rejects a note sustaining across either selected endpoint**,
rather than inventing a fresh attack at the beginning or silently clipping
a real note release at the end. These windows require a later explicit
continuation/tail policy before arbitrary musical tie crossings can be
treated as fully supported.

`coda_midi_grid.py` optionally derives a compact exact beat grid by taking
the GCD of the original source PPQ, selected note-on/off ticks and measure
boundaries. The normal full-PPQ mode remains unchanged. Long conventional
passages no longer allocate one high-PPQ tick for every source beat.
Unrepresentable events and oversized matrices still fail closed.

### 2. Broader MIDI

`tests/test_coda_midi_long_repertoire.py` constructs a deterministic
48-bar two-hand SMF, selects bars **17–24**, checks absolute-to-local
timestamp mapping, independent handed tracks (including matching pitches),
exact matrix ownership and x2-slowdown clean grading. It checks that MIDI
with overlapping same-pitch note-ons in a single track is **not silently
merged**: the importer retains the events with an explicit FIFO ambiguity
warning, and the 128-pitch binary MMR rejects that voice rather than
claiming lossless parity.

The existing sixteen independently authored SMF fixtures remain part
of the bounded Coda research suite, including odd 997 PPQ, mixed meter,
tuplets, held notes and unisons.

### 3. MIDI-inferred notation

`tests/test_coda_midi_notation_quality.py` uses **real imported MIDI**,
not presumed original notation, to verify generated two-staff rests,
eighth-note beam elements, voice tags, readable clefs, written tie
start/stop and tie segment source bindings, as well as triplet
time-modification and actual SVG. The separate selected-later-bar
`tests/test_coda_midi_passage_pipeline.py` passes a bar-two MIDI x2
exercise through actual Verovio SVG, synthesized WAV Listen,
`LiveInputView` source-note feedback and clean synthetic MIDI grading.

[Bounded Verovio/Listen/grade workflow 41438832266](https://github.com/tpepels/piano_teacher/actions/runs/41438832266):
**35 tests passed in 3.25 seconds**, including prior Coda cases.
[Research contracts workflow 41438321708](https://github.com/tpepels/piano_teacher/actions/runs/41438321708):
passed, including the new long-MIDI and arbitrary passage checks.

### 4. Godot passage-clock handoff

`scripts/research/export_coda_midi_godot_model.py` exports an
**actual** MIDI-imported, selected bar-two, slowed-stage semantic model
into a strict JSON boundary. `tests/godot/coda_midi_passage_runtime.gd`
consumes it through Godot's own `notation/shared/timeline.gd` and
`visual_transport_clock.gd` on **Godot 4.7.2 headless**, verifying
source identity, measure grid, constant fixed-playhead motion, pause,
resume and explicit retry transport identity.

[Godot bounded workflow 41439160029](https://github.com/tpepels/piano_teacher/actions/runs/41439160029):
**CODA_MIDI_GODOT_FAILURES:0**, success. The fixture contains
one selected MIDI note and does not exercise the complete application
service/UI, a physical keyboard, or a hardware audio/MIDI loop.

### Unfinished product gates

- Passage-boundary sustained-note policy; broader real-world performance
  and register/score readability across longer rendered passages;
- actual in-app strategy picker and backend orchestration of the
  selected source excerpt (the prototype is still a research API);
- complete Godot application and native extension graphical integration
  under the live teaching state machine;
- **physical MIDI device testing**, including feedback, onset/offset,
  rest transitions, pause/resume/retry and Listen against actual hardware.

**Do not claim Coda production readiness or enable its strategies in the
application based only on these bounded symbolic and headless checks.**
Existing normal MIDI lesson behavior is not modified by these research
functions. Source MusicXML reference-parity issue #42 remains separate.
See active [MIDI-first issue #43](https://github.com/tpepels/piano_teacher/issues/43).


## 2026-11-02 — user-invokable Coda MIDI trial in the teaching session

The three MIDI-derived Coda exercise families are now available as
**explicit opt-in controls** on the actual `Lesson` screen:

- **Slowdown ×2** (written rhythmic slowdown and shared transformed timing)
- **Dotted 3:1** (only an eligible contiguous source rhythmic group)
- **Chord blocks** (two-beat eligible grouping)

The new `coda_try`/`coda_exit` commands go through `main.gd`'s existing
`/control` route, `ControlDispatcher` and the locked `PracticeEngine`
entrypoint. `application/coda_trial.py` prepares the research
`project_midi_passage` result for the **current source course passage**
(up to eight measures), then builds a regular `LearningPlan` from the
new, locally rebased immutable MIDI-derived `stage.piece`.

The normal learning-plan owners now drive the exercise:
`ScoreArtifacts` generates MIDI-derived notation, `ListenSession`
renders the selected transformed MIDI, `PracticeEngine` provides
transport/learning controls, and the ordinary software/hardware MIDI
recorder and grader see the same transformed note attacks. There is
no separate Coda playback/scroll or grading clock.

Trial sessions use a new source-and-transformation-dependent fingerprint
**distinct from the original piece**. Saved source mastery and tempo
progress are not credited by trial performances. The exact original
in-memory `LearningPlan` and fingerprint are restored by
`coda_exit` (or discarded on loading a new MIDI file). Source audio
and transport are stopped before a successful transition; a rejected
trial never stops or replaces a currently selected lesson.

The Lesson screen displays the three trial buttons and, while active,
a `Return to original MIDI lesson` control. For MIDI-only passage
selection, zero transformation (when no eligible pair exists),
cross-boundary sustained notes, or unsupported source inputs, the
command reports a clear error. Strategy preferences cannot be changed
mid-trial; exit the trial first.

### Bounded verification

- Actual `PracticeEngine.control("coda_try")`, source fingerprint
  separation, regular score selection, Listen route, software grading,
  reset through `coda_exit`, new-score replacement:
  `tests/test_coda_live_engine.py` in the short Coda suite,
  [run 41440734124](https://github.com/tpepels/piano_teacher/actions/runs/41440734124), passed.
- Genuine selected MIDI source isolation:
  `tests/test_coda_live_trial.py`, same short research suite.
- Real Lesson screen emits concrete Coda try/exit command payloads and
  reflects busy/unloaded states: `tests/godot/coda_trial_controls.gd`
  in [Godot startup suite 41440819810](https://github.com/tpepels/piano_teacher/actions/runs/41440819810), passed.
- [Fast application contract suite 41440819793](https://github.com/tpepels/piano_teacher/actions/runs/41440819793), passed.

**Still unverified:** physical MIDI keyboard, real time full native
extension graphical application session, long real repertoire and
sustained-note passage boundary handling. This is deliberately usable
as a live experimental trial now, not a claim of physical-MIDI
regression coverage. Historical original Coda MusicXML parity remains
issue #42.
