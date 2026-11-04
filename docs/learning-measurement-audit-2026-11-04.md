# Learning variables, performance telemetry, and retry analytics — implementation audit
Date: 2026-11-04
Baseline: `b8a2aa8f7e28aef8ca27b6b857bc4ca8ece89092` (`main`)
Scope: MIDI-only learning, retries, grading, persistence, analytics, and runtime evidence. UI art direction is excluded. Read-only source audit; this document changes no application code.

## Verdict
Learning rules and immediate assessment are substantially implemented. Durable attempt-level, note-level, retry-decision, timing, and longitudinal evidence are not. Six selectable retry policies are predefined; no evidence-driven automatic choice of policy, no intervention outcome attribution, and no validated adaptive learner model. A recent assessment history exists but is **bounded to 64 graded attempts per exact stage** and records only BPM, note-status sequence, and extra-note count.

**Vocabulary:** Rule = fixed or configurable policy; Derived = computed from source MIDI or live grading; Live = exposed through current state/diagnostics; Persisted = retained in SQLite/settings across restarts; Absent = not implemented as a durable first-class metric. An exposed number is not necessarily a historical measurement.

## 1. Curriculum, score and source-complexity variables

| Variable | Computed / configured | Persisted | Exposed | Notes |
| --- | --- | --- | --- | --- |
| Default focus length / expansion increment | Rule: 2 measures | No separate observation | No numeric setting in main UI | `focus_measures` |
| Minimum unique rhythmic onsets | Rule: 2 | No | No | `focus_min_onsets` |
| Maximum focus length | Rule: 8 measures | No | No | `focus_max_measures` |
| Preferred maximum distinct attacks | Rule: 8 | No | No | `focus_max_attacks`; original score may exceed |
| Repeated-material transfer minimum attacks | Rule: 2 | Transfer eligibility, not count | Not directly | `repeated_tempo_min_attacks` |
| Original source pitches, note count, beats, bars and authored meter | Derived | Embedded in source; stage identity/metadata | Count/bars/score via live APIs | Retain source MIDI and content fingerprint |
| Distinct attacks (onset times), attacks per beat and shortest onset gap | Derived | No dedicated metrics | No analytics endpoint | Chord notes and unique attack times differ |
| Maximum chord size and simultaneous pitch span | Derived in optional difficulty feature estimator | No | No standard diagnostics | `difficulty.py` |
| Maximum melodic leap / rapid intervals / irregular offbeat attacks | Derived in optional estimator | No | No | Also used in source planner |
| Sustained voice overlaps / temporal density | Derived in optional estimator | No | No | Does not measure performed difficulty |
| Difficulty category and reasoning | Optional `HeuristicDifficulty`; feature-gated route | No longitudinal history | Not exposed as learner skill | `baseline` / `challenging` are heuristic |
| Personal skill/difficulty prediction, error risk by feature | Absent | No | No | RubricNet research/optional strategies do not create a continuously updated learner skill model |
| Exercise strategy, stage, hand, source boundaries, simplification level | Derived/configured | Stable stage identity and strategy sessions | UI/API | Default selected generator: `coda-fukuda-midi` |
| Full lesson-step count, completed count, navigation position | Derived | Position/mastery | UI/API | Explicit skip/placement is distinct from mastery |
| Count and proportion of removed/retimed/pitch-changed source notes | Derived by stage difference metadata | Not historical learner metrics | Partial stage description | See `lesson_stage_semantics.py` |

## 2. Tempo, repetitions and mastery variables

