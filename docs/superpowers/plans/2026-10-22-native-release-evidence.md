# Phase 4 — native notation release evidence

The user requests autonomous implementation of the Phase 4 requirements in
`docs/native-notation-proof-phases.md`. This branch stacks on draft PR #37;
Phase 3's blocked results remain blockers. Production rendering is outside
this change.

## Design

Reuse the fail-closed Phase 3 aggregator for each independent category. A
versioned release report adds coverage by score, hand, feature and original
measure, immutable revision binding, mutation evidence and artifact integrity.
No manual review or unsupported construct can override the automated verdict.
The release policy requires all 102 reports, all obligations verified, required
mutation suites executed without skips, and complete reproducible artifacts.

An evidence packager indexes and hashes original sources, generated XML/models,
reference engravings, actual native PNGs and independent symbol diagnostics.
It creates bounded diagnostic exemplars without changing verification facts.
Missing expected artifact classes explicitly block readiness.

CI reuses the existing corpus and mutation workflows, publishes reports even
when audits fail, and exposes a required release gate to a native release
workflow. Publishing requires the exact tested revision and a passing gate.
No existing publishing workflow exists as of this change.

## Implementation and validation

1. Establish isolated branch on PR #37; run existing accounting tests.
2. Add release report tests first: rejected missing/forged evidence, exact
   independent verdicts, all nonverified statuses, grouped coverage and binding.
3. In parallel, add artifact packaging/diagnostics with integrity regressions,
   and reuse/wire CI with workflow contract tests. Keep write sets separate.
4. Integrate on real existing 102-case evidence; record a blocked decision,
   never fabricate a passing corpus. Add policy/packaging commits separately.
5. Independently review trust boundaries; run focused and application checks.
6. Push a stacked PR, validate actual CI, document commands, results, release
   decision and remaining limitations. Keep PR #37 draft and unmerged.

## Work ledger

- Initial inspection: PR #37 head `1d8e47f`, unmerged; all known source and
  capture artifacts are available locally for integration validation.
- Underlying renderer is not release-ready: known lost authored rests and
  unsupported/ambiguous/unverified obligations remain explicitly recorded.
- Release policy/provenance implemented with red/green regressions. Independent
  review reproduced and fixed dirty mutation execution being accepted and an
  unhashable visual element ID crashing aggregation. Mutation snapshots now bind
  both ends of execution; malformed inventories retain blocked diagnostics.
- Actual Phase 2 probes are also a release prerequisite, replayed through the
  existing image oracles. All eight probes passed locally (64 independently
  measured noteheads and 53 frames). Invalid literal-newline JSON endings in
  the legacy pitch runner were reproduced and corrected; tolerances unchanged.
- Real historical 102-case evidence was consumed as a negative release test:
  absent revision provenance removed verified credit and blocked readiness.
  Historical evidence was never relabeled or promoted to a current-head pass.
