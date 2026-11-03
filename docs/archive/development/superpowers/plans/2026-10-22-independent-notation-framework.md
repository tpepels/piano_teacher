# Phase 3 independent notation framework

The user handoff is the acceptance specification. Continue PR #37 on its existing
branch; preserve production rendering unless independent evidence establishes a
defect. Source expectations must come from original MusicXML/MIDI, never native
geometry. Ambiguity and unsupported features must remain visible and prevent a
claim of complete verification.

1. Extend the semantic source contract to written rests, voices, ties, beams,
   tuplets and measure structure. Add source-linked discrepancies and mutation
   tests. Own `proof.py`, a new semantic runner, and semantic tests.
2. Validate differential rest isolation against actual screenshots. Test missing,
   wrong, displaced, occluded and contaminated masks. Separate contour evidence
   from identity/placement, and classify verified/failed/ambiguous/unsupported.
   Own `phase3_pixels.py` and its visual mutation tests.
3. Split semantic and visual CI reports/artifacts. Harden corpus aggregation
   against missing evidence, forged counters, wrong source identity and partial
   windows. Account explicitly for unverified source constructs. Own workflows,
   aggregate runner and aggregation tests.
4. Run the complete 17-source, three-hand matrix, examine diagnostics and actual
   PNGs. Record genuine renderer issues separately. Run the complete test suite
   and independent review. Update PR evidence and merge only if trustworthy.

Validation: each detector's deliberate mutations must fail, legitimate dense
polyphony/displaced rests must not be called incorrect, and absent evidence must
not pass. Reports include exact source/measure/voice identity. No score-specific
exceptions or threshold relaxation. Full corpus failures remain merge blockers.

Review focus: original/generated shared mistakes, use of renderer atlas/geometry
as expectation, mask contamination and occlusion, ambiguous block rests, and
aggregate success on empty/malformed or mismatched reports.

Progress
--------
- Initial branch: aaf969b; clean isolated worktree. Baseline focused tests running.
- Ruling: proceed under the user's explicit completion brief; no additional
  design approval needed for this existing framework handoff.
- Source contracts, canonical ledgers, separated workflows and all 51 capture
  cases implemented. Production renderer code remains unchanged.
- Ruling: run all 51 semantic cases in one headless CI job and remove redundant
  two-score pilot captures. This preserves every case/artifact while avoiding
  repeated dependency installation; if wrong, the tradeoff is less parallel
  semantic execution, not reduced coverage.
- Ruling: adjacent head silhouettes and unison voices are ambiguous until a
  joint pixel assignment is demonstrated. The former .75 adjacent allowance
  was removed; this sacrifices coverage rather than permitting false proof.
- Ruling: legitimate pickup label projection and source-unspecified tuplet
  engraving receive explicit correspondence/limitations rather than musical
  mismatches. Authored visible rest loss remains a mismatch.
- Final independent review: six Important findings. Each was reproduced and
  fixed with RED/GREEN regressions: adjacent-chord pitch false verification,
  dark-added rest controls, omitted theme/engine capture provenance,
  transposition/unknown attribute omissions, hidden-source event false defects,
  and missing-report denominator loss.
- Focused verification: 318 tests passed, including actual Godot wrong/hidden
  glyph mutations. Full suite: 1,284 passed, 5 skipped, four baseline failures
  independently reproduced on unchanged main (see findings document).
- Full semantic matrix: 51/51 reports, 48 zero-mismatch cases, three cases with
  the two authored secondary-voice rests lost. 204,657 ledger obligations:
  199,260 verified, 42 ambiguous, 5,325 unsupported, 30 mismatch, zero unverified.
- Final visual matrix: 51/51 cases, 513 windows, 13,032 native PNGs and 1,242 rest
  controls. 88,832 obligations: 11,336 verified, 7,136 ambiguous, 70,020
  unsupported, 336 unverified, four mismatch obligations for authored rests.
- Six attack-free tail captures were recovered by joining empty windows to
  adjacent context. Every measure now has actual framebuffer evidence; no
  source is exempted. Font expectations read installed Leipzig files directly
  rather than relying on mutable toolkit resource defaults.
- A final actual-image regression demonstrated correct ledger/stem ink can
  lower a head match. Low matches remain failed, unverified evidence rather
  than proven wrong pitches; thresholds and verified credit are unchanged.
- Complete semantic/visual aggregation is blocked. No complete proof or merge
  is authorized by partial passes. Detailed results are in the findings report.
