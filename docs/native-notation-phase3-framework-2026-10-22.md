# Independent notation framework — 22 October 2026

PR #37 is a draft. The framework reports evidence and fails closed; the current
detectors do not establish complete independent visual correctness. Production
rendering has not been changed to make this audit pass.

The completed local run is recorded in the
[102-case results](native-notation-phase3-results-2026-10-22.json). Both independent
boundaries contain all 51 reports and all 17 sources, with no source-inventory
accounting errors. There are 513 captured windows, 13,032 native PNGs and 1,242
rest suppression controls. Completion remains blocked:

| Boundary | Verified | Ambiguous | Unsupported | Unverified | Mismatch |
| --- | ---: | ---: | ---: | ---: | ---: |
| Semantic | 199,260 | 42 | 5,325 | 0 | 30 |
| Visual | 11,336 | 7,136 | 70,020 | 336 | 4 |

The 30 semantic obligations and four active-hand visual obligations marked as
mismatches trace to the two authored voice-2 rests described below, not 34
distinct lost symbols. Forty-eight semantic cases and 41 visual cases have no
failed evidence checks; **zero cases have complete coverage**. The focused suite
passes 318 tests, including three real Godot rest-mutation tests. The full suite
recorded 1,284 passes, five skips and the four unchanged-main failures below.

## Independent boundaries

The semantic job reads original MusicXML with an ElementTree cursor, rational
durations and independent tie accounting, and original MIDI with an independent
physical attack/release decoder. It compares original facts against both the
generated written score and native model. Generated/native agreement alone is
insufficient. Voice numbers may undergo an explicit, consistent injective lane
rename. Source identity, original measure label, staff and voice accompany each
discrepancy. Native fields not represented by the schema remain unsupported.

The visual job recovers staff rails from actual 1536 × 520 Godot framebuffers.
Written pitch/clef facts select the expected diatonic row. Glyph outlines come
directly from the installed Verovio font, independently of the atlas supplied
to the renderer. Matching searches the public fixed playhead region; it uses
no renderer-reported head/staff/rest position as expected geometry. Renderer
identity/proximity checks are supplemental and do not establish pixel proof.

Attack-free windows are joined to adjacent context, including opening silence
and held or silent tails. No bar is skipped for having no new note attack. This
repaired six final-bar capture gaps found by the independent coverage audit.

Source-directed head searches verify presence at a required pitch. They do not
detect every extra glyph elsewhere. Unison voices can share one silhouette,
and adjacent head searches can reuse neighboring ink; both remain ambiguous
pending joint pixel assignment. Seconds can displace an entire chord stem group; its horizontal
search region is inferred from the written chord. Registration remains below
one staff step at every detected staff scale. No score-specific thresholds apply.

A low local silhouette score is `unverified`, rather than a proven wrong pitch.
An actual correct octave chord with ledger/stem interference is retained as a
PNG regression fixture with source and capture provenance. Moved or erased heads
still fail verification; this distinction gives no additional verified credit
and does not change the match threshold.

## Rest subtraction experiment

Protocol 2 captures the original framebuffer, a no-op repeat, one full-frame
control per suppressed rest, and the fully restored framebuffer. The repeat and
restored images must exactly equal the original. Controls must remove visible
original pale ink in a bounded onset region, add no unrelated bright ink, and preserve the full
viewport dimensions. Full frames expose contamination outside the old crop.
IDs select the intervention; XML supplies expected facts; pixels supply evidence.

The isolated visible contour is compared with authentic Verovio silhouettes.
A confident competing family is a mismatch. Missing, occluded or inseparable
contours remain unverified. Legitimately displaced rest contours are accepted
without claiming their placement is correct. Whole and half rest rectangles
remain ambiguous; neither receives full identity credit from shape alone.
Dots, voice-lane correctness and overlap clearance need separate evidence.

Actual Godot mutations replace a quarter-rest atlas outline with an eighth rest
and make it invisible. The independent checker rejects both despite the atlas
claim. Synthetic mutations additionally exercise frame drift, contamination,
missing captures, wrong contour families, erased/moved heads and small staff
scales. A vectorized matcher is tested against the scalar pixel comparator;
its candidate positions, Dice scores and thresholds are unchanged.

