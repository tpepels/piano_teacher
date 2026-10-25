# Historical work preserved during notation audit recovery

The obsolete implementation worktrees were inspected before cleanup. All local
branch histories were saved in a verified, self-contained Git bundle. Every
untracked or ignored file and any tracked changes were archived and checked
against their original bytes or symlink targets.

Local recovery material lives in
`/home/tom/Projects/piano_teacher-preserved-2026-10-25/`, including its manifest,
per-worktree archives, tracked patches and `all-local-branches.bundle`.

Five patch-unique historical commits remain available on GitHub:

- [`archive/complete-native-notation-2026-10-25`](https://github.com/tpepels/piano_teacher/tree/archive/complete-native-notation-2026-10-25)
  preserves `3fcddf0`, `8876da1`, `6b7a05f` and `73a671a`. They contain optional
  grace-note grading, broader source annotation projection, additional tuplet
  and clef support, interval culling and an alternative sprite spacing solver.
  Some capabilities are already implemented differently on main; the grading
  changes and layout solver require deliberate ports and their own validation.
  Replacing the current tuplet implementation would lose newer singleton and
  source-binding fixes.
- [`archive/reading-visual-feedback-2026-10-25`](https://github.com/tpepels/piano_teacher/tree/archive/reading-visual-feedback-2026-10-25)
  preserves `a887a48`. Its reading feedback concepts are partly superseded by
  the native feedback implementation. Its remaining Learn confirmation and
  badge work is historical WIP, including a contradictory READY-state test.

The two previously untracked teaching handoffs are retained alongside this
document under `2026-10-15-teaching/`. They describe an older revision and are
historical research and future-work context, not current implementation rules.
The extra MIDI files in the UX worktree were already present on main; their
original copies remain in the verified archive.

No unfinished grading change or alternative renderer architecture was silently
merged into the current notation verification fixes.
