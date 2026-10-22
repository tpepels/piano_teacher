# Native notation Phase 5 remediation

Phases 1 and 2 are merged through PRs #35 and #36. PRs #37 (whole-piece
verification) and #38 (release evidence) remain unmerged dependencies. Phase 5
builds on their exact code and preserves the strict release decision: framework
tests passing does not certify unsupported or unverified musical notation.

## Real-score inventory

`tests/fixtures/phase5-midi-inventory.json` inventories every MIDI file discovered
recursively in `midi/`, with stable ordering, original byte size and SHA-256.
There are 17 MIDI sources, including ten newly supplied pieces. The supplemental
matrix requires 102 reports: 17 sources × Both/RH/LH × two independent categories.
It does not replace the original 17-source Phase 3 corpus or its required reports.
Together the inventories contain 27 distinct sources: 17 MIDI and 10 MusicXML,
or 81 unique source/hand combinations. Seven MIDI sources belong to both
collections; their presence in two reports does not expand the verified scope.
Shared sources can reuse captures only through the existing exact source,
fixture, engine, renderer-dependency and screenshot-hash validation.

The new sources include Hanon's first twenty exercises as one 1,167-measure
file with 18,058 attacks. Every measure remains in scope. Incremental index/hand
execution is available; omitted cases remain required and unverified in the
consolidated report. Added, removed, renamed or changed sources invalidate the
frozen discovery inventory. No filename selects a musical exception.

## Functional corrections

- Authored MusicXML rests are distinct from reconstructed voice padding.
  Projection retains explicit secondary-voice rests, consecutive rests,
  nonprinting rests, rest-only voices and voices whose pitched attacks lie
  outside the active phrase. MIDI display cleanup cannot consume written
  MusicXML micro rests. The two lost rests in `xml_parallel_tied_voices` are
  covered by original-source regressions; deliberately hiding them still fails.
- Same-channel, same-pitch MIDI overlaps preserve all source attacks, velocities
  and physical releases using a documented FIFO interpretation. Moonlight's
  1,164 attacks are no longer rejected. The importer emits explicit ambiguity
  warnings. Independent MIDI verification compares both endpoints and requires
  separate ambiguous pairing obligations for every affected attack; the raw
  source inventory prevents a report from omitting or claiming these as verified.
- Native notation events preserve explicit beam levels, membership and
  attributes, including explicit absence. Independent source/model comparisons
  catch changed metadata; missing fields in older models remain unsupported.
- Whole-measure rests preserve their authored spelling: a 3/4 measure rest
  remains a whole-rest glyph with its measure marker, rather than becoming a
  dotted half rest. Written tie and tuplet attribute bags remain distinct from
  timing and sound ties; unsupported nested display content cannot gain credit.
- Lesson navigation and hand-stage controls occupy a reserved header above the
  notation. The previous floating controls covered the top staff in the source
  fallback at smaller window sizes. Existing staff-pixel thresholds remain
  unchanged; navigation/notation separation has an additional regression guard.
- Pipeline failures retain every independently inventoried original obligation
  in the producer artifact. Aggregation independently restores omitted
  obligations as before; a crash cannot shrink the denominator at either layer.
- The grace engraving regression checks the actual SVG namespace rather than
  depending on a global XML prefix registration left by another test.
- Independent staff detection uses horizontal evidence across the viewport and
  measures stroke consistency separately for each staff. Long ties cannot
  replace an erased gray rule, and legitimate active/inactive ink differences
  do not move recovered rails. Antialiasing, erased/moved rules and authentic
  captured-pixel mutations have dedicated regressions. Pitch and glyph confidence
  thresholds are unchanged; inseparable dense evidence remains unverified.
- Differential rest evidence cannot credit the same changed pixels to two source
  identities in one frame, even when controls have different names or differ by
  one pixel. Such identities remain ambiguous. Distinct displaced rests retain
  credit, and different clocks can legitimately reuse the same playhead pixels.

These corrections preserve original performance data and the existing continuous
scrolling/fixed-playhead architecture. Semantic metadata adds no visual credit.

## Legacy cleanup

