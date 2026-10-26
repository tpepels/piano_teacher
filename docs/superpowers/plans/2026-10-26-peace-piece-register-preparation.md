# Peace Piece: register engraving and full preparation

Use systematic debugging, TDD and independent framebuffer verification. Continue
on main as authorized in this session; preserve existing user/editor state.

## Confirmed evidence

- Source MIDI: first meters `(0,1,8)`, `(.5,4,4)`; measure grid starts
  `0,.5,4.5,8.5`. The repeat descriptor currently chooses the literal opening
  1/8, producing only .5 quarter beats of preparation.
- At beat .5–2.5 the right-hand source voice `midi-t0-c1` contains pitches
  36,60,64,67; at 2.5–4.5 it contains 43,60,62,65,67. The original hand,
  onsets, releases, tracks, channels and source identities are immutable.
- Generated MusicXML groups each set into one treble-staff chord. Full Verovio
  independently produces the same long stem and ledger ladder, so clipping
  native stems or changing MIDI hands would hide the generating defect.
- Before artifacts: `playtest-results/peace-piece-regressions/before/`, including
  actual native PNGs, generated XML, source model, chord assets and full Verovio.

## Decisions

- Separate performing hand from display staff. For MIDI-only engraving, a remote
  register cluster in an extremely spread chord may use the other existing
  piano staff and an independent notation voice. Source hand and source voice
  remain unchanged in `model.notes` and every binding. Ordinary chords and
  authored MusicXML retain their notation. No pitch transposition or stem cap.
- Select register partitions using clef-relative ledger cost and a substantial
  gap between adjacent chord tones; require a clear improvement on the other
  staff. Reuse that decision for all tied segments and simplified variants.
- Add explicit performing `hand` to notation events; `staff` continues to locate
  actual musical ink. Validate each performing hand against the source note,
  even when its display staff differs. Native colors, feedback and fingerings
  use the performing hand; clefs, pitch Y and layout use the display staff.
- Use existing bounded pickup-meter policy for preparation, preserving the
  source 1/8 and its .5-beat duration while selecting the immediately following
  4/4 as a full four-beat preparatory measure. Genuine sustained 1/8 meters and
  unrelated later meter changes must not be reinterpreted.
- Backend and native must consume the same preparation context/duration,
  including restoration before the source pickup. No hidden count-in or delay.

## File ownership and tasks

- [x] Parent: source register policy helper; `notation/lesson.py`, `model.py`,
  source/Verovio/native regression fixtures, independent framebuffer checks,
  pipeline integration and evidence.
- [x] Native worker: `godot/notation/native/view.gd` and a focused display-hand
  regression, preserving source-bound fingering/click geometry and existing
  chord/unison/beam/tie behavior.
- [x] Timing worker: `notation/practice_timeline.py`, descriptor/timing tests;
  coordinate source-context metadata requirements with parent before changing
  shared interfaces.
- [x] Add deliberately corrupted negatives for lost bass head/extra long stem
  and shortened visible preparation; verify first lesson variants and m3–4.
- [x] Run focused source invariants, grading, pixel and timing suites, then fast
  CI only. No full corpus audit. Independently review both fixes and preserve
  user overrides/generated caches. Final integration target: commit/push main
  and inspect/prune worktrees as authorized in the session.

## Acceptance evidence

Real framebuffer captures must prove separate readable registers, authentic
noteheads/stems and full-bar rest on both staves. Independent source/MIDI
comparison must prove unchanged source identities, onsets, pitches, releases,
hands and voices. At 40 BPM the four-beat rest lasts exactly six seconds;
pause/resume, subsequent attack alignment and score revision remain stable.

## Verified result

- Fast CI: **559 passed, 6 skipped**, plus Godot main-script parse success;
  exit 0. This included fresh framebuffer captures and all existing fast
  chord, unison, beam, tie, tuplet and fingering regressions.
- New Peace framebuffer module: 17 tests, including seven deliberate
  corruptions. Independent review replayed all seven and rejected them.
- Exact before/after source comparison: all 18 opening source records equal.
- Cache migration regression first reproduced old v2 output, then passed with
  the scoped engraving-v3 key; a fresh engine reuses the corrected cache.
- The old repeat-dot negative fixture's horizontal authored hint was retuned
  for uniform ink fitting. The unchanged pixel oracle finds 39 repeat-dot
  clearance intersections under the old reservation code, zero main-stroke
  intersections, and no collision under current production code.
- Live Godot MCP project/runtime inspection and full app screenshots succeeded.
  The owned playtest and isolated backend were stopped after verification.
- Evidence and exact MIDI clocks: `docs/evidence/peace-piece-2026-10-26/`.
