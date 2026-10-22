# Native notation release evidence — Phase 4

Phase 4 enforces evidence completeness; it does not repair the renderer or
extend the detectors' musical scope. This branch depends on draft PR #37.
The native renderer currently remains **blocked for release**. Phase 3 found
two authored secondary-voice rests lost during lesson projection, and large
parts of the visual notation inventory remain unsupported or ambiguous.

## Decision rule

`scripts/audit_native_release.py` returns zero only when all of these hold:

1. All 17 pinned sources have separate semantic and visual reports in Both,
   RH and LH modes: 102 required reports. Original bytes, ordering, identity,
   hand and every-element inventory are independently checked by the existing
   Phase 3 aggregator. Missing reports restore original-source denominators.
2. Every obligation is `verified`. `mismatch`, `ambiguous`, `unsupported` and
   `unverified` each block release. A producer's `passed: true` alone never
   establishes completeness. Unknown or malformed evidence fails closed.
3. Every report carries the exact checked-out revision and a matching digest
   of tracked application, renderer, oracle, fixture, corpus and CI inputs.
   Relevant uncommitted changes block release. Wrong-provenance rows lose
   verified credit. Godot's generated editor cache is outside this digest.
4. Required semantic, visual, real-rest and release-contract mutation suites
   executed their exact current test inventories. The gate independently
   recollects those inventories and checks raw JUnit XML, file hashes and
   revision. Missing, duplicate, failed, errored or skipped tests block release.
5. Reproducible evidence is present and its manifest matches the exact reports
   and packaged bytes. Missing source/model/reference/capture/diagnostic data
   blocks readiness even when musical counters appear complete.

This is a strict corpus policy, with no score exemptions or manual override.
MIDI performance bytes do not specify a unique written score; its written
transcription sentinel remains unsupported. Resolving that limitation requires
an independently authored transcription reference and new detector evidence,
not changing its status to verified.

## Report contract

The JSON has `schema_version: 1`, `report_kind: native_notation_release` and
`policy_version: native-notation-release-v1`. `release_ready` is a boolean;
`decision` is `release_ready` or `blocked`. `revision` and `provenance` identify
the tested inputs. `required_cases` is 102 for the production corpus.

`categories.semantic` and `categories.visual` remain independent. Each has
`complete`, `correctness` (`verified`, `failed` or `undetermined`), `coverage`,
`cases`, `nonverified_elements` and coverage tables `by_score`, `by_hand`,
`by_measure`, `by_feature`. Every table uses the same counters:
`expected`, `verified`, `mismatch`, `ambiguous`, `unsupported`, `unverified`.
The sum of the status counters equals `expected`. Each dimension preserves
the entire category denominator, including an explicit score-level bucket
when the source does not bind an obligation to a written measure.

Counts represent verification obligations, not unique musical symbols. A note
can have several aspects and independent comparison boundaries. Measure labels
come from the source, including pickups; generated MIDI measures cannot stand
in for measures absent from the original performance bytes. Nonverified rows
retain source identity, measure, staff, voice, expected/actual facts and reason.

`evidence` and `mutations` contain separate integrity/execution verdicts.
`blockers` lists every required failure. `scope.beyond_corpus_verified` is
always false. A passing framework unit suite proves the framework's behavior;
it does not imply a passing release decision.

Manual editorial review is a separate `manual_review.editorial_record` with
`affects_automated_decision: false`. It cannot change automated statuses or
clear blockers. Readability aspects without independent detectors remain
unverified or unsupported even after a favorable editorial review.

## Evidence and diagnostics

`scripts/package_notation_evidence.py` packages the exact per-case report,
original MusicXML/MIDI, generated MusicXML, native model, reference engraving,
actual Godot viewport captures, capture provenance and independent pitch/rest
diagnostics. Its versioned manifest hashes the files and binds each case to
the compact report hash and packaging revision.

Symbol diagnostics and representative failure images are aids for locating
problems. They preserve the distinction between a proven mismatch and an
ambiguous or unverified glyph. Diagnostic overlays do not create additional
verified credit. Original full-resolution captures and complete JSON ledgers
remain authoritative artifacts; editorial layout budgets remain supplemental.

