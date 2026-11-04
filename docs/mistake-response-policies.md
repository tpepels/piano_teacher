# Mistake-response policies (MIDI practice)

## Source of truth
Each musical mistake is graded against the already-authoritative MIDI score, source
measure grid, active hand, and transport clock. Responses receive immutable
evidence and return a **decision**. PracticeEngine alone mutates tempo, plans,
persistence, score revision, the one MIDI recorder and the visual rewind. No
policy owns a timer, starts a second backend, infers missing notation, or
awards mastery. Partial retries never earn full-passage mastery.

Registered policies live in
`piano_teacher/application/mistake_responses.py`. Call
`resolve_mistake_policy(id)`, `rolling_response(policy, facts...)` or
`whole_response(policy, evidence...)`. An invalid ID raises an error,
rather than silently switching strategies. The selected ID is a validated,
persisted `mistake_response_strategy` preference and appears in Settings
under **When a note is wrong**. Changes apply to new decisions without
restarting the score. None of these settings changes the exercise generator.

| Policy | Rolling threshold | Failed complete take |
| --- | --- | --- |
| Adaptive recovery (default) | Two-measure rewind, -10% tempo, guided on second repeated problem | Ordinary rewind at existing tempo |
| Repeat at current tempo | Two-measure rewind, same BPM, no forced guidance | Ordinary rewind |
| Slower, accurate repetition | Two-measure rewind, -20% tempo, no forced guidance | -10% BPM and retry |
| Isolate difficult measures | Last offending chunk's final measure, -10% tempo, guidance on third repeat | -10% BPM and retry from latest graded bad measure |
| Guided repair | Two-measure rewind, -10% tempo, guided immediately | Rewind; guided intervention on mid-phrase threshold |
| Finish the phrase | No mid-phrase interruption; allow complete assessment | Rewind after the full assessment if failed |

The five-error rolling threshold, on-time/early/late MIDI assessment,
meter-aware boundaries, source identity, min-BPM bound, score loading gates,
and third accepted-full-take mastery are unchanged. Focused partial retries preserve
the original whole-passage verification step. Warm-ups retain their own
rules. Policy names and thresholds are configuration, not proven estimates
of causal teaching effectiveness.

## Evidence review — 2026-11-04

The evidence supports testing purposeful, source-local repair. It does not
establish that any supplied strategy, numerical threshold or adaptive selector
improves durable piano learning. Performance during an assisted, slower or
shorter retry is a different outcome from unsupported retention of the original
passage. The following sources were reviewed as evidence, not authority for
the application's constants.

