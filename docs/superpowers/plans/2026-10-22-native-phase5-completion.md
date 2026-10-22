# Native notation completion plan

**Goal:** remediate real score defects, remove unused notation implementations,
and integrate Phases 3–5 only when their required evidence supports merging.

**Architecture:** retain the original, independently inventoried 17-source
release corpus and its strict semantic and visual categories. Discover every
local MIDI source into an additional hash-bound inventory, reuse the Phase 3
auditors and validators, and keep performance verification separate from
claims about written notation. Functional fixes and cleanup use separate commits.

**Tech stack:** Python, pytest, MusicXML, mido, Verovio, Godot, software OpenGL.

**Specification:** the user's Complete and Merge Phases 1–5 handoff and
`docs/native-notation-proof-phases.md`.

## Constraints

- No threshold changes, omitted scores, self-attested musical facts or passing
  evidence manufactured from renderer output.
- Unsupported, ambiguous and unverified obligations remain explicit blockers.
- Preserve fixed-playhead scrolling, practice, playback, input and progression.
- Develop and reproduce CI locally before a final validated push.
- Merge PRs in dependency order only after their required checks pass.

## Tasks

- [x] Inspect branch ancestry and live PR state: #35 and #36 merged; #37 and
  #38 remain draft and unmerged. Main currently has no branch protection.
- [x] Create isolated Phase 5 worktree from Phase 4, preserving original local
  files and copying the ten newly discovered MIDI files without changing bytes.
- [ ] Add hash-bound MIDI discovery and supplemental whole-piece evaluation,
  reusing both independent auditors and the existing fail-closed aggregator.
  Regressions cover added/deleted/changed sources, duplicate identities,
  missing modes, runtime failures and unsupported transcription.
- [ ] Reproduce authored secondary-voice rest loss; add regressions before
  correcting projection while retaining suppression of synthetic gap clutter.
- [ ] Inventory legacy callers and remove only demonstrably unused code.
  Validate necessary reference engraving and diagnostic paths remain intact.
- [ ] Run every discovered score in all three modes. Separate musical defects,
  visual defects, unsupported constructs and framework limitations in findings.
- [ ] Correct confirmed new defects with regressions and repeat targeted checks.
- [ ] Run full application, notation, mutation and release checks locally;
  preserve coverage and provenance, record actual limitations and performance.
- [ ] Review integrated changes, batch logical commits, then use final hosted
  CI. Merge completed phases in dependency order, rerun final main checks and
  remove only obsolete branches with no unmerged work.

## Review focus

1. Discovery cannot silently omit a newly added or renamed source.
2. A runtime error must retain the source and its independent denominator.
3. Synthetic secondary-voice rests must not make authored rests disappear.
4. Legacy removal must preserve genuine reference engraving and practice paths.
5. Green framework tests must never override blocked release evidence.

## Evidence record

Initial release evidence on Phase 4: 102/102 reports with complete artifact and
mutation execution, but 34 discrepancy obligations from two lost authored rests
and extensive unsupported/ambiguous visual obligations. These are unresolved
work, not a reason to bypass or relabel the gate.
