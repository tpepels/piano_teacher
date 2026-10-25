# Native notation audit recovery — 25 October 2026

## What stopped shard 0

The run had stalled, rather than exited unexpectedly. At inspection it had
finished 631 of 632 cases; one Python worker was still using a CPU core while
the remaining pool workers waited. The unfinished case was Liszt,
`learn-0065-both-original`, at note-feature registration for five simultaneous
heads. Replaying its original XML and PNG reproduced repeated stacks inside
`raster_matching.claim/assign/search`.

The old candidate-node limit did not bound recursive pixel ownership work
inside each candidate. A concrete overlapping pair required 783 pixels but
had only 728 available. The other heads made the global capacity total look
sufficient, so the old search repeatedly attempted impossible ownership.

No matching kernel OOM, systemd-oomd, segfault or killed-process journal entry
was found for the relevant period. The inspected cgroup's OOM counters were
zero. The process was live; memory exhaustion is not the supported cause.
After saving the evidence, only the identified stuck audit worker was sent
SIGTERM. The old coordinator then produced its final failed summary:
632 attempted cases, 361 failed cases, 21 sources and 270 original measures.
Those numbers describe the old run, not a rerun with the fixes below.

Local forensic evidence is retained under
`notation-check-results/interruption-2026-10-25/`, including the prior summary,
run log, process/memory investigation, repeated-stack reproduction and
`triage.zip`. The original case captures were retained.

## Memory and interruption controls

The live Python pool used roughly 3 GiB RSS combined, with individual observed
high-water marks around 0.65–0.71 GiB. This is not a measurement of the peak
combined Python-plus-Godot load during capture. A separate two-case real Godot
probe completed both captures under the new limits: about 6.5 seconds each,
Python peaks of 151–154 MiB and renderer peaks around 707 MiB each. Seven
simultaneous captures can add substantial pressure; they were not the cause
of this observed CPU stall.

The existing runner now defaults to two workers and limits outstanding jobs
to that worker count. Workers use one BLAS thread, a 3 GiB virtual address
space limit inherited by renderer subprocesses, recycling after eight cases,
and a ten-minute case deadline backed by a coordinator watchdog. Requested
concurrency is also capped using available memory. Resource limits are
explicit controls, not a claim of a measured whole-pool RSS ceiling.

Each case writes atomic stage and result checkpoints. Reuse requires matching
source/checker/runtime identity, report/input hashes and capture provenance.
Completed comparisons, including completed failures, are resumed; changed
checks re-examine valid PNGs without another Godot capture. New captures are
staged before publication. A failed replacement keeps the prior capture;
interrupted publication can finish from its complete staging directory.

SIGINT, SIGTERM, worker crashes and timeouts retain partial evidence and
package a bounded diagnostic ZIP. SIGKILL or power loss cannot run a cleanup
handler: the next invocation packages the previous atomic run state before
overwriting its summary. Missing or unreadable sources keep coverage totals
explicitly incomplete. The next run retries incomplete work. Previously
deleted captures from the old runner cannot be recovered by checkpointing.
Validated process-lifetime records stop surviving workers and renderers before
restart planning; reused PIDs are never signalled. Previous-boot records retire
without signals. Cleanup escalates surviving renderer children independently
of whether their Python worker has already exited.

## Confirmed verification defects fixed

- **Joint head ownership:** exact capacity checks for every selected subset
  and a small membership-class flow graph replace recursive pixel assignment.
  Placement, candidate and ownership work are bounded. The retained Liszt
  feature probe now returns in about 1.5 seconds; it still reports 18 of 42
  features unverified rather than inventing proof.
- **Unexpected heads/rests and source tracking:** family scans include the
  complete neighboring contour before suppression, source heads use strict
  pale-ink registration with measured context, disconnected dots cannot become
  one rectangular rest, and flag-loop attachments remain ambiguous rather
  than definite extra heads. All 11 source heads in the selected Clair replay
  bind; its three insufficiently visible rests remain unbound.
- **Verovio groups:** complete visible source voice sequences bind only to a
  unique compatible printed SVG layer with preserved IDs. Hidden cursor
  padding is excluded. All 34 formerly unbound groups across the 21 inspected
  retained cases acquire structural bindings; that does not certify their ink.
- **Hanon scrolling:** all allowed horizontal shifts are evaluated using exact
  row-preserving pixel intersections. The genuine shift was outside the old
  eight-entry column shortlist. All four inspected motion probes now pass;
  frozen, reversed and jumping mutations still fail.
- **Rest dots:** eight-connected changed contours distinguish adjacent circles;
  independently registered body ownership separates a dot sharing a short
  rest's horizontal range without borrowing its flag bulbs. Four retained
  cases verify 11/11 rest glyphs and placements, including genuine triple dots.
  Erased, extra, wrong-shape, joined, unchanged-neighbor and control-only dark
  dots are rejected. Each dot and the rest body must independently match
  visible pale ink that the suppression actually removed; genuine dots cannot
  lend visibility credit to a body drawn only in a corrupt control image.

The existing Dice, family-margin, visibility, corridor and clearance thresholds
remain unchanged. Ambiguous evidence is still blocking. No renderer/layout or
grading semantics were changed to make these verification cases pass.

## Remaining rendering and verification issues

- Two existing actual-framebuffer regressions still fail on the unchanged
  baseline: simultaneous half/quarter unisons share the same native position
  instead of owning distinguishable heads and shafts. They require a renderer
  layout change and corresponding independent physical registration.
- The retained Moonlight tuplet's source group now binds, but its bracket is
  still missing/detached. Its numeral match does not certify the bracket.
- Dense Liszt head ownership remains unresolved within the bounded search;
  dependent flag-absence observations remain unverified. Three selected Clair
  rests remain below the contour threshold or outside the readable corridor.
- Touching/occluded rest dots, more than three dots, global unowned-ink absence,
  and incomplete cross-frame source ownership remain explicit limitations.
- Remaining measure-boundary, tie, ledger and accidental failures across the
  library have not been certified or eliminated by this focused work. Existing
  positive and corrupted-image checks remain active. There was no 24-shard rerun.

## Git preservation and local verification

Focused validation completed without a full shard or library rerun:

- Final `--ci` command: **129 passed**, plus Godot script parsing.
- Wider pixel/structure scope: **260 passed, 4 opt-in tests skipped**.
- After the final control-ink tightening, affected rest scope: **184 passed**.
- The four opt-in live Godot framebuffer tests were then enabled: **4 passed**,
  including wrong/hidden native glyph mutations.
- Runtime review scope: **39 passed**, including actual coordinator SIGKILL,
  restart, interrupted initialization and a TERM-ignoring child process.
- Two fresh real captures completed concurrently under the resource limits.

These scopes overlap and their counts should not be added. Two separate native
unison regressions were confirmed failing against the unchanged baseline and
remain listed above; no test was removed or weakened to hide them.

Six obsolete worktrees were removed after byte-verified preservation; one
missing worktree registration was pruned. Twelve old temporary local branch
names were removed. Five unique historical commits remain on two pushed
archive branches, with a verified local Git bundle and all dirty/untracked
files saved. See [the preservation inventory](archive/worktree-preservation-2026-10-25.md).
Historical teaching notes were integrated into the documentation archive.
Alternative grading/layout work remains archived for deliberate future ports.

The recommended local command remains:

```bash
./scripts/verify-notation.sh
```

It resumes compatible completed cases and retains good captures. It stops at
the first failing batch; only a complete pass of all 24 batches establishes
full-library verification. Its internal `--ci` mode runs focused fixtures and
Godot parsing only.