| Variable | Computed / configured | Persisted | Exposed | Notes |
| --- | --- | --- | --- | --- |
| Baseline start tempo | Rule: 40 BPM | Only resulting per-stage tempo | UI/API | Fast sustained attack patterns may reduce start BPM |
| Minimum/maximum BPM | Rule: 12/300 | No per-attempt rule version | UI/API |
| Original BPM, selected target BPM | Source / selection | Yes | UI/API |
| Current practice BPM, independently for each stage | Mutable learning state | Yes | UI/API |
| Automatic ladder | Rule: 12 subdivisions | Only current earned rung as BPM | UI/API | Integer rounding can merge rungs |
| Manual increment/decrement | Rule: 5 BPM | Resulting BPM only | UI/API |
| Minimum automatic increment | Rule: 1 BPM | No | No |
| Tempo under optional shaped tempo-map policies | Derived per stage | Stage selection and BPM, not complete historical map | Current tempo segments API | Requires authoritative mapped clock |
| Automatic BPM increase after accepted full take | Yes | Resulting tempo | Current BPM/streak | Accepted is broader than strictly clean |
| Rolling/whole retry slowdown | Six registered policies | Resulting BPM only | Transient notices | Selected policy ID saved separately |
| Exact repeats per stage, repeats per tempo, total attempt counts | No full counter | Bounded history can approximate only graded full takes | `exercise.diagnostics` reports recent bounded window | Does not include partial/interrupted/ungraded attempts |
| Number/cause of manual BPM changes or auto slowdowns | Absent | No | No |
| Consecutive accepted full target-BPM results | Mutable streak | Yes for current stage/strategy | UI/API | Reset on navigation/manual tempo changes |
| Mastery passes requirement | Rule: 3 | Mastery record on completion | UI/API | Note: `result.passed` admits certain amber timing warnings |
| True clean full target-tempo pass count | `Assessment.clean` available | Not as explicit event/counter | Current assessment; limited history | Distinguish strict clean vs passed |
| Time on each rung; attempts to first mastery | Absent | No | No |
| Identical-source passage BPM transfer | Derived | Yes, transfer credit and stage tempo | Indirect | No mastery or streak transfer |

**High-severity semantic discrepancy:** `practice.py:Assessment.passed` accepts performances with non-red timing warnings when fewer than half the distinct attacks are amber. `application/assessment_commit.py` passes `result.passed` to `LearningPlan.apply_result` as `accepted`; `apply_result` may count these toward the three-pass mastery streak. Requirement wording repeatedly says "three clean passes". Define explicitly whether mastery requires `clean` or `passed`; do not change behavior without the product decision.

## 3. Note-level performance and grading

| Variable | Measured | Persisted | Exposed | Notes |
| --- | --- | --- | --- | --- |
| Per-note correct/missed/wrong/early/late/short/long | Yes | Ordered statuses only, for bounded complete takes | Review and note feedback | Exact per-note source identity is absent from `practice_evidence` |
| Wrong played pitch and source expected pitch | Yes | Fukuda's latest source error family and trouble pitches; not full timeline | Detailed active review | Per-source errors accumulate until resolved |
| Extra played notes | Yes | Aggregate extra count per graded take | Review |
| Exact onset deviation, duration deviation (milliseconds) | Computed for grading | Discarded | Only categorical statuses | Not available for distributions or improvement curves |
| Strict clean, passed/failed, percentage correct | Derived | Inferable from status sequence; not explicit durable outcomes | Current/review |
| Distinct attack count and amber attack count | Derived in `Assessment` | Not first-class | Not historical |
| Per-hand/measure/chord note error distribution | Calculable from a graded score | Persisted only partial trouble units/statuses | Current detailed review | No repeated longitudinal per-hand / per-note analytics |
| Fine-grained musical timing variance / systematic rushing / duration bias | Absent as metrics | No | No |
| Velocity/dynamics control, pedal timing/accuracy | Not graded as a complete practice metric | No | No |
| Performance MIDI event trace | Live recorder | No durable full recording | Live indicator/feedback | Must distinguish preview/assessed performances |

Grading uses `grading_tolerance.py` with 0.13s minimum onset slack, up to 0.30s at slow tempo, and duration fraction currently 0.5 (tempo-scaled further). The human-readable `docs/lesson-tempo-policy.md` still cites older 0.10s and 0.20 values; update the documentation in a future approved phase.

## 4. Recovery, intervention and guided learning