The [call-site inventory](native-notation-phase5-legacy-inventory.md) records the
removal of unused inferred beam grouping and eleven compatibility facades.
Tests and audit scripts import their canonical owning modules. Organisation
regressions reject restored facades and stale absolute or relative imports.

The remaining Verovio engraving, raster and score geometry paths have live
purposes: extracting authentic native assets, independent reference images,
existing feedback transforms, and supported fallback for expressions the native
compositor cannot yet draw. Removing those paths now would remove functionality.
They are recorded as retained dependencies, not classified as unused legacy.

## Independent findings and release decision

`scripts/audit_phase5_scores.py` reuses the existing semantic auditor, whole-piece
Godot capture runner, fail-closed aggregator and Phase 4 coverage grouping.
Its report retains independent `categories.semantic` and `categories.visual`
with score, hand, measure and feature denominators. Its findings separate
semantic discrepancies, visual discrepancies and framework limitations.
Canonical `unsupported` statuses remain explicit in every coverage table and
source row. A missing detector is not evidence that the application cannot
render a feature: `unsupported_features_assessment` explicitly records that
application capability is not established by these verification statuses.
Known native fallback dependencies are documented in the legacy inventory.
An import/capture failure is not asserted to be a proven
wrong pitch. Nonverified source rows remain available for exact diagnostics.

The supplemental assessment cannot independently grant a release. The versioned
Phase 4 decision still requires all original reports, clean revision provenance,
all current mutation tests and complete artifact integrity. Phase 5 regressions
are included in the trusted mutation registry, including source-discovery and
failure-accounting guards. Manual editorial review creates no verified credit.

MIDI alone cannot specify a unique written score or unique hand assignment.
Same-pitch overlap pairing is additionally ambiguous. Such rows remain blockers
under the existing strict policy. Original-source transcription references would
be needed to establish written correctness; generated notation cannot serve as
its own expectation. Dense pixel assignment, rest placement, extra/overlapping
ink and other unsupported visual aspects also retain their explicit statuses.
Zero semantic mismatches does not resolve those visual or information limits.

## Performance and application validation

Source-only rest analysis is bounded and cached by exact XML text, across hand
and lesson projections. Native JSON serialization copies owned mutable values
once instead of recursively copying immutable metadata and then converting it
again. These changes preserve the actual capture fixture and screenshot hashes.

Paired local preparation probes used 30 warmed trials per score under concurrent
audit load. Median CPU time was 328.9 ms versus 320.3 ms on the Phase 4 baseline
for a 660-attack MIDI score, and 113.2 ms versus 129.9 ms for a 240-attack MusicXML
score. These measurements describe preparation cost; they do not certify display
FPS or physical keyboard/audio latency.

The practice journeys exercise the current two-measure route, a visible partial
retry, guided recovery, the configured tempo ladder and full-stage mastery.
The modes journey explicitly selects a complete connection through the existing
lesson picker, retaining its source rests, held ending and all 26 original
notes for PCM Listen and uninterrupted Perform. Production grading and recovery
thresholds are unchanged. The complete application run, independent mutation
registries and corpus reports remain separate evidence.

## Reproduction

Use the project's test environment, actual Godot, and software OpenGL with an X
display or Xvfb. Freeze discovery separately before running its auditors:

```sh
python scripts/audit_phase5_scores.py \
  --write-inventory tests/fixtures/phase5-midi-inventory.json
python scripts/audit_phase5_scores.py \
  --inventory tests/fixtures/phase5-midi-inventory.json \
  --out /tmp/phase5-scores --kind semantic
python scripts/audit_phase5_scores.py \
  --inventory tests/fixtures/phase5-midi-inventory.json \
  --out /tmp/phase5-scores --kind visual
python scripts/audit_phase5_scores.py \
  --inventory tests/fixtures/phase5-midi-inventory.json \
  --out /tmp/phase5-scores --summarize-only
```

An incomplete assessment exits nonzero and writes its diagnostics. `--index`
and `--hand` limit execution, not the final denominator. `--reuse-captures`
requires the existing provenance checks and never promotes arbitrary old PNGs.
Run the original Phase 3 and Phase 4 commands separately as documented in
[the release framework](native-notation-phase4-release-evidence.md).