| Source and design | Finding relevant to this product | Limit on the inference |
| --- | --- | --- |
| [Ericsson, Krampe & Tesch-Römer, 1993](https://doi.org/10.1037/0033-295X.100.3.363), expertise framework and practice histories | Purposeful work on weaknesses, feedback and repeated improvement opportunities motivate a concrete repair goal. | Not a randomized test of this application's retries or beginner piano teaching. |
| [Duke, Simmons & Cash, 2009](https://doi.org/10.1177/0022429408328851), 17 advanced student pianists, observed practice and next-day retention | Practice accuracy and incorrect-trial counts related to retention rankings; repetition/time totals alone did not. | Observational, small sample and one difficult three-measure passage. Does not establish a causal interruption rule. |
| [Allingham & Wöllner, 2022](https://doi.org/10.1177/03057356211073481), survey of 256 adult instrumentalists | Slow practice is widely used for technical and expressive work. | Self-report; no optimal slowdown percentage or evidence that every error needs slowdown. |
| [Hanberry, 2004](https://repository.lsu.edu/gradschool_dissertations/1187/), 39 undergraduate music majors, eight-week strategy instruction | No significant between-group accuracy differences attributable to the taught strategies. | Dissertation; bundled analysis, difficult-measure and slow-metronome interventions do not isolate individual effects. |
| [Winstein, Pohl & Lewthwaite, 1994](https://pubmed.ncbi.nlm.nih.gov/7886280/), controlled nonmusical movement experiment | Frequent physical guidance impaired retention/transfer relative to some comparison conditions. | Physical guidance differs from note prompts; no universal prompt-fading schedule follows. |
| [Fujii, Lulic & Chen, 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4893479/), 20 adults learning arm coordination | Full concurrent auditory feedback outperformed reduced feedback on coordination error at unsupported tests. | Counterexample to a universal reduced-feedback rule; different task and feedback modality from terminal piano assessment. |
| [Caramiaux et al., 2018](https://pmc.ncbi.nlm.nih.gov/articles/PMC5832267/), 48 nonmusicians, randomized tempo-set/order conditions | Smaller tempo sets and nonrandom order benefited movement smoothness at immediate transfer; timing findings differed. | No delayed retention; eight-note right-hand task. Does not justify universal random tempo variation. |
| [Cash, 2009](https://doi.org/10.1177/0022429409343470), 36 nonmusicians, digital-piano sequence and overnight test | Rest placement affected within- and between-session learning rates. | Does not prescribe a universal break duration or multi-day spacing rule for repertoire. |
| [Wiseheart, D’Souza & Chae, 2017](https://doi.org/10.1371/journal.pone.0182986), 100 novice university learners, 0–15 minute practice lags | No reliable spacing advantage in the reported piano tasks. | Short laboratory tasks and tested lag/retention ranges; verbal-memory spacing results cannot simply be imported. |
| [Moringen et al., 2024](https://arxiv.org/abs/2406.04812), workshop manuscript, six novice pianists/one teacher, 121 pre/practice/post tuples | MIDI contexts could support models approximating teacher practice choices. | Predicting a teacher's choice does not establish that autonomous choices improve retention; controlled comparisons were deferred. |

Two syntheses qualify the primary evidence: [McKay et al., 2022](https://doi.org/10.1016/j.psychsport.2022.102165)
found no significant reduced-feedback advantage across 75 comparisons and
substantial uncertainty; [Zhang & Liu, 2026](https://pubmed.ncbi.nlm.nih.gov/42947794/)
describe heterogeneous instrumental feedback studies with limited delayed
retention/transfer. Neither ranks these six policies.

No strong direct comparison was identified between this product's bar-boundary
interruption and finishing the same phrase at equal practice dose with later
unsupported retention. Immediate versus terminal corrective feedback is an
experimental design choice. Studies of delayed instrument sound do not directly
answer when to display an assessment message.

## Proposed adaptive retry specification

**Status: reviewable proposal, not implemented or pedagogically validated.**
The six IDs above remain fixed experimental baselines. The misleadingly broad
existing ID `adaptive` retains its documented fixed parameters. A new selector
must have a separate stable ID and policy version; changing its algorithm must
not silently change a baseline. Only [ROADMAP](../ROADMAP.md) defines phases.

Three approaches were considered:

1. Keep fixed strategies and add evidence/outcome measurement. Lowest behavior
   risk; necessary to establish comparisons, but no automatic selection.
2. Add a deterministic, explainable selector over measured error patterns.
   **Recommended first adaptive implementation.** Each action has an explicit
   reason and fallback, and can be replayed exactly through the registry.
3. Learn action selection online with a contextual bandit. Potential later
   experiment; current logs lack randomized action support and delayed outcomes.

The recommendation and all numerical settings below are engineering proposals,
not user-approved implementation phases or findings of optimal pedagogy.

### Observable error evidence

An immutable assessment snapshot must contain these fields before selection:

| Group | Required facts and units | Missingness/interpretation |
| --- | --- | --- |
| Identity | Schema/grader/policy versions; source SHA-256; generator/version, stage, hand, attempt, transport and score revision; calibration version | Changed source, hand, stage or assessment version cannot inherit comparable-attempt history without an explicit mapping. |
| Target and scope | Authentic source measure grid; full/partial interval; target and performed BPM; timing-map identity; expected source attack IDs | Full target, partial loop and guided acquisition are separate exposure types. |
| Pitch | Required pitch, observed matched pitch, wrong/omitted/extra flags, association confidence | A wrong pitch replaces a miss; do not count it twice. Extras remain separate. Ambiguous unison matching stays ambiguous. |
| Timing and rhythm | Signed onset residual in seconds and local beats, inter-onset interval residual, expected local seconds/beat, tolerance and chord attack group | A uniform offset may be calibration; interval distortion is a rhythm descriptor. Neither proves a cognitive cause. |
| Duration | Expected/observed key-down duration and release residual; unreleased/truncated flags | Key release is not audible acoustic duration; pedal and final held keys need explicit unknown/censored treatment. |
| Hand and density | Expected source hand, simultaneous required pitches, distinct attacks/beat, notes/beat | MIDI pitch does not identify the learner's physical hand or fingering. A chord has one onset opportunity and several pitch obligations. |
| Location/pattern | Source measure and beat; per-measure pitch/timing/hold counts; repeated source IDs or interval/rhythm signatures across comparable exposures | Repeated patterns describe observations, not diagnoses of attention, fatigue, emotion or misconception. |
| Reliability/history | Device continuity, calibration, complete capture, assistance, comparable prior actions/outcomes, learner override and missing fields | A disconnected/truncated take is not evidence for more aggressive teaching intervention. |

Today `NoteAssessment` exposes one priority status and a wrong-pitch value,
not independent onset/hold residuals or the complete event assignment. The
future evidence adapter must obtain those dimensions from the authoritative
grader's actual match; it must not manufacture timing/duration detail from a
`wrong` or `late` label. Frozen containers must also freeze nested values.

### Feedback timing and action eligibility

Operational failures—device loss, invalid score, stale identity, missing
notation—require immediate safe suspension by existing runtime owners. They
are not teaching errors and do not enter adaptive escalation.

For musical mistakes, keep existing provisional live feedback. Isolated pitch,
timing or hold errors receive an end-of-phrase summary by default in the proposed
selector. Repeated, concentrated wrong/omitted notes can justify repair at the
next authentic metrical boundary in accuracy practice. A sustained breakdown
can also qualify, provided capture is reliable. An attack in progress is never
cut short solely to deliver feedback. Uninterrupted Perform and the fixed
finish-then-review strategy retain their contracts. Rhythm-only and duration-only
patterns initially receive terminal feedback; immediate intervention has no
established superiority here.

This context-dependent timing is **not expressible by the current interface**:
`interrupt_rolling` is static, `RecoveryDecision` supplies aggregate wrong/missed
counts, and the handler must return a repair. Before enabling dynamic timing,
extend the same registry with a generic validated continue/repair decision and
source-bound detailed evidence. Do not add policy-ID branches in `server.py`.
Continue means no mutation of tempo, recorder, mastery or source revision.

### Observe → classify → intervene → reassess

The proposed state machine is source/stage/hand scoped and deterministic:

| State | Entry/action | Reassessment/exit |
| --- | --- | --- |
| Observe | Capture a reliable completed take or settled rolling boundary. Classify concentrated/scattered pitch, omission, timing and hold patterns with confidence/missingness. | No adequate evidence: use documented steady-repeat fallback. A learner override ends the episode. |
| Repeat | First comparable failed exposure: repeat at current tempo, give one concrete goal. | A clean full take follows normal progression. Repeated failure selects focused repair or slowdown using the rules below. |
| Targeted loop | A repeated source measure contains at least 60% of bad pitch obligations and at least three wrong/omitted notes across the last two comparable takes: retry that measure with source-safe entry/exit. | Two clean focused attempts move to reintegration. Two further failed focused attempts permit slowdown. |
| Slowdown | For persistent failure after repeat/loop, reduce current BPM by 10%, bounded by the existing minimum. Record both performed and next BPM. | Two failures at the slower setting permit guided acquisition. Clean focused work moves to reintegration; full slower work follows the existing target-tempo ladder. |
| Guided notes | Existing GuidedSession acquires the exact source-bound unit without timed mastery credit. No inferred fingering or new notes. | Guided completion returns to an unsupported timed focused attempt, then reintegration. Guidance success alone is not evidence of mastery. |
| Reintegration | Restore the repaired material's surrounding authentic measures, then the complete pre-repair active stage target. Respect sustained notes and changing meter. | Full-target success resumes the existing tempo/streak rules. Recurrent same-location failure reopens repair with bounded escalation. |
| Full verification | Play the complete active target at the selected target tempo under existing assessment and three-accepted-full-take rules. | Only this normal path may award mastery or promote stages. Partial work never advances a full-target streak. |

The 60%, three-note, two-exposure, two-pass and 10% values are initial
calibration parameters. They must be versioned and tested, not advertised as
scientifically optimal. A small/sparse target cannot meet a three-note rule;
it uses comparable whole-target repeat/slowdown rather than invented evidence.
Scattered errors choose a full-target repetition before a smaller loop. A
wrong pitch alone is insufficient to infer a tempo problem. Timing/hold errors
use explicit terminal goals and only persistently failed comparable takes
qualify for bounded slowdown.

Cap automatic corrective actions at six per source episode; then offer a
learner-controlled repeat, Listen, break or end. Preserve progress and explain
the choice without claiming fatigue. This proposed frustration safeguard also
requires physical usability evaluation. Do not silently skip, award mastery,
or switch the exercise generator to escape the cap.

The pure handler receives the immutable history; the engine applies a
validated decision and transactionally records an action/outcome event through
the existing SQLite owner. Include decision ID, eligible actions, chosen action,
reason code, parameters, assistance and scope. Outcome events bind to the next
comparable attempt and distinguish observed, canceled and censored results.
Policy switches preserve the current take and start a new policy episode.
Stale worker replies cannot contribute evidence. No additional service or
second clock is required.

### Online learning readiness

Deterministic logs cannot estimate outcomes for actions never chosen. Future
randomized logging needs eligible action sets, known nonzero selection
probabilities, RNG state, policy version, and observed/censored outcome windows.
[Li et al.'s replay method](https://arxiv.org/abs/1003.5956) relies on appropriate
logging assumptions; [Dudík et al.](https://proceedings.mlr.press/r10/dudik12a.html)
describe importance-weighted/doubly robust evaluation. These methods do not
create missing counterfactual learner behavior.

Before a local interpretable contextual bandit is considered, require action
coverage within each eligible context, acceptable effective sample size and
confidence intervals, held-out learners, a prespecified reward and successful
randomized feasibility data. There is no defensible universal minimum sample
count today; use observed variance/coverage for power and precision planning.
Slowing or shortening practice must not inflate reward: the provisional proximal
outcome is the next comparable unsupported full-target performance. Retention
remains a delayed outcome. Actions change later learner state, so simple
independent bandit rewards are an approximation requiring explicit evaluation.

## Evaluation protocol

### Reproducible offline MIDI replay

Freeze original MIDI bytes/hash, importer/grader/policy versions, settings,
calibration, exact note-on/off traces with monotonic offsets, authentic measure
grid, source/stage/hand identity and action history. Save input/output JSON and
environment versions. Use an injected virtual monotonic clock and the production
MIDI callback/assessment/registered decision path; retain separate pure-handler
fixtures for decision tests. Use a temporary database and fresh caches.

Run each trace against all six unchanged baselines and the candidate. Cover
chords, repeated pitches, sparse/dense passages, leading/full-measure rests,
mixed meter, either/both hands, clustered/scattered errors, constant latency,
rhythmic distortion, short/long/missing releases, extras, partial retries,
minimum BPM, stale history, navigation, source changes, disconnects and live
policy switches. Include negative controls for stale score acknowledgement,
duplicate completion, failed persistence and failed engraving.

Assert source identities, authentic boundaries, one recorder/transport, exact
performed BPM, bounded actions/retries, clean-pass eligibility and atomic
history/progress. Report deterministic decision differences, interruption and
guidance counts, BPM trajectory, loop coverage, invalid-decision rate, runtime
and memory. Fixed traces test engineering behavior; they cannot predict what a
person would play after an alternative intervention. Synthetic learner models
must be labeled simulations and cannot establish teaching effectiveness.

### Small controlled physical comparison

Start with a preregistered feasibility crossover, proposed 12–20 consenting
adult learners with counterbalanced matched unfamiliar passages, followed by a
power-planned study. Compare the candidate with the current default and
finish-then-review; preserve the other fixed strategies for subsequent targeted
comparisons. Stratify experience and document passage difficulty, keyboard,
latency calibration, practice dose, starting/assessment tempo and supports.
Use different passages per condition and model period/order effects; learning
does not wash out simply because a short break passes.

Primary endpoint: pitch errors per required source pitch on an unsupported
full original target at a common prespecified tempo after 24 hours. Assessors
should be blind to condition and independently check captured performances.
Keep ordinary instrument sound available. Add one-week retention and untrained
related-passage/tempo transfer when feasible. Report uncertainty and missing
follow-ups; a pilot estimates feasibility/variance, not superiority.

| Outcome | Operational definition |
| --- | --- |
| Error reduction | Change in pitch/omission/extra rate, signed onset dispersion and hold error separately, on matched full targets at common tempo. |
| Clean-pass rate | Clean unsupported full targets divided by eligible full attempts; report partial/assisted denominators separately. |
| Time to mastery | Active practice seconds to existing full-target criterion; unfinished sessions are censored, not dropped. |
| Retention/transfer | Common-tempo unsupported tests after 24 hours and, if feasible, seven days; related untrained material separately. |
| Interruption burden | Automatic interruptions per minute and per full target, correction time and abandoned/restarted takes. |
| Frustration | Brief prespecified learner rating after each condition, overrides, voluntary stops and preference; never infer it from MIDI alone. |

Report both intention-to-treat assignment and descriptive actual exposure,
dropouts, technical failures, assistance use and practice-time differences.
USB/Bluetooth timing, GPU cadence and usability require the
[physical acceptance checklist](verification/coda-fukuda-physical-midi-checklist.md).

## Acceptance and extension contract
A new response must have a stable ID and explanation, valid tempo/focus
bounds, a pure no-side-effects policy, full- and rolling-evidence behavior,
source-bound tests, a Settings option, and a safe fallback for inadequate
evidence. The engine must not grow a policy-name-specific chain.

The public extension is `register_mistake_policy(MistakePolicy(...))` called
once before loading settings. A registration can declare `rolling_handler`
and `whole_handler` pure functions; they receive frozen `RollingEvidence`
and `WholeEvidence` objects and return `RollingResponse` /
`WholeResponse` decisions. The public evaluator checks identity, authentic
metrical boundaries, tempo bounds and source duration even for third-party
strategies. An invalid decision raises rather than corrupting a transport or
silently changing the score. The six supplied strategies use the same default
evaluator with independent parameters; custom algorithms can replace either
evaluator without touching `PracticeEngine`.
Policy changes during active playing must preserve the current recorder,
transport ID, existing score revision and source-derived evidence.
