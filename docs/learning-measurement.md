# Local learning evidence and analytics contract

**Status: approved P0 implementation contract (2026-11-04).** This document
defines the complete P0 measurement phase and subsequent read-only analytics.
Implementation and verification status are tracked in ROADMAP. Only
[ROADMAP](../ROADMAP.md) defines development phases. The
[source audit](learning-measurement-audit-2026-11-04.md) records today's gaps.

P0 uses `application/learning_capture.py` and `learning_ledger.py`;
[verification and remaining gates](verification/learning-measurement-2026-11-04.md)
record actual coverage. P1 analytics below remain a specification.

## Decisions and scope

The user selected **three consecutive accepted full-target Practice takes**
for mastery. Preserve `Assessment.passed` and separately retain
`Assessment.clean`. The rule is named `accepted-full-target-v1`: no wrong,
omitted or extra notes, and warned distinct onset groups strictly fewer than
half the required onset groups. This is an operational product rule, not a
validated measure of durable musical learning.

The implementation is one evidence ledger on the existing
`ProgressRepository` SQLite connection. Merely extending the 64-status cache
cannot recover discarded timing/source assignments or interrupted attempts.
A separate recording service or log-file history would duplicate transaction
and source ownership. Neither is part of this design.

P0 includes all attempt routes, grading detail, intervention/outcome linkage,
rule provenance, migration, retention, local export/deletion and deterministic
failure/restart tests. It does not include automatic strategy switching,
learner-skill prediction, a new UI design or a network service. All six fixed
retry policies remain selectable baselines. Read-only P1 analytics consume the
same ledger; no historical query runs in a frame or MIDI callback.

The user approved these implementation defaults: one local learner; 365 days of
note detail; a 256 MiB logical detail budget; compact summaries retained until
explicit deletion; versioned JSON export with paths/device names redacted.
Detail days and budget are validated local preferences in the existing
Settings screen, with bounds 7–3,650 days and 16–4,096 MiB. Changing
them records a policy event; pruning applies at the next safe transition.

## Entities, identity and units

Use random UUIDs allocated once by the existing application owner. An attempt
ID survives pause, resume, pending settlement and retrying a failed database
commit. A new musical repetition gets a new attempt ID. Transport IDs and
score revisions are provenance, not globally unique attempt identities.

One application/engine run creates one `PracticeSession`. Stop, idle, a piece
change, a mode change or device reconnect does not create another session;
their intervals/events remain distinguishable. Graceful engine shutdown ends
it. Recovery marks the prior open session interrupted with an unknown end
and a separate recovery timestamp. UTC is for calendar grouping, not a
substitute for measured active intervals.

A valid manual retry-policy or calibration change ends the current exposure
with `policy_changed` or `calibration_changed`; Play begins another exposure.
This deliberate change makes one attempt's policy/correction provenance stable.
Invalid preference changes preserve the current take. Other fixed-policy
decisions and the accepted-take mastery predicate retain their behavior.

| Entity | Durable identity and required facts |
| --- | --- |
| Learner | Random local ID and creation UTC. No name, email, account or inferred physical identity; one learner initially. |
| PracticeSession | Session/learner/run IDs, UTC start/end, timezone, closure reason and accumulated active/guided/pause/count-in/preparation/feedback durations. Existing SQL `sessions` remains saved navigation state and is not renamed into practice history. |
| Attempt | Session/parent-decision IDs; source SHA-256, generator/version, exact stage key, hand, variant and source IDs; authentic interval/grid; full/partial/guided/preview/Perform classification; target/performed BPM, complete frozen tempo map and hash; transport/revision; device availability/calibration snapshot; start/terminal state and reason. |
| NoteObservation | Attempt/source-note and onset-group IDs; expected pitch, authored hand, source beat/measure, expected onset/release; matched press identity/pitch/onset/release; signed onset, release and held-duration residuals; local seconds/beat and applied tolerances; priority status plus independent pitch/timing/hold flags; missing/unreleased/truncated/ambiguous flags. |
| Assessment | Unique attempt linkage, grader/schema/rule versions, assessed interval and completeness; note/extra/onset/warning counts; explicit clean/passed and mastery eligibility/reason. |
| RetryDecision | Trigger attempt/assessment/boundary, policy/version/resolved parameters, eligible facts, wrong/missed source IDs/window, reason, selected range, before/after BPM, guidance count, automatic/manual origin, and applied/canceled state. |
| Outcome | Decision and subsequent exposure/assessment IDs, scope/tempo/support comparability, observed/aborted/canceled/censored state; separate focused success, unsupported full-target verification, accepted/clean pass and mastery transition. |
| LearningRuleSnapshot | Content-addressed resolved settings, grading formulas/version, mastery criterion, importer/generator/timing/tempo/retry versions and parameters, exact source/stage/map provenance. Store values and formulas, not just a settings filename. |
| PracticeEvent | Session/attempt-linked pause/resume, manual tempo/navigation, guidance/hint/assistance, interruption and progression events. Stable ID, reason, before/after facts and applicable rule snapshot. No identity or source is inferred later from the current plan. |

