# Automatic lesson-generation reproduction — resume point (2026-10-30)

**Primary project:** faithful research reproduction of automatic piano
practice-exercise generation and adaptive teaching. The user explicitly
redirected work here after a native notation verification detour.

## Scope from the original handoff

The seven acceptance gates are (1) full-paper/source/licence traceability,
(2) trained RubricNet parity, (3) **complete Coda**, (4) Fukuda audio/CQT +
supervised NMF + DTW + mistake detection + three score simplifications,
(5) Piano Tutor score-following/diagnosis/student-model/instruction,
(6) physical MIDI/audio end-to-end verification, and (7) controlled
pedagogical pre/post/retention evidence. The research inventory also
includes Suzuki and Moringen. Heuristic adaptations **do not** count as
reference-equivalent reproductions.

RubricNet's official five-fold checkpoints, source descriptors, CIPI
reference metrics and trained offline application strategy have been
validated in the preceding Gate 1 work. Current emphasis: **Gate 2, Coda**.

### Coda acceptance (unmet)

Full hierarchical Music Matrix Representation with source-owned notation;
Part Splitting, Tempo Shaping, generalized Chordification and polyphonic
Dotted Rhythms; documented reference-example parity; real-score correctness;
one transformed exercise timeline consumed by notation, Listen, MIDI grading
and feedback; and independent original-score mastery. Coda research
prototypes remain **non-parity** until the actual thesis/reference code and
published examples establish the detailed algorithms. The Dartmouth
download returned 403 when checked on 2026-10-30; the abstract verifies
only the four exercise categories and Score-Part-Voice hierarchy.

### Latest supporting notation work — archived checkpoint

2026-10-30, source revision `701f28447fa827059d724039959799dc6bb636ce`
with evidence committed on main at `5529e302`:

- Source-specific slur suppression and independent ink ownership: **14/14**
  bounded Godot framebuffer tests passing, including missing/drifting control
  rejection; 3-voice collisions and actual *Autumn Leaves* flagged ties.
- Real MIDI excerpts: **1/1** *Peace Piece* eighth rest and placement, **8/8**
  selected Chopin Nocturne noteheads, with negative pixel controls passed.
  The other 69 Chopin noteheads in that excerpt were unsampled.
- Source-revision-bound artifacts: Actions runs
  https://github.com/tpepels/piano_teacher/actions/runs/41137661038
  and https://github.com/tpepels/piano_teacher/actions/runs/41137661023.
  Supporting reports: `docs/native-framebuffer-sample.md`,
  `docs/native-real-score-sample.md` and
  `docs/evidence/native-framebuffer-2026-10-30/current-sample.json`.
- These results do not certify the full notation corpus, real Godot 4.7.2,
  or physical MIDI.

**Do not continue notation audits as the primary workstream.**
Retain this evidence for Gate 6 hardware/corpus acceptance; return to it
only when a Coda-generated exercise exposes a specific rendering mismatch.

### Immediate continuation on research reproduction

Complete **Coda's source-aware MMR**, particularly explicit linked
slur/tie relationships (part/staff/voice, measure, source IDs, partial-window
safety) needed to transform and partition real polyphonic scores without
silently severing musical connections. Then validate and integrate each
of Coda's four separate transformation families against reference examples
when available. Preserve the existing shared transformed timeline and
original-piece mastery contract.

**Engineering constraints:** main only; small verified commits; short fast
CI; no long-running corpus audits, no worktrees, no rebranding experimental
heuristics as exact Coda.

## 2026-10-30 — resumed Coda Gate 2 progress

- `piano_teacher/research/coda_notation_hierarchy.py`: source part,
  measure and voice ownership plus inherited context values from prior
  measures, including exact XML subtrees and original source identifiers.
- `MatrixScore`: complete original MusicXML retained, exact original
  direct-child inventory cross-checked, inherited source context accessible,
  and conservative mid-measure context transformation guards.
