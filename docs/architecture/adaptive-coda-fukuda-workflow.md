# Complete adaptive Coda + Fukuda MIDI teaching workflow

**Source:** `piano_teacher/adaptive_hybrid_curriculum.py` and the registered
`CodaFukudaMidiLessonGenerator`. **Input:** imported MIDI only. **Selection:**
Settings → Coda + Fukuda · MIDI combined lessons. The Coda-only strategy
remains the default until human comparison supports a change.

## End-to-end ownership

| Phase | Owner | Invariant |
| --- | --- | --- |
| MIDI import | `music.load_midi` | Stable PPQ and source attack IDs |
| Passage construction | `_segments`, `_course_exercises` | Every source attack covered once by learn passages, full original finale |
| Candidate compilation | `compile_hybrid_catalog` | Every applicable Coda/Fukuda source variant compiled once; no clipped note durations |
| Lesson selection | `select_hybrid_stages` | Adapt by graded original-attack status, always end at original |
| Practice and transport | Existing `PracticeEngine`, `VisualTransport` | Exactly one clock for notation/Listen/grading |
| Assessment | Existing `AssessmentService` | Only authentic completed original-note takes update source-error evidence |
| Durable feedback | `FukudaMistakeStore.evidence` | Per-piece source ID → latest graded status, with corrections removing errors |
| Replanning | `LearningPlan.refresh_from_feedback` | Stable unchanged stage keys, mastery, BPM, streak and cursor |
| Persisted resume | `ProgressRepository` | Strategy- and version-specific course keys |
| Finale | Existing `LearningPlan.apply_result` | Three clean original-score target-tempo passes for mastery |

## Error-specific teaching policy

The teaching policy selects exercises according to the existing grader's
status evidence, without independently grading recorded notes.

- **Wrong or missed source pitch:** apply eligible Fukuda chord outer-note,
  fast-run thinning and/or octave-leap reduction; use Coda's slow stage
  for deliberate retry.
- **Early or late attacks:** use both Coda dotted-rhythm families where
  applicable, then a slower stage and original notes.
- **Short or long note releases:** choose Coda slowdown stages, including
  further slowdown when available.
- **No diagnosed error yet:** offer at most a few preparatory stages,
  never force the learner through every generated author variant.
- **Unrepresentable operation:** remain on exact original source notes.
  Generated exercise availability is conditional on actual MIDI content.
- **All outcomes:** stage identity and final original notes remain
  separate, and no Coda exercise changes the authoritative transport.

The selected stages remain manually navigable; the current lesson can
also advance automatically through existing mastery transitions.
The full author Coda research catalog remains accessible through
`coda-midi`, whose whole-piece semantics were deliberately preserved.

## Verification

Bounded CI: [complete combined lesson verification](https://github.com/tpepels/piano_teacher/actions/workflows/composed-midi-lessons.yml)
runs the adaptive journey, the established Coda/Fukuda integration
contracts and all 17 real full MIDI pieces. Source-identity coverage,
repertoire, timing stages, error-specific selection, score rendering,
Listen/grading and durable feedback are asserted separately.

Native Godot 4.7.2 Settings/lesson smoke checks:
[Godot startup workflow](https://github.com/tpepels/piano_teacher/actions/workflows/godot-startup-check.yml).

## Acceptance limits

Software tests and headless GUI checks cannot certify real physical
USB/Bluetooth keyboard latency, count-in and retry ergonomics, or visible
score handoffs under genuine played MIDI. Those must be performed locally
with a keyboard. Exact source-figure reproduction of the original
Fukuda acoustic system is also unproven; this application intentionally
implements the MIDI-domain score-reduction adaptation.

Pedagogical superiority of adaptive Coda+Fukuda over other lesson plans
requires controlled learner evaluation. No synthetic tests count as
evidence of improved teaching outcomes.

## Physical acceptance script

Use the [real MIDI keyboard checklist](../verification/coda-fukuda-physical-midi-checklist.md)
to record a complete on-device run, including repeated mistakes, clean
corrections, stage/BPM restoration, grading and full-score mastery.
Software CI alone cannot provide this evidence.


## Progressive consolidation and accepted-result handoff (2026-11-02)

In addition to individual short source passages and neighboring boundary
bridges, the curriculum inserts progressively larger **original MIDI**
connectors after complete adjacent groups of two, four, and eight focus
passages when those connectors are safe at measure boundaries. Every
connector uses original note attacks and releases, and its stages never
substitute synthetic notes or duplicate the full original performance.
These connectors are traversed by the existing lesson mastery policy.
The full-score performance remains the unique finale.

Adaptive feedback now distinguishes the **failed attacks from the current
take** from older mistakes retained elsewhere in the piece. Earlier
stored evidence can still select future scaffolds, but cannot redirect a
new assessment to the wrong passage. A passing take containing a small
number of advisory amber timings retains normal course advancement.
Changing the future adaptive catalog without changing the currently
rendered stage no longer invalidates the active score revision, avoiding
an unnecessary engraving handoff.

### Local, bounded verification

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
bash scripts/verify-hybrid-workflow.sh --focused
# Optional full 17-score corpus without waiting for GitHub Actions:
bash scripts/verify-hybrid-workflow.sh --corpus
```

The local suite verifies software contracts. The existing physical MIDI
checklist remains required for actual keyboard timing, GUI transitions
and count-in/retry experience.


## Source-local Fukuda assignment

The hybrid selector compares each prospective Fukuda reduction against the
original MIDI attack IDs that are **actually removed**. For failed pitch
notes, it prefers reductions that remove that exact attack, then reductions
affecting the surrounding two-beat context. A chord reduction elsewhere in
the same phrase is not presented as a remedy for an unrelated failed pitch.
When no eligible local simplification exists, it falls back to Coda
slowdown and the unchanged original score. The original candidate catalog
is retained, including otherwise unused research variants.
