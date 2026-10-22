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

### Phase 2 — implemented common-notation image gate (PR #36)

Actual 1536 × 520 Godot screenshots are captured by the production native
compositor, not the retired raster renderer. Independent original-MusicXML
parsing supplies pitches, clefs, onset times, rest/note values, accidentals,
explicit beam group boundaries, tie continuations and slur endpoints.

The automated image oracle detects:
- All 64 notehead/staff positions in two two-hand reference pieces (16 isolated
  notes and 48 chord members in 16 captured frames);
- Written quarter, half, eighth and whole REST outlines: atlas glyph
  classification distinguishes exact silhouettes, not merely nearby pixels;
- Sharp, flat and natural accidental shapes at their source pitches;
- Whole, half, quarter, eighth + real flag silhouettes and dotted-quarter
  augmentation mark;
- Horizontal ink bridges for explicitly written beams, an intermeasure tie
  and a slur, including independent source-versus-generated-group checks.

Tests physically remove or move notehead ink, erase staff rails, replace a
rest glyph, or erase continuous marks; negative cases must fail. Artifacts
include every screenshot and the original and generated MusicXML alongside
per-glyph scores and structured errors. The beam tests revealed a REAL
source-to-lesson notation defect: authored <beam> groups were discarded,
resulting in flagged eighths. Projection now preserves complete groups by
source-note ID, hand/voice and unchanged rhythmic duration; incomplete
practice variants do not emit broken groups.

**Phase 2 acceptance scope:** the common glyph and connective classes listed
above, tested as standalone independently authored scores; zero unmatched
source features in those cases, zero image mismatches, passing mutations and
full application integration. Scores or notation classes outside that set
are NOT certified as image-perfect.

Whole-piece coverage, dense overlapping voices, unusual clefs, tuplets and
complex curved marks remain explicitly assigned to Phase 3. This distinction
must survive in CI summaries; a Phase 2 pass must never be presented as
proof of correct sheet music across the entire repertoire.

## Phase 3 — Whole-piece coverage, not chosen excerpts

**PR #37 remains an incomplete proof.** A successful capture or detector check
does not certify a whole score. The completion gate separately requires every
semantic and visual ledger element to be `verified`; `ambiguous`, `unsupported`,
`unverified` and `mismatch` all block it. See
[the Phase 3 framework and findings](native-notation-phase3-framework-2026-10-22.md)
for the implemented contracts, reproducible commands and remaining gaps.

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