- One pinned, non-vacuous 16-note, two-hand MusicXML sample checks all
  four *experimental* Coda families together; transformed chord/dotted
  plans successfully build application source notation-models with original
  note IDs and timing intact. Further real MusicXML samples verify hierarchy.
- These tests are **engineering invariants**, not published-algorithm
  reproduction. Full thesis/reference example access still missing (403);
  no research gate has been newly accepted.
- See `docs/research-reproduction-gate-2-coda.md` for the exact remaining
  requirements. Next: written-notation projection/reconstruction proof
  across transformations, then published-reference matching when source
  can be obtained. Do not return to unrelated notation corpus tasks.

## 2026-10-31 — Coda full thesis and public author backend recovered

The user uploaded the complete Dartmouth 2025 thesis. The author's
public backend source was found at `annieetang/coda_backend` SHA
`a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`; public
frontend is at `annieetang/coda_app` SHA
`c5a00ca53c3204fc66bde4cdaba3157ab760e76a`.
**The previous missing-thesis blocker is resolved.**

The earlier 'Coda' strategies are not all the thesis algorithms:
source *Part Splitting* is Score→Part→Voice isolation, not measure
segmentation; source *Tempo Shaping* is written x2/x4 note-duration
expansion, not a BPM ramp; and dotted/chordification work through
three 128-pitch MMR matrices and equal-duration runs.

Added isolated `coda_reference_matrix.py` and
`coda_reference_exercises.py` with independent, source-preserving
research equivalents of the documented four categories and
fail-closed guards. Existing production remains untouched.
See `docs/research-reproduction-gate-2-coda.md` for the thesis
and source comparison, known upstream limitations and remaining
reference-run parity work. No full notation audit or long CI.

## Reference parity checkpoint — 2026-10-31

Explicit short original-backend differential run `41192215147`
against author SHA `a4eb85df...` PASSED: all 6
128-pitch MMR array comparisons and 10 output exercise
event comparisons on the source-backed two-hand uniform
example. Current repo revision `20b7ba9f`, fast CI
`207 passed, 6 skipped`. See the Gate 2 report for the
exact tested scope and exclusions. Run is explicit-only, so
ordinary CI remains short.

## 2026-10-31 Coda Gate 2 mixed-rhythm reproduction checkpoint

New bounded `probe_coda_upstream_edges.py` executed the actual
pinned author backend on four different input scores:
mixed note durations, a three-note dotted run, simultaneous
source chords and a run with trailing silence. At code SHA
`7026db23`: **4/4 cases**, **12/12 matrix arrays** and
**20/20 exercise output sequences** exact against original
`music21` results. An earlier failed parity run found a
real padded-window bug; source chord duration was corrected.
The final unmatched dotted event now matches upstream when
the altered length stays in the source grid and avoids
authored rest/next-onset overlap. Tests **211 passed, 6
skipped**. See `docs/research-reproduction-gate-2-coda.md`
for caveats. The remaining objective is full notation-preserving
source-to-exercise projection and wider pinned author parity,
not unrelated native rendering.

## 2026-10-31 — practical Coda research exercise pipeline

Source MusicXML → Coda reference-guided `TimingPlan` →
`CodaProjectedStage` → production `ScoreArtifacts` →
real Verovio SVG, production `ListenSession` /
`DemoAudioCache` WAV and `assess_timed` /
`timed_live_marks` now share a **single source-mapped clock** for
a strict notation subset. Dotted-short/long, chordified and x2/x4
written slowdown are verified on a source-backed two-hand XML
score; source rest-only voice/key-change context survives.
Fast CI **218 passed, 6 skipped**, actual SVG/WAV/live test
**6 passed**, code SHA `99c33563`.
Evidence run `41194677252`, artifact `13039764876`.
The production lesson planner remains unchanged: no user-facing
Coda strategy has been enabled; no original mastery is granted
by transformed exercises. See Gate 2 tracker for limitations and
the next annotation-projection work. Do not resume unrelated
notation audit workstreams.