One onset group can contain several pitch obligations. Count note-level pitch
accuracy and onset-level timing opportunities separately. Extras have press
IDs and no fabricated expected source-note identity. Source hand does not prove
which physical hand played a key. Raw velocity/pedal accuracy is unavailable
until deliberately captured and graded; absence is explicit.

Store UTC for calendar history and a run ID plus monotonic offsets for elapsed
time. Monotonic epochs cannot be compared across restarts. Preserve scheduled
playable origin, pause intervals and the calibration correction actually applied.
Recorded times must never be rescaled using the BPM selected for the next retry.
Keep source quarter-beat values and authoritative floating-second values;
export integer microsecond residuals as a derived convenience. Reject nonfinite
values. Do not quantize grading time merely to make a table easier to store.

## Authoritative grading evidence

Extend the existing evaluator's actual assignment result in the same matching
pass. Capture matched press indices/times, expected seconds, local tempo and
resolved tolerances before priority status selection. Wrong-pitch reassignment
must retain its actual matched press; repeated pitches and chord obligations
must use exactly the assignment used for grading. Do not rematch later from
statuses or estimate numerical confidence from a category.

Pitch, onset and hold observations can coexist even though the current
presentation selects one priority status. Preserve that presentation behavior
while recording independent observations. Keep unreleased keys, truncated
capture and ambiguous MIDI pairing distinct from measured short duration.
Per-note onset residuals describe latency and timing; inter-onset residuals
describe rhythm. Neither alone diagnoses attention, fatigue or musical intent.

An aborted capture never invents future omissions. Preserve observed presses,
elapsed interval and missingness. Grade a settled completed window only when
its deadline and capture completeness support it. Guided work records target
and assistance events with timed mastery eligibility false.

## Lifecycle and transaction ownership

`PracticeEngine` retains its current lock and transaction boundary. Domain
policies receive frozen explicit facts. SQLite and serialization stay outside
the physical MIDI callback; no additional grading clock or scheduler is added.

An intervention episode is scoped to source, exact stage, hand, policy/rule
version and original target. Each decision gets one proximal outcome: its first
subsequent linked exposure, including an aborted exposure. A later decision
does not erase that outcome. The episode can separately link one first
unsupported full-target verification at the original target tempo. That
verification describes the complete intervention sequence; it does not award
independent causal success to every earlier decision. Navigation, changed
source/stage/hand/policy/rules, session end or learner override closes unresolved
episodes as censored with a reason. Do not attribute a next-session take to an
old decision automatically. Explicit later retention tests are a different
comparison type and carry their actual delay.

