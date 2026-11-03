# Recover and bound native notation verification

The existing canonical Verovio/native comparison remains authoritative. Work
directly on main. Use retained screenshots for focused fixes; do not launch the
24-shard sweep for this task.

- [x] Inspect the latest shard, live processes, memory events and system logs.
  Preserve a forensic snapshot before stopping the CPU-bound worker.
- [x] Fix the reproducible Liszt notehead assignment runaway with a bounded
  algorithm and positive/corrupted-negative regressions.
- [x] Add atomic per-case checkpoints, provenance-bound resume, a bounded
  submission queue, worker memory limits, case deadlines and progress output
  to `scripts/check_native_verovio_overlay.py`. Keep successful PNGs. Interrupted
  cases remain incomplete and retryable; completed cases with matching inputs
  are reused. Changed verifier code reruns probes on valid retained captures.
- [x] Extend the existing diagnostic ZIP and local shell command to package
  incomplete cases and run state on failure or interruption. Default to two
  workers; expose resource controls through the existing command.
- [x] Fix confirmed unexpected-symbol/tracking, Hanon translation and Verovio
  source/group binding defects using retained XML/SVG/PNG examples. Preserve
  ambiguous evidence and all negative mutation checks.
- [x] Inventory every worktree and branch; preserve dirty and unmerged work,
  integrate valuable changes, remove obsolete worktrees/merged temporary
  branches and prune. Preserve local editor changes before cleaning main.
- [x] Run focused regression and CLI/interruption tests, review changes, commit
  completed work to main and push. Record unresolved notation honestly.

Review focus: interrupted writes cannot become a pass; resume binds exact
source/checker/runtime inputs; timeouts do not omit denominators; one stuck
worker cannot hold the pool open indefinitely; recovery never deletes valid
captures; cleanup preserves every unmerged commit and dirty file.