## Coverage and CI

The pinned corpus contains seven bundled MIDI pieces and ten MusicXML reference
scores. Each is audited in RH, LH and Both modes: 51 independent cases per
boundary. Semantic and visual jobs, artifacts and aggregate reports are separate.
The short semantic matrix runs in one headless job with 51 individual reports;
this avoids 51 repeated dependency installations. Visual captures retain a
51-case parallel CI matrix. Redundant two-score pilots have been removed.

Each schema-version-1 report binds its source index, exact filename, SHA-256 and
hand. Its ledger gives each construct a stable identity, source location,
status, reason and evidence. The aggregate independently reconstructs the
original source inventory; omitted IDs restore the denominator as unverified.
It also rejects changed bindings, duplicated IDs, malformed counters, swapped
sources, incomplete/duplicated measure windows and inconsistent flattened
window ledgers. MIDI's lack of an authored written score remains unsupported.

One original note produces separate pitch, rhythm, stem/flag/dot and connector
obligations where applicable. Explicit clefs, keys, meters, barlines, tuplets,
directions and other written constructs remain in the visual denominator even
where no pixel detector exists. A pitch/rest-only ledger cannot certify a score.

Commands from a checkout with the `godot,test` extras installed:

```sh
rtk proxy python scripts/audit_phase3_semantics.py --all --all-hands --out /tmp/phase3-semantic
rtk proxy env LIBGL_ALWAYS_SOFTWARE=1 python scripts/audit_phase3_whole_pieces.py --all --all-hands --out /tmp/phase3-visual
rtk proxy python scripts/aggregate_phase3_corpus.py --kind semantic --root /tmp/phase3-semantic --out /tmp/phase3-semantic-coverage.json
rtk proxy python scripts/aggregate_phase3_corpus.py --kind visual --root /tmp/phase3-visual --out /tmp/phase3-visual-coverage.json
rtk proxy env PIANO_REAL_PIXEL_TESTS=1 LIBGL_ALWAYS_SOFTWARE=1 python -m pytest tests/test_phase3_real_rest_protocol.py -q
```

The visual commands require a graphical display (CI uses Xvfb). A single case
uses `--index I --hand right|left|both`. `--reuse-captures` reanalyzes stored PNGs
only if their source/layout/protocol fixture and recorded hashes still match.
Reuse checks include shared theme/resources, engine version and actual PNG
hashes. Capture manifests preserve Godot, Verovio and Python versions. CI uploads actual
PNGs, source/generated notation, model data, logs and machine-readable failures.

## Findings kept separate from framework fixes

The original `xml_parallel_tied_voices.musicxml` contains two explicit visible
rests in voice 2: a half rest in measure 1 and dotted half rest in measure 2.
The lesson generator sets them to `print-object="no"`; the native model omits
them. `lesson.py::_render_measure` hides secondary-lane gap and trailing rests
without distinguishing these authored rests from reconstructed MIDI silence.
The expanded original-source contract detects this loss. No exception is added,
and production code has not been changed in this PR to hide the failure.

Pickup measure labels and source-unspecified tuplet engraving are normalization
cases requiring explicit correspondence/limitations, not automatically musical
errors. Checker regressions preserve this distinction. A real Autumn Leaves
frame also exposed a checker error in chord displacement; the same captured PNG
passes after the source-derived search correction, without changing rendering
or silhouette thresholds.

Four unrelated tests were reproduced failing unchanged on `main`: the local
Merry-Go-Round stage-count assertion, instructional learner-unit assertion,
mode-journey note-count assertion, and nine raster staff-visibility checks. They
remain separate from Phase 3 findings. Launcher verification requires the test
virtual environment on `PATH`.

## Remaining limits

Full-piece pixels do not yet independently certify stems/flags, augmentation
dots, accidentals, all connective marks, rest placement, overlapping symbols,
key/clef glyph identity, meter glyphs or absence of arbitrary extra ink. Dense
inseparable silhouettes and the half/whole rest family remain ambiguous.
MIDI verifies physical performance facts, not a unique written transcription or
sustain-pedal sounding duration. These gaps block the complete corpus verdict;
passing mutation suites must never be presented as complete notation proof.