| Existing boundary | Complete required capture |
| --- | --- |
| Score readiness → start / `_continue_at` | Allocate and durably record the attempt and immutable context before starting its musical epoch. Record count-in separately. |
| MIDI callback | Continue the one recorder/ring path. Attach the captured attempt identity; never query historical analytics or write SQL here. |
| `_complete_attempt` | Seal the actual played notes before clearing the recorder. Capture full, partial, section review, Perform and preview routes, with their distinct eligibility. |
| Rolling correction | Seal the interrupted exposure/window and fixed-policy decision before preparation replaces its recorder. Commit trouble, BPM/streak/progress and decision together. |
| `_commit_pending` | In the existing savepoint, insert the sealed assessment/observations/outcomes, apply generator feedback and mastery/progress. Restore in-memory state on failure; retain sealed evidence until commit succeeds. |
| Stop/restart/seek/navigation/source or device replacement/calibration/reset/shutdown | End the current exposure with an explicit reason before discarding state. Invalid rejected commands must not create successful action events or terminate a valid take. |
| Guidance | Record source-bound targets, assistance and completion separately; return to timed reintegration without awarding whole-target mastery. |
| Tempo/policy/progression changes | Record intent and applied/canceled outcome with before/after facts. A valid deliberate manual change is not an earned improvement. |
| Startup after interrupted process | Close open sessions/attempts as `process_interrupted`; retain known checkpoint coverage and explicitly unknown suffix/end time. Never manufacture a completed assessment. |

Use unique settlement and terminal-event constraints. Identical repeated
settlement is a no-op; the same ID with a conflicting sealed payload is an
error. Source/revision changes cannot relabel a sealed attempt. An unacknowledged
future score cannot receive assessment or mastery. Retry after a failed commit
must write the same IDs, once, including all outcome links.

Exactly-once settlement is not zero data loss during arbitrary process death.
Persist attempt start and bounded checkpoints at existing musical boundaries;
the unflushed suffix remains missing after a crash. If a required write fails,
pause at the existing safe boundary with an explicit recording/save error,
preserving the pending take and progress. Do not continue awarding unrecorded
mastery. Settings JSON and SQLite are not one atomic filesystem transaction:
record a change intent before applying a file-backed setting, then applied or
reconciled status; recovery must represent uncertainty rather than assert a
change happened from an intent alone.

Replace the active status-only history writer rather than writing two histories.
Current advisory diagnostics read the last eight retained eligible ledger assessments
in transaction order; their recommendation service does not append a duplicate
assessment. Retain no executable compatibility history backend.

## Retention, migration, privacy and export

Detail retention defaults to 365 days with a 256 MiB **logical detail-payload**
budget. The budget is not a promise about SQLite/WAL file size. At safe
transitions prune the oldest complete sessions' detail transactionally and
record pruning coverage; retain compact counts/provenance/outcome summaries.
Never silently delete open or pending evidence. If a pending write cannot fit
after eligible pruning, suspend recording safely and report the limit; no
successful assessment/mastery is invented. A fixed global note-row cap would
retain radically different practice histories for dense and sparse pieces.

Pruning removes the per-note status order as well as match/timing detail;
compact status counts, note/onset counts, clean/passed and provenance remain.
Pruned status sequences are not reconstructed for advisory recommendations.

Startup recovery stores a checkpoint prefix once. If its interruption envelope
crosses the budget, sessions are closed as interrupted before normal retention
runs; pruning is reported explicitly. Authorized history deletion does not
first append the data being deleted, so it remains usable at the recording limit.

Summary retention is until explicit learner/piece/history deletion. File growth,
transaction time and checkpointing must be measured with representative dense
and long-session fixtures; defaults can be revised only with documented effect
on retained coverage. Queries expose retained-since bounds, pruned-detail counts
and censored outcomes. Lifetime coarse counts must not masquerade as complete
note-level lifetime observations.

Versioned migrations belong to `ProgressRepository`. Preserve existing progress
and source/version isolation. Import the bounded old rows once with deterministic
migration identities and `legacy_bounded` provenance. Unknown timestamps,
onset groups, target tempo, rules and matched timing stay unknown. Historical
`passed` is not inferable from its status sequence alone. Do not invent lifetime
counts, dates or note matches. Remove the old active table/writer after verified
migration; an interrupted migration must restart atomically and idempotently.

Export is explicit, local, versioned JSON with schema/rule provenance,
IDs, units, coverage and missingness. Default exports omit source paths,
human-readable piece/device names and raw MIDI bytes; an explicitly selected
detailed export may include note observations. No automatic upload, external
account, background sharing or participant enrollment. A random local learner
ID is pseudonymous, not a guarantee of anonymity for a detailed musical trace.

