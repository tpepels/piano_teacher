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