Thresholds are inherited unchanged from Phases 1–3 and are identical across
the corpus. In particular, notehead contour confidence remains 0.79 with a
0.42-staff-step registration limit; adjacent dense assignment remains
ambiguous. Rest silhouette confidence remains 0.65 with a 0.03 family margin,
and requires stable no-op/restored frames and removal of original visible ink.
Half/whole rest identity remains ambiguous when the contours cannot establish
it. A low contour score is failed verification, not an invented pitch defect.

## Local reproduction

Use a clean checkout of the revision being evaluated and the project test
dependencies. The Phase 3 runners create the independent case directories:

```sh
python scripts/audit_phase3_semantics.py --all --all-hands --out /tmp/semantic
python scripts/audit_phase3_whole_pieces.py --all --all-hands --out /tmp/visual
```

Merge their separate canonical case directories under one reports directory.
Keep full visual raw directories available to the packager. The packager and
release gate commands are:

```sh
python scripts/package_notation_evidence.py --reports /tmp/reports \
  --raw /tmp/raw --out /tmp/evidence --revision "$TESTED_REVISION"
python scripts/audit_native_release.py --reports /tmp/reports \
  --evidence /tmp/evidence/evidence-manifest.json --mutations /tmp/mutations \
  --prerequisites /tmp/prior-phases/prerequisites.json \
  --revision "$TESTED_REVISION" --out /tmp/release.json \
  --markdown /tmp/release.md
```

`TESTED_REVISION` must be the full checked-out commit SHA. Historical Phase 3
reports without release provenance are useful diagnostic evidence but cannot
certify a newer revision. CI produces the required mutation manifests and raw
JUnit alongside the corpus evidence; no manual success manifest is accepted.

## CI and release enforcement

`phase4.yml` runs the same reusable `native-release-gate.yml` used by
`native-release.yml`. That gate calls the existing Phase 3 corpus and mutation
workflows. The corpus runs once per gate invocation: 51 independent semantic
reports and a 51-case visual matrix with fail-fast disabled. Phase 1 source
mutations and Phase 2 pixel detector tests remain in the required registry.
The reusable Phase 2 workflow also captures its eight actual native pitch,
chord and symbol probes. The release report independently replays those existing
image oracles on the preserved PNGs and requires their clean revision provenance.
These earlier bounded probes add no whole-corpus coverage credit and cannot
replace Phase 3's independent external-glyph or every-element obligations.

The report/packaging job runs even when upstream audits fail, so a red gate
still produces the coverage decision, manifest, original sources, native
captures and raw mutation JUnit. Downloads may fail without stopping diagnostic
collection; the validators then account for the missing evidence and block.
Audit and release-decision steps cannot ignore failures.

The final gate requires successful corpus, mutations and report jobs, plus
their exact event revision. The native release workflow accepts `native-v*`
tags; manual dispatch must select that same existing tag. Building a Python
distribution and native Godot source candidate requires the passing gate.
Publishing a draft requires the same gate and candidate revision, checks the
candidate checksums, and resolves the remote tag again before publishing.
No release/tag is created by framework tests or normal PR checks.

Evidence artifacts are retained for 30 days in CI. Download and archive them
before expiry when preserving a release dossier. The draft publishing path is
deliberately unreachable while the current corpus is blocked. The ordinary
application integration and earlier standalone proof workflows remain separate
checks; their success cannot override the native release gate.

## Current limitations

- The known authored-rest loss is a genuine renderer pipeline discrepancy;
  it remains a release blocker and is documented in the Phase 3 framework.
- Dense one-to-one symbol assignment, rest placement, general extra/overlapping
  ink, many engraved connectors and rhythm aspects remain incomplete.
- Glyph diagnostics cannot establish full readability beyond detector scope.
- Artifact hashes establish correspondence and reproducibility, not musical
  correctness; the independent semantic and visual oracles remain necessary.
- The gate protects the repository's native release workflow. Administrators
  can still publish outside that workflow; configuring hosting permissions and
  branch rules is a separate repository administration action.