Define distinct operations before implementing them: reset lesson progress
preserves evidence and records a reset event; delete piece history removes its
linked evidence **and all saved learning progress/generator feedback** for that
learner/source; delete learner history removes all evidence, mastery, tempo
credit, guided state and generator feedback, and generates a new local learner
ID on next use. A new learner cannot inherit the deleted learner's proficiency.
Source files and device-level/audio/window settings remain. Existing reset
currently deletes its short history; P0 deliberately changes Reset Lesson to
preserve the new ledger, with functional wording distinguishing reset from
permanent data deletion. Exports are outside the app's deletion control.
Deletion covers assessments, notes/extras, decisions/outcomes, events and old
import provenance, with no orphan references. It must never delete source MIDI.

P0 includes working export, retention and distinct deletion controls in the
existing Settings UI, using the current visual system and typed commands.
Permanent deletion requires the existing explicit confirmation interaction.
These are functional data-management controls, not a visual redesign. Typed
ports alone do not complete a user-facing data-management phase.

## Read-only analytics and comparable outcomes

Use versioned, validated typed operations with bounded pagination/filters on
the existing in-process queue. They read ledger snapshots, not live plans.
Index learner/session time; attempt session and source/stage/hand/BPM/time;
source-note/attempt; decision/attempt/policy/time; and outcome/decision/state.
No query mutates settlement, progress or a policy.

P1 includes a functional read-only statistics view using existing screen/layout
conventions, with the same coverage labels as exports and typed queries. A
query endpoint without a usable report/view is not the proposed P1 exit gate.
No graphs, decorative layout or new animation style are required.

| Metric | Definition / required qualification |
| --- | --- |
| Pitch accuracy | Correct required pitches / assessed pitch obligations, plus omission/wrong/extra rates separately. Missing/censored targets stay out of observed denominators and are reported. |
| Clean / accepted rates | Separate booleans and eligible full/partial/assisted denominators; never reconstruct from mutable current target or raw repetition count. |
| Timing / hold variation | Signed residual mean/bias, dispersion and quantiles on matched observations; report sample count, local tempo, calibration and missingness. |
| Repetitions and tempo trajectory | Distinct attempt IDs and explicit change events by exact stage/hand/performed BPM/scope; include abort/retry counts. |
| Practice time | Monotonic active intervals; separately show guidance, count-in, feedback, preparation and pause. Wall-clock app-open time is not practice time. |
| Time/attempts to mastery | Existing eligibility criterion and target; include censored unfinished sessions and distinguish historical imported gaps. |
| Error frequency | Source-note, onset, measure, hand, stage and performed tempo with explicit exposure denominators. Optional difficulty features describe score complexity, not player ability. |
| Intervention outcomes | Link decision to the next exposure and unsupported full-target verification. Mark changed range/tempo/support as incomparable; a slower/shorter success is not a causal improvement estimate. |
| Fixed-policy comparison | Descriptive rates/burden at comparable source/tempo/expertise/exposure; selection bias remains. Six baseline IDs and resolved parameters are retained. |

Deterministic replay freezes MIDI/event traces, source and rule/map identities,
clock schedule, policy configuration and initial database. Exercise all six
fixed policies, extra/repeated/chord notes, mixed meter/rests, mapped tempo,
partial/guided reintegration, navigation, reconnect, stale preload, repeated
settlement, write failure and process restart. It verifies engineering behavior,
not unobserved learner responses to alternative interventions.

## Acceptance before phase completion

P0 requires end-to-end callback → grading → decision → persistence fixtures for
every lifecycle boundary above; exact expected/actual matched timings including
wrong repeated pitches and mapped tempo; rollback/idempotency/crash recovery;
all migration/retention/export/delete operations; and no credit from ineligible
routes. Historical diagnostics must read the one ledger. No half-wired table or
unused public endpoint counts as completion.

P1 then requires bounded query correctness/coverage and resource tests against
the same ledger, followed by physical USB/Bluetooth, latency, long-session and
clean-machine gates. Human comparison requires consent, prespecified matched
original-target tests, equal dose, 24-hour delayed unsupported retention and
missingness/frustration reporting. The existing
[retry evaluation protocol](mistake-response-policies.md#evaluation-protocol)
provides that study boundary. Synthetic successes do not establish learning.