| Variable | Defined / measured | Persisted | Exposed | Notes |
| --- | --- | --- | --- | --- |
| Rolling wrong/missed error threshold | Rule: 5 across ~2 measures | No rule version | No |
| Warmup recovery threshold | Rule: 2 | No | No |
| Source-grid retry start/end; metrical windows | Yes | Some selected trouble units | Live retry range | Changing meter uses canonical bar grid |
| Selected retry policy (six) | Configurable | Current setting | Settings |
| Recovery tempo factor and guided escalation | Per-policy parameters | No intervention history | Settings description / transient feedback | Defaults: adaptive -10% rolling and guided after repeated matching unit |
| Repeated trouble count for current section | Transient | Learner unit failure counts persist separately | Partial trouble spots | Transient counter resets on navigation |
| Automatic vs manual retry and interrupted vs completed attempt | Control flow | No durable event | Live state |
| Graded error classes used in retry selection | Pitch/wrong/missed threshold; selected whole-pass micro-loop positions | Only partial summaries | Notices / review | Diagnosis (pitch/rhythm/duration) is separate and mainly advisory |
| Intervention policy, eligibility, reason, trigger and before/after BPM | Calculated in policy calls | No | Transient notice | Impossible to attribute outcome without event IDs |
| Action sequence repeat/slow/guided/whole reintegration | Fixed strategies and some guided return paths | Partial guided progress | UI/API | No general evidence-driven escalation controller |
| Outcome after each retry or guidance | Assessment exists | No linked pre/post outcome | Not summarized | Cannot estimate intervention effect |
| Guided targets and prepared unit counts | Yes | Per-unit completion and assisted bit | API/UI |
| Hints, wrong guidance keys, stalls, assisted target count | Yes live | Only per-unit assisted bit; no timeline/count | Live teaching snapshot |
| Guided chord window | Rule: 0.25s | No | No |
| Guided stall threshold | Rule: 3s | No | No |
| Persistent trouble pitches/count/resolved | Yes | Yes per exact stage+unit | Lesson overview | Does not represent every attempt or timing family |
| Fukuda source-note error counts/status | Yes on graded original takes | Yes until resolved | Indirect generator inputs |
| Effective retry strategy by learner/task | Absent | No | No |

`practice_history.py` persists `practice_evidence(fingerprint,stage_key,bpm,statuses,extra_notes)`, trims to the latest 64 entries per stage, and returns 8 recent for diagnostic recommendations by default. No timestamp, attempt ID, intervention ID, device condition, grading-rule version, note source IDs, or actual MIDI timing trace. `diagnosis_policies.py` has error-family and repeated-error recommendation policies, but its recommendation service does not automatically select one of the six mistake-response policies.

## 5. Longitudinal learning, session and runtime telemetry

| Variable | Status | Persistence / presentation |
| --- | --- | --- |
| Saved stage position, BPM, streak and mastery | Implemented | SQLite; UI/API |
| Guided-unit completion/resume, skip/placement reason, trouble regions | Implemented | SQLite; lesson overview |
| Session ID, started/ended timestamps, practice minutes, number of sessions | Missing as durable analytics |
| Total lifetime attempts and all retries; cancellation/interruption counts | Missing |
| Progress per day/week, practice frequency, return latency | Missing |
| Retention/retest performance after days/weeks; relearning speed | Missing |
| Difficulty-adjusted learning velocity, time to mastery | Missing |
| Explicit device and calibration associated with each attempt | Missing |
| MIDI calibration offset | Saved setting; measurement details transient |
| Calibration jitter/tap rounds | Calculated in calibration UI; not historical |
| Runtime MIDI callback, tick, snapshot processing latency | Opt-in bounded in-memory p50/p95/max; not persisted |
| Godot process-frame FPS/inter-frame percentiles | Opt-in; not a durable per-attempt metric |
| Physical key-to-light latency, physical audio/display latency | Not fully measured or accepted |
| Recorded trial/intervention efficacy, matched learner comparisons | Missing |

