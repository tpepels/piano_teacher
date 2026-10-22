# Native sheet-music correctness: verification phases

**Status:** Phase 1 is the first independent semantic evidence gate. A passing
Phase 1 report does **not** establish correct native rendering. Do not claim
"sheet music verified" from this gate, the existing 15 viewport overlays,
or the general 900+ unit-test count.

## Phase 1 — Independent source-to-model semantics (PR #35)

Oracle: read **original MusicXML**, not the application's importer result.
Compare each unsimplified full-score note's pitch, written spelling, onset,
and sounded duration (including tie continuation), and every measure boundary
and explicit meter/key/clef against the native model. Separately inventory
**every** note/rest in the generated XML that Verovio receives and compare to
the native model: duration, position, staff, voice, type, dots, ties,
accidentals, tuplets and note IDs.

Gate: no unmatched events. Deliberately corrupted source/note/measure/model
facts must fail. Produce per-piece JSON with covered quantities and failures.

**Out of scope:** individual drawn pixels; beaming/slur/ornament positioning;
full MusicXML layout semantics; MIDI's inherently ambiguous written rhythms.
The corpus includes all ten supported MusicXML fixtures from the manifest,
including the 240-note multipage score; it is still not the full repertoire.
A failure must be corrected or explicitly classified as an unsupported feature,
not made to pass by widening numerical tolerances.

Run: `python scripts/audit_notation_proof.py --out /tmp/notation-proof.json`
and `pytest tests/test_notation_proof_phase1.py`.

## Phase 2 — Native geometry and ink verification

For an independently authored MusicXML corpus, collect every rendered symbol
at every needed fixed-playhead viewport position, not four samples per excerpt.
Compare staff-step vertical coordinates, accidental identity and side,
notehead/ledger-line pixels, rest shapes, stem/flag/beam connections, ties and
tuplet/slur contours against Verovio's identified engraving primitives. Use
source-linked anchors and scale/translation registration; do not equate optical
print horizontal spacing with constant-beat practice spacing.

Gate: zero missing/extra/incorrect/illegible symbols within documented
geometric tolerances; fail if any score symbols are never exercised at all.
Mutation testing must prove that moving one notehead by one staff step or
hiding a symbol is caught.

### Phase 2 implementation checkpoint (PR #36)

The first real-pixel gate verifies 16 isolated notes and 48 ordinary triad
tones, over 16 frames from two independently authored MusicXML sources.
It locates staff lines and *actual notehead ink peaks* in PNGs captured by the
canonical Godot renderer. Expected diatonic positions, clefs, onset groupings
and chord inventories come from the original source MusicXML, not from Godot's
notehead/staff telemetry. Image-mutation tests shift and delete pixels and
show the validator rejects them.

Passing this gate establishes staff-pitch image correctness **only for these
supported regular patterns**. It does not establish complete Phase 2,
professional engraving, glyph type correctness, or every score's accuracy.
Remaining tasks include independent rest/accidental/beam/tie geometry checks
and regression testing of actual dense score frames.

## Phase 3 — Whole-piece coverage, not chosen excerpts

Audit *all* measures of each bundled score in right/left/both settings,
repeat with independent MusicXML reference scores covering ordinary piano
notation (single notes, chords, rests, rhythm values, dots, beam groupings,
accidentals, keys, ties, voices, ledger lines, clef changes, pickups and
tuplets). Record counts of covered and uncovered source constructs.
Split supported and unsupported cases explicitly.

For MIDI, verify every performed note and timeline position and test
transcription rules against curated musical expectations. MIDI cannot prove
a unique correct written score.

Gate: 100% of supported source events have independent semantic and visual
evidence; every unsupported construct is named and never silently dropped.

## Phase 4 — CI release evidence

Combine Phases 1–3 into one machine-readable, versioned audit summary.
Run mutation checks regularly; publish source engraving, native viewport
captures, symbol-level diffs and failure exemplars as artifacts. Apply the
same score-independent thresholds across the corpus. Document any manual
editorial review separately from automated claims.

Release gate: supported scores have **zero unresolved correctness
discrepancies**. Failing scores block the native renderer release rather than
being removed from the corpus or granted score-specific exemptions.
