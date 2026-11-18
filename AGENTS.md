# Working on this repository

This repository has one product architecture: the Godot 4.7 desktop
application with the embedded CPython engine, a native Verovio notation
renderer, one immutable score stream, and a single MIDI/transport timeline.
ROADMAP.md is the product and phase record. The practice behaviour a learner
sees is specified in docs/practice-flow.md; the owner tests it by hand at the
piano.

## Rules

- Work directly on main; no branches or worktrees. Do not push, force push,
  reset hard, rewrite history, or discard unrelated user changes.
- Make small, coherent commits after a real change.
- Change production code to match docs/practice-flow.md. Never add parallel
  renderers, clock owners, simulated application behaviour or legacy shims.
- Do not report physical MIDI, audio or rendering acceptance from headless
  runs.

## Tests

The test suite is small on purpose (owner decision 2026-11-18): only tests
that guard behaviour a player notices. Run it with `bash scripts/test.sh`
(GitHub runs the same script). Do not add abstract, pixel, parity or
infrastructure tests. Add a regression test only after the owner has
confirmed the behaviour at the piano. A test that encodes behaviour the
owner has since changed is updated or removed, not worked around.