## 6. Missing canonical contracts / recommended priorities

**P0 — semantics and provenance:** Decide `passed` vs `clean` for mastery and disclose amber eligibility. Define stable `LearningRuleSnapshot` (rules, grader version, generator identity, score fingerprint), `PracticeSession`, `Attempt`, `NoteObservation`, `AssessmentResult`, `InterventionDecision`, `Outcome`. IDs and monotonic+wall timestamps must link score source IDs, active hand/variant, actual BPM/timing map, graded/ungraded state, and decision inputs.

**P0 — durable evidence:** Persist full attempt outcomes and per-note expected/observed onset + release deviations in **append-only** bounded-aware storage with explicit retention policy, including partial and aborted attempts where relevant. Preserve correctness, category, source MIDI identities, explanation, and assessment confidence. Guarantee exactly-once commit under retry/score revision changes. No preview/guided evidence may award timed mastery.

**P1 — derived analytics:** From immutable events calculate trials per stage/BPM, accuracy/precision/consistency, source difficulty vs error frequency, retry frequency, minutes to mastery, timing drift, dwell and transition durations, guided assistance, and clean vs accepted passes. Add versioned read-only analytics ports; prefer per-session aggregation and appropriate SQLite indexes over per-frame queries.

**P1 — policy outcome linkage:** Capture which of six policies was selected, trigger window/evidence, response and subsequent comparison at the same source range and compatible tempo. Track escalation/reintegration and prevent false credit from partial retries. Test what really improves rather than infer success from one clean pass at a slower BPM.

**P2 — difficulty calibration:** Relate optional `DifficultyFeatures` and authored stage metadata to observed learner success; distinguish score complexity from individual ability and tempo-specific difficulty; quantify uncertainty, no unvalidated score as pedagogical fact.

**P2 — evaluation protocol:** Run deterministic MIDI replay across all six fixed policies using paired note-trace fixtures (also changing meter, missing MIDI, repeated notes/chords, dense/sparse, tempo maps, rewinds). Prespecify intervention outcomes; only introduce adaptive strategy selection if evidence supports it. Add retention study and hardware latency validation separately.

**Verification:** Fast contract gate on baseline `b8a2aa8`: 549 passed, 6 skipped. Godot syntax/Practice UI gating previously passed. Embedded runtime smoke run `41817442615` failed at intermediate `ff186e7` because it still called deleted marker helper; it did not run current baseline and must not be reported as its failure. Repeat current-head native/in-process, corpus, physical MIDI and release gates before sign-off.

## 7. Source ownership and implementation pointers
- Source/learning configuration: `piano_teacher/lesson_settings.json`, `lesson_settings.py`, `learning.py`, `tempo_difficulty.py`, `lesson_source_planner.py`, `difficulty.py`.
- Grading: `practice.py`, `grading_tolerance.py`, `assessment_service.py`, `application/practice_assessment.py`, `application/assessment_evidence.py`, `application/assessment_commit.py`.
- Retrying: `recovery.py`, `application/mistake_responses.py`, `application/rolling_recovery.py`, `application/attempt_progression.py`, `remediation.py`.
- Longitudinal evidence: `practice_history.py`, `learner_state.py`, `fukuda_mistake_store.py`, `progress_repository.py`, `application/learner_progress.py`.
- State boundary: `application/session_snapshot_builder.py`, `application/lesson_snapshot.py`, `state_projection.py`, `inprocess.py`, `server.py`.
- Diagnostics: `runtime_timings.py`, `midi_calibration.py`, `godot/frame_meter.gd`.
- Existing design and tests: `docs/mistake-response-policies.md`, `docs/teaching-methodology.md`, `docs/lesson-tempo-policy.md`, `tests/test_mistake_responses.py`, `tests/test_learner_progress_service.py`, `tests/test_assessment_commit.py`, `tests/test_progress_repository.py`.

Nothing in this document constitutes a code change or physical MIDI test. Treat future findings from newer Codex commits as authoritative when supported by their actual source and validation evidence.
