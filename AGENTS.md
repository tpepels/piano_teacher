# Local autonomous CI repair agent

This repository uses one active product architecture: the Godot 4.7 desktop
application with the embedded CPython engine, a native Verovio notation
renderer, one immutable score stream, and a single MIDI/transport timeline.
ROADMAP.md is the authoritative product and phase contract. Read it, README.md,
docs/README.md, and the affected source before modifying tests.

## Assignment and completion criteria

Work directly on the checked-out main branch. Do not create worktrees or
feature branches. The local launcher scripts/local-ci-agent.sh drives this
assignment (Claude Code by default, Codex optionally); do not spawn another
copy of that launcher from inside an agent turn. Read
docs/verification/ci-repair-log.md first: it is the durable hand-over record
of completed work, current failures, commits and remaining tasks. Append to
it in every turn.

The two mandatory phases are sequential:

A. Audit ALL collected pytest tests, Godot test harnesses and the workflow
   definitions against the current executable application.
   Remove or rewrite obsolete tests for retired HTTP/UDP/Qt servers, duplicate
   transports, discontinued UI, removed generator strategies, and old
   compatibility behavior only after tracing their tested behavior to actual
   production code. Do not remove a failing test merely because it fails.
   Keep relevant regression, migration, security, performance and original
   research-parity tests where the current product still owns their behavior.
   A mixed module must have its individual cases reviewed. Every native test
   script and every workflow must be traced to a current owner, or deleted
   with the reason recorded. Track each removed test, the retired contract,
   and any replacement in
   docs/verification/ci-current-scope-audit.md. Classify every remaining pytest
   module, native Godot harness and workflow in tests/ci-scope.json with an
   actual current source owner and a
   concrete tested contract, then pass scripts/ci-scope.py --check. Ensure
   pytest collection, the four-shard plan, smoke selection, and strict xfail
   paths still point to existing and appropriate tests. No blanket renaming,
   skipping, deselecting, or excluding a shard to manufacture a green result.

B. Fix every remaining CURRENT product/test defect, one failing shard and
   its first actionable failure at a time. The launcher runs the four-part
   full suite, stops at the first failing part, and supplies its log for the
   next repair turn. Inspect complete tracebacks, real Godot framebuffer
   output, test artifacts and current code. Prefer repairing production code
   when it is wrong; adjust assertions only when the model is demonstrably
   wrong and preserve independent negative controls and numeric tolerances.
   Reproduce the original failure, add/keep a regression, run focused checks,
   commit one coherent fix, and return control to the launcher. Never add
   parallel renderers, clock owners, simulated application behavior or legacy
   shims to satisfy obsolete tests.

Known observed failure at the start of this handoff:
tests/test_note_status_framebuffer.py reported a missed half note
(head_half) with recolor mean pixel error 8.426 > 6.0 and an apparent
detached glow. Earlier rounds had whole-note mask-coordinate defects;
those projection fixes already landed. Do not assume the next failure is
identical: inspect the current log and PNGs. Previous speculative fixes in
native glyphs and the framebuffer test have not been accepted by a local
passing run.

## Per-turn operating rules

- Read the current launcher log and files before editing. The launcher owns
  shard execution. You may run focused pytest/Godot tests within a repair
  turn, but do not rerun a full suite in a second concurrent process.
- Verify the current branch is main and preserve unrelated user changes.
  Make small, reviewable commits directly on main after a real change.
  Do not push or force push, reset hard, discard untracked user files or
  edit history. Commits remain on the local main until the owner publishes them.
- Do not weaken the CI gate, reduce coverage, introduce unjustified xfails,
  or silently change the interpretation of a research/engraving contract.
- A failing relevant test stays until fixed. A suspected legacy test requires
  evidence of the removed implementation and explicit documentation of its
  deletion or replacement. Maintain a complete test inventory for every
  remaining module, including new tests added during repairs.
- Preserve test diagnostics on failure. Distinguish unavailable hardware
  from software failures; do not report physical USB/Bluetooth acceptance
  as achieved from headless tests.
- All test removals, quarantine changes, and CI-selection modifications
  must be supported by the scope audit, with the exact test names logged.
- Do not mark the work complete from a focused run, a past green commit, or
  four independent shards on different revisions.
- During scope work use scripts/ci-scope.py --inventory to inspect the
  complete module list, and scripts/ci-scope.py --check to verify registry
  coverage. Only declare scope complete after auditing every test module and
  its cases, recording the findings and committing the manifest.
- End each agent turn with: root cause, files changed, tests actually run,
  commit SHA, unresolved failures. Do not claim a pass without executing it.

## Final acceptance

A: scripts/ci-scope.py --check passes and
docs/verification/ci-current-scope-audit.md records the reviewed current
scope, deleted obsolete cases and retained regression/migration contracts.
There must be no current CI selection of a removed legacy-only test.

B: the checked-out clean main revision passes all FOUR full shards at the
SAME commit, with no unresolved tests/quarantine entries. Also pass
scripts/ci-smoke.sh, scripts/check-godot-syntax.sh and the focused and corpus
hybrid verification scripts at that same commit. Where any physical acceptance
gate remains unavailable, record it separately and do not claim it passed.

The launcher runs until these gates are met or a genuine no-progress,
permission, environment or execution error requires human intervention.
Do not declare success or bypass an unresolved gate.
