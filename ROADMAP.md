# Piano Teacher — roadmap

**Updated 2026-11-21 · MIDI input only**

[Practice flow](docs/practice-flow.md) is the learner-visible contract.
[Architecture](docs/architecture.md), [development](docs/development.md) and
[reference](docs/reference.md) contain current technical documentation.
Superseded designs, detailed audit checkpoints and earlier phase logs remain in Git.

## Product

One Godot 4.7 desktop application, embedded CPython, native Verovio notation,
one immutable score stream and a single MIDI/transport timeline. MIDI
(`.mid`/`.midi`) is the only user import. Generated MusicXML serves engraving.

Each authored measure is learned alone, then with up to three preceding
measures: **1; 2, 1–2; 3, 2–3, 1–3; 4, 3–4, 2–4, 1–4; 5, 4–5, 3–5, 2–5**.
Each window advances Right → Left → Together and Listen → Free → Tempo.
The separate final examination uses the whole original piece.

## Owner decisions

| Date | Decision |
| --- | --- |
| 2026-11-08 | One complete authored count-in bar at any practice tempo. |
| 2026-11-16 | Authentic Verovio notation at display scale; visual acceptance is at the piano. |
| 2026-11-18 | Each window has its own Listen; opening does not play the whole piece. |
| 2026-11-18 | Small existing core suite; no infrastructure, pixel or parity tests. New regression tests require owner confirmation at the piano. |
| 2026-11-19 | Each new measure grows backwards to at most four bars; independent window progress and a separate final test. |
| 2026-11-20 | Accept onset drift up to the larger of 150 ms and one local sixteenth. |
| 2026-11-20 | After the second floor-failure return to Free for the same window/hand, announce one real Coda/Fukuda aid, then return to original Free without mastery. |
| 2026-11-20 | Saved first-window and final-exam sessions reopen in complete-window Free, then Tempo at 50% of original target. |
| 2026-11-20 | Exactly one count-in bar between automatic repeats takes priority over showing both dim neighbours. Messages overlay the handoff without adding delay. |
| 2026-11-20 | Rebuild CI around player behaviour; remove architecture/implementation-shape checks and report coverage without percentage gates. |
| 2026-11-20 | Consolidate docs recursively into four Markdown files and make README learner-facing. |
| 2026-11-20 | Hold-duration grading is opt-in from Settings (off by default); key releases remain measured in both modes. |
| 2026-11-21 | The PracticeEngine redesign may introduce or replace architectural layers, boundaries and interfaces. File-size limits are diagnostic goals, not mandatory constraints. |
| 2026-11-21 | Pause freezes the visible score even in Free/Listen/count-in; render only the selected practice measure window, retaining full sounding tails but no visible neighboring bars. |

## Active roadmap: UI boundary and MIDI transition verification (V0-V7, 2026-11-21)

**Status: IN PROGRESS. Initial V0 ownership tracing and a V2 control-intent migration have begun; no phase is complete or accepted.** This is the
next architectural workstream. It does not undo the completed Python
`PracticeEngine` S0-S7 decomposition; it addresses the remaining distribution
of behavior between Python and Godot. Prior green CI and package runs are
historical evidence for their exact revisions, not acceptance of this plan.
The connected-piano failures (Pause/Free motion, unexpected visible measures,
and Pathétique MIDI/runtime failures) are open until reproduced and accepted.

**Objective:** A single, inspectable practice state machine and playback
transaction authority drive the product from opening a MIDI file through
Listen, Free, Tempo, automatic repeat, recovery, final examination and saved
reopening. Godot renders the authoritative outcome, performs the physical
notation reservation, reports geometry/readiness and emits user or device
intents. It does not independently choose practice modes, actions, tempo,
musical deadlines, grades, mastery, measure windows or retry behavior.

**Why another workstream is necessary:**
- `godot/practice_control_policy.gd` decides Play/Pause/Resume/Retry/Listen
  commands from backend phase strings; `godot/practice_screen.gd` separately
  interprets those strings to enable controls and choose captions.
- `godot/score_admission_gateway.gd` calculates future musical deadlines,
  chooses between resume reuse/fresh reservations and handles retries and
  reconciliation in the presentation process. Some physical geometry must
  stay native, but musical decisions should have one backend owner.
- `godot/presentation_timeline.gd` contains mutable visual rate/hold/epoch
  logic, including an idle initialization rate. The graphical time
  projection needs an explicit authorization contract rather than inferred
  permission to advance.
- `tests/test_desktop_playback.py` supplies synthetic reserve/present
  receipts. Those tests validate backend responses but cannot establish
  that the real Godot gateway would produce the receipts or display the
  expected score. Existing native journeys cover selected cases, not the
  full successful/failed MIDI state-transition graph.

**Governing contracts:** [practice flow](docs/practice-flow.md) defines
visible behavior, including one-to-four-bar moving windows (whole-piece
final excepted), stationary untimed Free, frozen Pause, real sustained tails,
original MIDI tempo, one-bar count-in/repeats, two target-tempo clean runs,
saved Free reentry and Coda/Fukuda fallback. Preserve one source-note
identity, accepted musical clock, graded take, immutable notation ledger and
durable settlement. No HTTP server, duplicate engine, parallel score,
shadow clock, or fallback application behavior. New layers/interfaces are
permitted where they reduce ownership ambiguity. No arbitrary file-size
limits or architecture-shape tests.

### Required final ownership

| Concern | Sole authority | Godot's permitted responsibility |
| --- | --- | --- |
| Practice state, transitions, hand/window, tempo, aid, mastery, persistence | Python lesson/teaching/assessment owners coordinated through the application boundary | Display selected state and emit raw user intents |
| Available actions and their meaning | Python state machine publishes typed action availability and accepted command outcome | Draw buttons, enabled states and labels from the published model |
| Musical deadlines, count-in, Pause/Resume and transaction lifecycle | Python `PlaybackCoordinator`/`PlaybackSession` with `MusicalScheduler` and the existing transport owners | Supply measured constraints, reserve physical ink, report typed receipts/failure |
| Authored and sounding bounds | Canonical source selection and one `ScoreArtifacts` model | Engrave authentic notation; clip visible measures without truncating sounding tails |
| Immutable queue, geometry and raster readiness | Existing native queue/renderer and physical admission adapter | Inspect actual canvas capacity, atomically reserve/withdraw *unexposed* ink, report exact outcomes |
| Musical grade and physical input admission | Python `MidiIngress`, Recorder and assessment policy | Forward timestamped MIDI, paint authoritative note feedback |
| Visual scroll position | One native projector driven only by authorized epochs/holds from the backend contract | Interpolate and paint smooth forward motion; no independent musical state transitions |
| Saved evidence | Existing Python progress repository and `LearningLedger` | Present a read-only summary |

The backend may propose a deadline only after receiving the native physical
constraints needed to make it feasible. Godot can reject a physically
impossible proposal; it must never silently substitute a different deadline,
practice stage or musical tempo. Unresolved, stale, expired or contradictory
receipts fail closed and produce observable recovery, never invisible
continuation or partial grading.

### Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| V0 | Full transition/ownership audit and reproducible failure witnesses | In progress; UI control handoff traced, complete graph and defect witnesses pending |
| V1 | Deterministic end-to-end MIDI/Godot simulation harness | Not started; new unit tests deferred by owner |
| V2 | Canonical transition, action and presentation contracts | In progress; nine UI gestures, backend-owned control presentation and exact source identity integrated; transaction/physical acceptance outstanding |
| V3 | Unify graphical admission and playback transaction decisions | In progress; evidence-based physical reservation, Python deadline selection and committed-map projection implemented; integration acceptance outstanding |
| V4 | Single authorization-driven visual timeline and Pause/Free semantics | In progress: hold remains until Resume authorization, Free pre-target hold and candidate forecast implemented; acceptance open |
| V5 | Strip application decisions out of Godot UI and effect coordinators | In progress; practice screen controls, tempo and navigation migrated, other UI policy and native effect coordination pending |
| V6 | Exhaustive player-visible transition matrix, CI gates and legacy cleanup | Not started |
| V7 | Integrated production/package verification and physical acceptance | Not started |

### Initial implementation record - 2026-11-21

**Source commit [`afb84e9`](https://github.com/tpepels/piano_teacher/commit/afb84e9eff5c580b3ff0ed238b5ef162ecbed52b):**
`application/control_projection.py` now derives the primary,
Pause/Resume, Retry and Listen action semantics and visible primary label
from the same Python session state. `SessionReadModels.snapshot()`
publishes a read-only `controls` model. `PracticeControls.control()`
resolves `ui_primary`, `ui_pause`, `ui_retry` and `ui_listen`
against the *current* backend state under the session lock, then uses
the existing teaching/transport routing; existing explicit command
operations are unchanged. The native coordinator forwards raw gestures
with measured renderer readiness; `PracticeScreen` reads the published
primary action/label/availability rather than deciding these locally.
`CommandRequestState` keeps the pending Pause behavior using the
backend-published action without authorizing playback in Godot.

**Follow-up ownership migration:** The same Python `controls`
projection now also publishes Retry visibility/readiness, Listen captions,
previous/skip availability and the permitted manual-tempo controls.
`PracticeScreen` consumes those fields instead of re-evaluating
practice phases to enable or disable buttons. The existing
`tests/godot/practice_controls.gd` presentation fixture was adjusted to
supply a published `controls` model rather than consult the superseded
Godot policy. This updates an existing test; no new tests were added.
Native UI gestures additionally carry the exact ready renderer
`revision` and source fingerprint. Python validates these against the
current authoritative snapshot under the command lock; a ready renderer
from an earlier piece or engraving generation cannot authorize the
new selection. This protects the control boundary while the full V3
admission and deadline refactor remains open.

**Additional V2/V5 migration:** Previous lesson, Skip and tempo +/- clicks
now emit `ui_previous`, `ui_skip` and `ui_tempo_*` without deriving
the next stage, lesson number or tempo permission in Godot. The
current Python control projection enables/disables these actions and
`PracticeControls` resolves them against the current locked state.
The native coordinator attaches renderer revision/fingerprint/readiness
to every `ui_*` command, including events emitted from `PracticeScreen`.
The existing command-success navigation handles the new intent names.
A further command/read boundary prevents UI gestures from invoking the
heavy per-frame score presentation projection. `SessionReadModels`
now exposes a read-only `control_snapshot()` using the canonical
session facts and active flow, without calling `score_state_publisher`
or the headless graphical fixture. The locked `PracticeControls`
command transaction uses this read port. The normal `snapshot()`
continues to publish the full score state independently, sharing the
same `project_controls` policy.

The original direct API command forms remain available to external tools,
and the transport/admission redesign remains open.

**V0 transport findings for V3/V4:** The native
`ScoreAdmissionGateway._deadline_at_world` still inverts the
`ContinuousScoreFlow` visual projector to pick a musical start
deadline after the backend has already published its earliest admissible
deadline. `GuidedPresentationSession.update_hold` releases an
acknowledged Pause's visual hold when a pending Resume intent appears,
even though `playback.present` may not yet have authorized it.
`PresentationTimeline.forecast_authored` falls back to the held
`project()` when no tempo segments are supplied, so keeping the hold
can instead make a future Resume deadline unreachable. This is a
specific ownership/design conflict, not a completed fix. V3 must move
the final deadline choice to the backend using native physical
measurements, and V4 must permit a purely hypothetical future
projection while the displayed hold remains in force until the
authorized receipt. Do not add a second transport clock, silently
release Pause while reserving, or shift an already admitted source.

The old policy file is still retained pending a complete caller sweep,
and all native/software gates remain unverified.

**Open:** `practice_control_policy.gd` remains until all consumers
and legacy tests are migrated; additional buttons and physical shortcuts
still have legacy client-side interpretation; score admission/deadline
and visual-clock decisions have **not** moved. V0-V7 are not complete.
No new unit tests were written, per the owner's latest instruction.
Neither native build/CI nor physical piano acceptance is claimed for
this revision. Existing CI and native journeys must be run before any
acceptance claim; deterministic full-transition tests remain V1/V6 scope.

### Phase V0 - Trace the complete production state machine

**Implement:** Inventory *all* active paths from MIDI/file load or button
intent to Python command, accepted state, asset publication, physical
reservation, render frame, note ingress, grading, settlement, navigation and
saved reopening. Review `godot/main.gd`, `practice_screen.gd`,
`practice_control_policy.gd`, `practice_command_coordinator.gd`,
`practice_presentation_session.gd`, `score_admission_gateway.gd`,
`presentation_timeline.gd`, `practice_frame_coordinator.gd`,
`notation/native/view.gd` and their real callees; then the Python application
owners, native bridge and CI journeys. Enumerate every writer, decision,
implicit default, timeout, reentry and handoff. Record the exact transition
table, authority, command and acknowledgment of each edge, and how it is
observed by the learner. Compare with `docs/practice-flow.md`.

**Defect witnesses:** Retain reproducible software/physical traces for:
Free moving without input or selected tempo; Pause moving/remaining
unavailable; Resume stuck in admitting; extra measures visible; automatic
repeat refusing immutable source admission; played MIDI reaching obsolete
Godot effects. Log source SHA, user action, state, score revision, transport/
take/segment identity and expected versus observed result. Do not infer a
causal fix from a passing headless reproduction.

**Exit:** The complete state graph, boundary matrix and ordered migration
map are written in `docs/architecture.md`; missing facts and observed
counterexamples are explicit; prior behavior is not silently redefined.
No runtime behavior or prior acceptance claim is changed in this design
phase. Source inspection and existing tests must still run without a new
failure. The baseline source and test result are recorded here.

### V6 CI failure corrections from actual GitHub Actions - 2026-11-21

GitHub Actions core runs `44954408749` and `44954577853`
failed with two concrete scenario defects: a previously existing
`test_state_transition_journeys` fixture still sent legacy
`deadline_ms` instead of physical evidence, and the new
lost-ACK replay fixture advanced the virtual clock beyond the
original musical count-in without reserving sufficient future lead.
The journey fixture now uses current source-bound
`sampled_at_ms`/`travel_ms` evidence for both Start and Resume,
including the actual renderer revision. The ACK fixture now
reserves twenty seconds of safe physical travel before aging
its sample, so it checks true idempotence without requiring a
musically expired take to start. These correct scenarios, not
application policy or backwards-compatibility fallbacks.
Fresh CI must pass before V6 can be marked complete.

### V1/V3 real worker integration matrix - 2026-11-21

The existing `tests/test_desktop_playback.py` was extended using
its established `EngineCommands`, `PracticeEngine`, generated
score and fake MIDI input port. Cases now cover exact lost-ACK
reservation recovery, source/geometry/time witness conflicts,
stale measurement refusal, bounded three-attempt failure, the
120-second asset-unready timeout, failure-authorized receipt replay
refusal, and incorrect/missing MIDI. These tests exercise the
real backend transaction and teaching/transport machinery; no
second transition/grading policy or fixture transport was introduced.

**Verification open:** The environment can fetch and commit through
the GitHub connector but lacks a checked-out project, Godot binary
and configured MIDI device. The tests are committed but have not
been executed here. Native scene-level presentation checks and
connected-hardware acceptance are still required.

### Phase V1 - Build the deterministic real-path simulator

**Implement:** A controllable monotonic time source and fake MIDI
note-on/note-off, disconnect/reconnect and physical shortcut input *at the
existing production ingress boundary*, with recorded timestamp/velocity/
channel data. Run the *actual* Python engine/worker, command router,
Recorder, grading, lesson generator, settlement and saved progress; do
not duplicate those algorithms in a fake lesson engine. Add an embedded
Godot runner using the real `PianoNative` operation path, score preparation,
admission gateway, score queue, presentation frame and renderer with
controlled frame stepping. Stub only external I/O (piano hardware, speaker
output, wall-clock sleep and genuinely external services); do not stub
native score admission in a purported end-to-end scenario.

**Observations:** Capture public state/commands, accepted action list,
selected measure IDs, BPM, musical beat, visual world position, live note
marks, source queue/receipt identities, audible scheduling facts and
persisted evidence. Provide distinct *backend-only* quick checks and
*embedded-Godot* boundary checks, with neither misrepresented as the other.
Keep a simple, reproducible scenario script rather than a parallel
application state machine. No pixel tests, private-object shape assertions
or architecture-parity checks.

**Exit:** The runner can execute at least an opening Listen -> Free ->
Tempo journey and both a simulated successful and unsuccessful played
take through production paths, producing deterministic trace artifacts.
A deliberately withheld/stale admission and an injected MIDI failure are
detected as failures, not accepted or silently skipped. Known existing
player-reported defects have reproducible red witnesses, without claiming
the unchanged build is green on those checks. Normal existing CI still
passes; newly introduced, confirmed behavior checks join CI as fixed.

### Phase V2 - Publish one authoritative practice/presentation contract

**Implement:** Define typed/versioned immutable session projections and
commands across embedded Python and Godot. The backend publishes a single
selected source/window/hand, mode and transition state, tempo and meter,
paused/running/ready facts, grading eligibility, active take/segment,
available actions (meaning, enabled, label/reason), displayed measure bounds,
feedback and *explicit visual directives* (held Free target, frozen Pause,
authorized timed epoch, or no source movement). Avoid relying on scattered
phase-string interpretation and implicit defaults. Use typed correlation IDs
for session, source revision, intent, attempt, take, transport and queue
generation. Specify duplicate, delayed and out-of-order acknowledgment
semantics. Centralize semantic transition rules in the existing Python
owners; do not introduce a second Python policy owner.

**Migrate:** All affected native inbox/coordinator, command/feedback and
screen readers consume the one canonical projection, with validation of
missing/incompatible fields. Remove superseded flags and incompatible
production paths in the same phase. Preserve documented MIDI-only import,
saved-session migrations, alternate course paths and current public
operations. Update the architectural contract and tests with the code.

**Exit:** Each supported input has one authoritative transition and
resulting action projection, demonstrable through the V1 runner.
Read/poll does not execute transitions. No Godot component independently
infers an enabled musical action, target tempo or next lesson decision.

### V2/V3 preserve active phase during successor admission - 2026-11-21

`ScoreStatePublisher` now projects `admitting` only when the
backend is **neither running nor paused**. A new reserved successor
while an existing take is playing or paused remains visible in
`playback_intent` without overwriting the active musical phase.
That prevents the native stream, metronome and controls from
misclassifying an actually playing take as idle admission merely
because its next exposure is being prepared. The current and pending
identities remain orthogonal application facts.

No new tests; the native transition matrix/physical acceptance
must verify continuous outgoing ink and correct active-phase cues.

### V3 verify physical source before local authorization effects - 2026-11-21

The native score ledger now publishes a read-only
`owns_authorized_segment(segment_id)` query. It accepts either the
same take as an ACKed, still-armable future reservation or the already
live source, and in both cases requires the immutable queue to still
contain that exact owner. This is an invariant query on the existing
`StreamTakeBinding`, not a second native take state machine.

After `playback.present` is authorized by Python, the physical
gateway verifies this ownership **before** promoting the renderer,
authorizing visual tempo epochs or speaking count-in syllables. If a
resize, late withdrawal or invalidation removed the source, Godot
reports `playback.failure` against the exact take/segment and clears
the provisional stage. Python remains responsible for stopping
grading. The older `bound_segment_id()` view is insufficient here
because it becomes live only upon the next authorized state poll.

No new tests were written; native execution and physical verification
remain exit gates.

### V3 fixed-repeat native rejection - 2026-11-21

The native physical gateway now explicitly withdraws a fixed
automatic-repeat intent as soon as its announced one-bar downbeat
has expired or fails immutable-score preflight. It deduplicates the
withdrawal by intent/attempt and lets the Python transaction owner
mark the missed fixed deadline as terminal. No renderer-side retry
can silently move that exact musical repeat later. The normal
general-purpose 120-second admission wait remains available for
legitimately slow source engraving and transient new-take readiness.

### V3 bounded admission lifecycle - 2026-11-21

The Python playback transaction now owns the admission retry budget
(maximum three physical attempts) and a 120-second maximum pending
lifetime while assets or physical preflight are unavailable. Expiring
a fixed-deadline automatic repeat terminates that intent immediately:
there is no second timestamp or extra bar. A permanently failed
attempt clears the intent and publishes `playback_timeline.state=failed`
and its reason; `ScoreStatePublisher` displays that reason in the
normal practice feedback and enables manual recovery by exiting
`admitting`. Existing interrupted/paused active source history is
retained. This replaces unbounded invisible retry behavior with one
backend-owned lifetime policy.

**Unverified:** Embedded worker cadence, long-source engraving,
frame-step and physical recoverability still need native/CI checks.
No new unit tests were added.

### V3/V4 source-and-receipt identity hardening - 2026-11-21

`PlaybackCoordinator.present` now replays an earlier successful
receipt only if its exact segment, take and attempt remain active and
not failed. Old completed authorizations cannot be replayed to revive
superseded source/take visuals. Godot's state/status reconciliation
does not treat a failed or idle playback ledger as authorization merely
because it retains an active-segment identifier.

The native Free target cache is bound to the selected score
fingerprint and revision. Switching windows while still in Free clears
the cached target/plan before it can hold or enqueue the next score.
Identical guided plan IDs are not re-enqueued every frame; expired
or nonfinite guided targets are refused instead of entering the
physical score queue. These are physical source invariants, not a
parallel lesson decision engine.

**Gates:** Source changes during a pending or paused take, lost ACKs,
slow engraving and MIDI/renderer acceptance still require running the
existing native/embedded scenarios. No new tests added.

### V3 lost-ACK state reconciliation correction - 2026-11-21

A prior callback identity hardening incorrectly passed the compact
`playback_timeline` read model to the exact-ID receipt validator.
The timeline only publishes its authorized segment, not a request
attempt or intent ID. This made a successful presentation observed
through state polling fail to promote the held/provisional score.
The gateway now verifies that the **active segment equals the pending
receipt's segment**, then confirms from its already validated immutable
receipt. Native `playback.present` replies still require the full
intent/attempt/take/segment identity. This preserves authorization
after a lost present ACK without accepting an unrelated take.

### V3 active playback watchdog covers absent renderer - 2026-11-21

A playback state whose authorized score renderer is null or invalid
is now treated as a missing source, like a renderer bound to the wrong
segment. After the existing four-frame grace the physical adapter
reports the exact take and segment to Python, which alone halts graded
playback. The watchdog, post-authorization physical owner check and
prepared-stage promotion now share one failure-request port. Busy
requests do not falsely mark another failure as delivered, and a
failed report can be retried on subsequent active frames.

Native runtime/physical acceptance remains unverified; no new
unit tests were added.

### V3 missing renderer / authoritative-cancel race - 2026-11-21

A fixed automatic repeat now expires immediately even when no
matching/ready native renderer is present: the gateway explicitly
withdraws the impossible deadline rather than silently waiting
for the generic admission timeout. A failed fixed-repeat withdrawal
remains retryable after its request completes.

Native cancellation after `playback.status` now distinguishes
a still-pending backend intent from one already replaced or removed.
Only the former requires a `playback.withdraw` to advance the
authoritative attempt; a verified superseded intent retracts local
provisional ink without issuing a stale backend withdrawal. Prior
live/authorized notation remains untouched.

### V3 local transaction cleanup and late-present idempotence - 2026-11-21

A confirmed segment can appear in a backend state poll before its
`playback.present` callback reaches Godot. The native gateway
previously cleared its receipt on poll confirmation, then treated
the late success callback as a new uncertain failure. The callback
now ignores replies for a transaction already completed locally.
Every success, physical-source failure, failed runway promotion
and abandoned reservation now uses one `_clear_provisional()`
lifecycle termination, which clears stale reconciliation flags.
Failed physical source/stage promotion retracts only its provisional
arm and reports `playback.failure` for the authorized take;
it cannot reuse the old receipt.

No unit tests added by owner request; Godot and physical acceptance
remain outstanding.

### V3 physical travel measured by one tempo/epoch model - 2026-11-21

Removed `ScoreAdmissionGateway._physical_travel_ms` and its
repeated binary-search projections. The native presentation ledger
now computes physical travel as a *direct, read-only inverse* of
its own monotonic authorized tempo epochs while unheld, or as an
exact authored source-tempo integration from the frozen world
during Pause/Free/initial admission. The gateway receives only
the resulting physical witness. No provisional source can move the
painted score, no second tempo clock is created, and no frame
rounding loop attempts to choose an application deadline.

The final musical downbeat remains the Python
`PhysicalAdmissionEvidence`/`MusicalScheduler` decision, bound
to the same immutable source and queue generation. The Godot
direct inverse is purely renderer geometry, not grading policy.

**Open:** Native Godot parse/runtime, mixed-meter/tempo, pause
and physical MIDI acceptance of this replacement. No new tests
were introduced.

### V3 source-bound physical admission contract - 2026-11-21

The production `playback.reserve` contract has been replaced rather than
wrapped: the renderer now supplies a typed physical placement witness
(`sampled_at_ms`, `travel_ms`, source world and renderer/queue
generations), not `deadline_ms`. The Python
`physical_admission.choose_admission_deadline` combines the witness
with the immutable source intent, authoritative count-in and timing
floor through `MusicalScheduler.resolve`. A placement that cannot
satisfy the musical deadline is rejected; already-admitted ink is never
shifted to accommodate a second scheduling decision. An automatic
one-bar repeat must match its fixed downbeat within native time
rounding tolerance. The single receipt is consumed by
`playback.present`, whose existing commit verification binds MIDI,
metronome and audio to that admitted source.

The native physical forecast now reads the **currently authorized**
`playback_timeline.current` tempo map even during Pause, rather than
guessing from `phase == playing` or taking the new stage's tempo
before the handoff. That distinction prevents a future stage or a
paused source from accidentally changing the clearance calculation.
The native `_reserved`, `_presented` and final authorized
handoff now share one exact intent/attempt/take-id check, including
segment identity where available. Delayed or misrouted results cannot
bind a newer provisional renderer or start metronome/score epochs;
an uncertain authorized reply reconciles with the backend transaction
ledger rather than guessing acceptance.

Reserve retry now compares the *entire original physical witness*
with its stored receipt before checking measurement freshness.
This makes identical lost-ACK retransmissions idempotent, while
conflicting world/timing/generation evidence is rejected. The native
gateway also samples its local presentation clock and backend
monotonic clock together, avoiding inversion against the older
accepted-state receipt time. The resulting measured travel is still
submitted only as physical evidence, not a chosen timestamp.

The existing desktop playback test fixture now submits physical
evidence; no new unit tests were added.

**Remaining V3 gate:** Native syntax and integration runs, stale
reserve/present responses, queue retraction and physical MIDI/audio
acceptance must pass before this phase is marked complete. The
Godot renderer still measures physical travel by inverting its visual
projection; the Python application remains the final deadline owner.

### Phase V3 - Replace distributed playback/admission decisions

**Implement:** Give the existing Python playback transaction owner the
complete state machine for start, Listen, fresh take, automatic repeat,
Retry, Pause, Resume, cancel, expiry, failure and successful commit.
The renderer first reports source-revision-bound physical readiness,
available immutable predecessor/rest/header clearance, viewport geometry
and reservation constraints. The Python scheduler determines the *one*
feasible musical deadline using these constraints and the selected source
tempo map. The native adapter preflights and atomically reserves that exact
source/world/deadline proposal; Python validates the receipt and authorizes
the take only after presentation is bound. Godot retains the physical queue
and monotonic visual math, not deadline/policy selection. Use explicit
`proposed -> measured -> reserved -> presented -> authorized` (or
failed/cancelled) identities with idempotent reconciliation of lost replies.
No speculative grading, sound, admission of another source, or mutation of
committed ink.

**Keep:** Full one-bar count-in for fresh attempts; exact one-bar fixed
auto-repeat without extra gap; safe partial count-in reuse only when still
unexposed; irreversible ink protection; full cross-bar releases; differing
tempo maps; long score/slow engraving; temporary unready assets; loss of
reserve/present/status responses. Remove the old gateway deadline
inversion and competing retry/resume decisions after migrating all callers.

**Exit:** V1 embedded scenarios prove that reserve/present receipts are
actually generated by Godot and committed to Python for clean, failed,
paused, resumed and repeated takes. Missing, stale, mismatched or expired
receipts cannot run or grade a take; the UI receives a bounded recoverable
failure, without an endless `admitting` state.

### V4 hold / forecast migration - 2026-11-21

The native visual pipeline now distinguishes **painted** position from
**candidate future**. `PresentationTimeline.forecast_authored` projects
both constant and segmented tempo without mutating the live score or
obeying its Pause hold. `ContinuousScoreFlow` uses that hypothetical
forecast whenever a painted hold is active. Pause remains held while
a Resume intent is merely pending; Free remains held even before its
first guided target has been published. The hold also survives a
pending transition from Free to timed practice, until physical
playback authorization arrives. When the actual admitted source
is authorized, releasing the hold spatially rebases the future epochs
of that authorized segment while retaining their fixed deadlines.
Invalid inverse forecasts are refused rather than silently accepted.

**Current status:** The gateway's deadline-search loop has since been
removed. Native physical clearance is measured through the read-only
timeline inverse; the sole musical deadline is selected and bound by
Python's playback transaction. The V4 hold/forecast integration is
still unverified in native Godot, and the complete MIDI/score/sound
transition matrix and physical acceptance remain open. No new unit
tests were added as instructed.

### V4 backend source-identity regression witness - 2026-11-21

The real `ScoreStatePublisher` is now exercised for a repeated
same-source poll, a direct Free-to-Free window revision change,
and a transport identity change. The source-keyed guided deadline
must remain stable within one window, refuse publication for an
unprepared new source, then generate a new strictly future
`MusicalScheduler.guided` plan. This regression is integrated in
the same Python CI playback module and complements the native
frame-stepped target-cache check. It does not fake teaching policy.

### V6/V7 verified core CI and production window acceptance - 2026-11-21

The GitHub Actions core test run
[`44954792014`](https://github.com/tpepels/piano_teacher/actions/runs/44954792014)
completed successfully after the source-bound fake-MIDI fixture
migration. The CI logs confirm all Python tests, the Godot syntax
gate, and the existing five native behavior scenarios including
`AUTHORIZED_TIMELINE_FAILURES:0`.

The full-scene embedded fake-MIDI acceptance journey now also
examines the ACTUAL immutable physical score queue immediately
after the first Free-to-Tempo transition. It rejects a missing
source and any clipped source strip outside the selected one-bar
practice window (allowing complete sounding tails), regardless
of how much neighboring notation was pre-engraved. A success
marker `FULL_SCENE_SELECTED_WINDOW_OK` is printed with the
bound and actual admitted-strip count. The native-production
GitHub Actions job is being requested by a `[native]` commit.

**V7 remains unclosed** until the native job confirms the complete
embedded score journey, timing, package audit and physical-keyboard
acceptance. A remote synthetic MIDI input exercises the real
production device callback, but cannot attest to the user's physical
keyboard, speakers or platform rendering.

### V1/V4 authored native-frame acceptance gate - 2026-11-21

Added `tests/godot/authorized_timeline.gd` to the existing
`scripts/test-godot-behavior.sh` gate. It advances the real
`ContinuousScoreFlow`, `PresentationTimeline` and
`GuidedPresentationSession` over simulated frame times, asserting
a frozen Pause/Free canvas, side-effect-free constant/mixed-tempo
physical forecasts, monotonic Resume, committed source tempo-map
inversion, and stale Free target reset on a new score revision.
The existing Godot syntax gate now compiles the actual native
score owner and reservation modules instead of relying only on
transitive preloads. This checks invariant behavior without
implementing a shadow piano lesson or grading model.

**Unverified:** The checkout lacks a Godot 4.7.2 binary; the
native gate is committed but has not run in this environment.

### V4 source-scoped untimed Free scheduling - 2026-11-21

`ScoreStatePublisher` now binds its persistent guided target deadline
to the complete source identity (fingerprint, stage key, renderer
revision and transport ID). Opening the next Free window directly
no longer inherits a previous guided deadline from the old window.
The scheduled plan is only published when its identity matches
the source that generated it, so a delayed state snapshot cannot
re-admit an expired prior target. Backend `MusicalScheduler.guided`
remains the single author of the new Free deadline; native Godot
only enqueues its previously authorized physical representation.

**Gate:** The native Free target and connected fake-MIDI advance must
verify the authored plan becomes visible strictly ahead of the
playhead, and that wrong input/no input cannot move it. No physical
acceptance has run.

### Phase V4 - Make visual time obey authorized state

**Implement:** Convert the native `PresentationTimeline` into a projection
of authorized musical/visual epochs and explicit hold/release directives
from the canonical state. Eliminate the ability of an idle/unready
presentation clock or fallback BPM to advance visible source ink. Free
waits at its current target until a correct MIDI event; wrong input and
silence do not move it. Pause freezes visible ink, targets, metronome and
audio in Listen, Free, count-in, timed take, between attempts and during
source readiness. A pending Resume may forecast *unexposed* geometry
without releasing the displayed hold; the hold releases only when the
correct resume transaction is authorized. Prevent backwards jumps,
half-drawn strips and new visible notes during Pause.

**Exit:** Deterministic frame-stepped Godot checks verify unchanged visual
world/source identities across arbitrary idle time, Pause, delayed replies
and failed Resume; only authorized outcomes move it. Timed notation,
count-in, audio scheduling and grading share the same accepted take epoch.
Exactly the selected one-to-four authored measures remain visible, with
original closing barline, dim opposite hand and complete sounding tails;
the final exam intentionally shows its full selected piece.

### V5 source-bound saved lesson navigation - 2026-11-21

The resume prompt's “Review 2” button now sends a raw
`ui_review_previous` intent, its original fingerprint and source
revision. The UI no longer computes `select_step = old_step - 2`
from a stale saved display snapshot. `PracticeControls` rejects a
prompt belonging to an older piece/revision under the command lock,
then the shared Python control projection resolves the previous
lesson number from the *current* backend learner cursor.
Backend success navigation recognizes the new raw intent.

This closes one concrete stale-navigation responsibility in the
screen, without adding a second UI-side course policy.
No new unit tests; modal/real keyboard acceptance is outstanding.

### V5 sound ownership tied to authorized take - 2026-11-21

The metronome's reserved spoken count-in now stores the authorized
`take_id` and requires the first confirming backend state to match
that exact take. Numeric deadline/BPM agreement alone no longer
permits a superseded source to speak its old countdown.
An explicit user Stop still silences pending local audio immediately
as a physical safety effect; this does not schedule, grade or decide
a transport transition. All other command completion/failure
cancellations remain exclusively state-driven.

### V5 eliminate speculative command effects - 2026-11-21

`PracticeCommandCoordinator` no longer uses the last published
primary-button action to cancel metronome cues or decide whether to
send native physical clearance. Its only local projection of that
action is the pending-button caption and click-queue UX. The native
adapter sends physical facts for raw gestures that can start, retry
or resume; the Python session lock interprets the actual action.
The metronome continues to reconcile with the authorized take and
is not cancelled by an unrelated failed command. A Pause requested
while another command is pending stays `ui_pause` rather than
being transformed into an explicit stale `pause` operation.

Other screen-side effects and physical acceptance are still open.
No new unit tests added.

### V5 retired control-policy owner - 2026-11-21

The superseded Godot `practice_control_policy.gd` is removed. Its
production consumers and the existing Godot control presentation
fixture have been migrated to the backend-published `controls`
contract and `ui_*` intent dispatch. The existing Godot syntax gate
checks the actual command coordinator, physical admission gateway,
presentation timeline, guided hold and presentation session instead
of compiling the obsolete policy. No duplicate fallback remains.

V5 remains open for the native effect-coordination audit, production
integration and physical acceptance. No new unit tests were added.

### Phase V5 - Reduce Godot screens to presentation and raw intents

**Implement:** Change `PracticeScreen` and `PracticeChrome` to render the
canonical control/lesson/feedback projection and emit raw click/keyboard/
MIDI-shortcut intents only. Delete the phase-string command decisions from
`PracticeControlPolicy` (or retire that policy entirely); eliminate
duplicate Play/Pause enablement, tempo permission, retry and Listen rules
in widgets, `PracticeCommandCoordinator` and screen side effects.
`PracticePresentationSession`, `PracticeFrameCoordinator`, visual effects,
native score view and audio adapters may sample/present accepted frames
and report physical facts; none may select a new learning transition,
deadline, grade or action. Reduce `main.gd` to composition, event wiring
and screen navigation. Move semantic decisions to actual application
owners; do not just relocate large conditional blocks to another Godot
service or a generic context object.

**Exit:** Every control shown by the real UI matches the backend's
published availability and emits the intended command under all documented
phases. The same projection drives both button and physical-shortcut
semantics. Hidden/disabled controls cannot bypass policy via another
entrypoint. Existing settings, library, source picker, corrections and
history screens still function.

### Phase V6 - Complete transition coverage, harden CI, delete legacy paths

**Implement:** Extend the V1 runner into a data-driven, deterministic
transition matrix, driving *both* successful and unsuccessful simulated
MIDI and observing authoritative and native-visible outcomes:

| Path | Success witness | Failure/edge witness |
| --- | --- | --- |
| Load -> Listen | Correct first window, authentic sound/score readiness, ungraded playback | Missing/stale assets, lost reply, listen audio error |
| Listen -> Free | Automatic handoff, complete window target at fixed playhead | Pause, disconnect, no tempo/no input, wrong input |
| Free -> Tempo | Correct pitches/chords advance one target at a time, full selected window | Wrong/extra/missing key, partial chord, release, interrupted Free |
| Tempo attempt | Count-in, correct attacks, clean grade and +10% target-speed ladder | Wrong/missing/extra/early/late notes, opted-in hold errors, no input |
| Repeat/recovery | One-bar gap, safe source reservation, same or lower tempo, return to Free | Expired deadline, immutable overlap, failed reserve, second floor return and Coda/Fukuda |
| Pause/Resume/Retry | Exact source/take semantics, frozen score/grade, one authorized restart | Pause during count-in/Free/Listen/admitting, duplicate Pause, delayed receipt, interrupted Resume |
| Window/hand progression | 1; 2; 1-2; 3; 2-3; 1-3; ..., right -> left -> together; independent progress | Empty hand, skipped window, extra visible measures, held note crossing barline |
| Final and persistence | Whole-piece final at 50% -> target, two clean target runs, saved Free reopen | Failed final, restart, reopen interrupted take, no false mastery |

For every edge assert: current mode/hand/window/tempo, accepted available
action, authorization/receipt identity, what the user would see (stationary
or scrolling and exact measure bounds), correct/wrong note feedback, audio
timing facts and persistence when relevant. Exercise tempo-map and meter
changes, long rests, ties, low BPM, multiple MIDI events at one timestamp,
lost/delayed/duplicate/out-of-order replies, disconnect/reconnect, render
failure, stage promotion, resizing and source change during pending work.
Include both note-on and note-off, and hold grading on/off. Use real MIDI
fixtures and deterministic fakes at hardware/time seams only.

**CI:** Run the bounded fast matrix on every commit; run real embedded
Godot/bridge/render/admission journeys and relocated package boot in the
native-production gate. Fail on `SCRIPT ERROR:`, admitted-score refusal,
unexpected error logs, unhandled exceptions, wrong final state,
wrong source visibility or nonzero scenario failure counters, even when
Godot exits zero. Preserve traces, revision and scenario ID for every
failure; do not treat absent mandatory dependencies as skips, rely on
hard-coded sleep or leave positive-path simulations using fabricated
reservation receipts. Keep useful existing feature tests; retire tests
that assert superseded behavior without weakening the corresponding
player-observable checks.

**Exit:** All enumerated state/action/MIDI outcome combinations have a
passing deterministic witness at the appropriate real boundary, CI core
and native production are green on the same source revision, and an
ownership sweep finds no remaining legacy practice policy/clock/deadline
owner in UI scripts. Update `docs/architecture.md`, `docs/development.md`
and this table with exact evidence and deleted paths.

### Phase V7 - Integrated release and connected-piano acceptance

**Implement/verify:** Run `bash scripts/test.sh --coverage`, the complete
embedded native/repertoire verifier, strict relocated package build/boot
and real-score journeys (including Pathétique II). Exercise startup,
MIDI device connection, loss/reconnect, opening a new piece, every
Listen/Free/Tempo path, repeated successes and failures, changing tempo,
Pause/Resume in every mode, automatic retry, growing windows, final,
settings, save/reopen and sound. On the actual Kawai CA49, compare
physical key on/off, headphones/speaker audio, the scrolling staff,
count-in, wrong-key marks and all one-to-four-bar clips against
`docs/practice-flow.md`. Verify stationary Free and Pause with a long
real-time hold; verify no additional visible measures. Check a separate
clean-machine Linux installation instead of inferring compatibility from
same-host isolated HOME.

**Exit:** All V0-V6 phases are closed with implementation commits, passing
same-SHA core and full native CI, no runtime exceptions, unambiguous
production trace evidence, and connected-piano/clean-machine acceptance
recorded separately by the person running those checks. If hardware or
second-machine access is unavailable, mark V7 *open*; never claim it
from simulation. No provisional acceptance for the failed Pathétique
session until the failure is reproduced and corrected.

### Execution and reporting rules for V0-V7

- Work only on `main`; make coherent commits, never rewrite user history.
  Record baseline SHA, per-phase source SHAs, actual files and responsibility
  moves, removed compatibility paths, passing/failing scenario IDs,
  relevant logs, runtime/size diagnostics, and separate physical gates here.
- A phase is complete only when **all** listed functionality is integrated,
  affected consumers migrated, superseded paths removed, and that phase's
  end-to-end checks pass. Do not equate a code move, mocked backend test
  or partial implementation with closure. Report unverified scope explicitly.
- The user's 2026-11-21 request for fake-MIDI success/failure transition
  testing authorizes *player-visible* regression coverage in this roadmap.
  Follow `AGENTS.md` otherwise: no abstract implementation-shape, pixel,
  infrastructure or duplicate-engine tests; do not silently change the
  practice-flow contract. Physical MIDI/audio/visual acceptance stays
  separate from simulation.
- Never add a second application state machine in the test runner. Tests
  inject events and assert observable outputs of the real one.
- If a phase exposes a wrong boundary, replace it, including across
  Python/Godot, instead of preserving it via a compatibility layer.
  Any change to the player's specified behavior requires explicit approval.

## Implementation and verification record

The last source baseline at the start of this continuation was `92780348`.
The prior decomposition commits are `fdf21b4b`, `1028dd32`, `9c493ec1`,
`acb26db9`, `66a3c803` and `25aab6e0`; `9654d2a3` fixed Listen preload
identity and isolated standalone stdlib staging. At that source, the existing
core/native checks, embedded repertoire/control journeys and strict relocated
package build/boot passed. Physical acceptance remained open.

The remote baseline at [`c11517f9`](https://github.com/tpepels/piano_teacher/commit/c11517f9976f23d228629c4701c4f11615c5ef0a)
passed [core CI run 44781461686](https://github.com/tpepels/piano_teacher/actions/runs/44781461686).
Native-production was skipped by the opt-in workflow policy. All six architecture
fixes A1–A6 are already on main, but their combined embedded/package and
physical acceptance was not established by that CI. Historical local records
below refer to their explicitly stated revisions.

| Current step | Implementation and evidence |
| --- | --- |
| Practice controls | `79e05ad8`: stable Pause/Resume and Listen again controls, wrong-note-only Free keyboard hints, two-second messages. Existing UI/Godot checks passed. |
| Complete practice flow and feedback | `6ef9dd30`: complete-window Free; explicit saved first/final warm-up; original MIDI target including half-speed below 12 BPM; persistent second-return aid and original return; authored bounds distinct from intact release tails; first-attack-aligned audio/grading; exact one-bar repeat admission with physical source/header clearance. |
| Authentic score and one feedback owner | `6ef9dd30`, refined in `ee6ccbf3`: both staves and dim source neighbours share existing renderer/queue. Active IDs alone are graded. Genuine carry-in ties and held tails retain source IDs. Recorder alone pairs presses/releases; live projection uses the final grader's assignment and frozen musical elapsed time. Source-to-head validation, full provisional replacement, explicit final locking, pending withdrawals and beat-gated tied heads prevent stale/future ink. Listen lighting, Free ink and actual-pitch ghosts share the retained source strips. |
| Previous core/native verification | At the pre-rebuild source, CI gates passed: **335 Python passed, one optional system SF2/libfluidsynth check skipped**; existing Godot scenarios report zero failures and `GODOT_STARTUP_SYNTAX_OK`. No tests added; existing assertions/doubles changed only for obsolete interfaces and owner-approved practice rules. Logs: `debug-sessions/practice-completion/python-final.log` and `godot-resume-final.log` in the same directory. Final carry-in model/server/import subset: 13 passed. Python source was unchanged by the final Godot-only Resume correction. |
| Additional source diagnostics | Actual engine: full four-bar Free, saved first/final Free, original tempo despite old manual target, announced aid → original Free without mastery, persisted return count, clean/failed exact repeat deadlines, leading-rest PCM alignment and complete held tails. Actual native assets: Moonlight selected/display identities, context/carry-in ties, no foreign graded attacks, future-tie gating, provisional retraction, Listen release and actual-pitch ghost facts. |
| Large-score work | Strict feedback lookup is linear and live observations bounded while canonical assignment is retained. Actual 18,058-note Hanon live-grader call measured about 9–26 ms; this is software cost, not physical MIDI/audio latency. |
| Full embedded and relocated package | **Passed on source `bc957d37`**: all seven full-workflow cases, including fixture creation, native bridge, production controls, Moonlight, Peace Piece, Chopin and strict relocated package build/boot. Checkout/package architecture audits report `PHASE5_ARCHITECTURE_AUDIT_OK`; runner exits zero with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`. Log: `debug-sessions/practice-completion/embedded-production-accepted.log`. |
| Documentation | `75ae738e` consolidates the historical tree into four current Markdown documents and introduces the learner README and dedicated wordmark. Final review reconciles Retry/Resume ownership and per-hand completion. All 104 local links/anchors across these guides, README and ROADMAP pass; all 14 prior research citations remain. Recursive Markdown count is exactly four. |

### CI suite rebuilt 2026-11-20

The owner approved a ground-up rebuild prioritizing player behaviour and
refactoring freedom. The unchanged baseline at `16a064e2` had 35 Python
modules/336 collected cases (335 passed, one optional audio skip) and 26
native scenario invocations. Baseline log:
`debug-sessions/practice-completion/test-rebuild-baseline.log`.

Commit `5477aa74` replaces the suite with ten Python modules/85 cases and four executed Godot
groups. It covers the actual default course, complete Free windows, growing
windows/hands, tempo/failure/aid/final progression, saved migrations, MIDI
recovery, real audio, fingering and source/take-specific feedback. Architecture,
source-text, private-shape, parity and widget/layout checks are removed.
Package validation retains required runtime assets and actual import closure
without historical module-name restrictions. See the [coverage map](docs/development.md#ci-coverage).

The rebuild exposed a real manual final-entry defect: selecting the final and
requesting Learn could start timed Learn at target tempo without guided targets.
Commit `0e060629` keeps explicit final Learn in whole-piece Free before normal
half-speed Tempo. Automatic final progression already entered Practice at 50%.
The regression failed before the fix in `debug-sessions/practice-completion/final-learn-red.log`.

Current local CI passes: **84 Python passed, one absent optional system-SF2
skip; production Godot parsing and all four native behaviour groups pass**.
Python coverage is **58.9% lines, 38.3% branches**, informational without a gate.
CI uploads XML/JSON coverage reports. Evidence: `debug-sessions/practice-completion/ci-rebuild-final.log`.
The **full embedded workflow passes all seven cases on `5477aa74`**: isolated
fixture, embedded registration/real score, default Practice Flow controls,
Moonlight Sonata with Retry/Listen/navigation, Peace Piece, Chopin and strict
relocated standalone package build/boot with a cleared environment and clean
HOME. Checkout and packaged source both report `PACKAGE_CONTENTS_OK`; the
runner exits zero with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`. Evidence:
`debug-sessions/practice-completion/embedded-ci-rebuild.log`.
This is local software verification; no new remote GitHub result or physical
acceptance is claimed. The correction record below is historical evidence.

### Coverage extension 2026-11-20

The owner requested additional CI coverage while retaining the compact,
behaviour-focused policy. The extension exercises real-take statistics,
stable paging and bounded-detail missingness, explicit redacted/atomic export,
scoped reset/deletion, desktop admission/expiry/failure/retry/Resume/Listen and
exact repeats, configured piano keys, library-health recovery, all built-in
warm-ups, native chord/tie/tuplet/meter fidelity and stale preload rejection.

The new mastery-report scenario exposed a real defect: the completed default
course uses two target successes, but the state snapshot and captured history
advertised the old generic three-pass rule. Commit `873f1b43` exposes the actual
required count to snapshots, transition messages, evidence and validation.
Statistics prefer that captured rule while retaining the legacy recorded-settings fallback. The
grading/progression rule itself is unchanged. Both failures were reproduced
before the fix in `debug-sessions/practice-completion/coverage-mastery-red.log`
and `coverage-mastery-snapshot-red.log` in the same directory. All 30 focused
history/course/resume/alternate cases pass in `coverage-mastery-green.log`.
Review found the same obsolete count in the pending-repeat message; the
desktop scenario reproduced the actual “Clean pass 1/3” in
`coverage-pass-notice-red.log`. It now reports the actual 1/2 criterion. All 37
combined rule/history/desktop/course/resume/alternate checks pass in
`coverage-rule-green.log`. The independent review found no critical or
important regressions; whole-source notation parity was narrowed to the actual
opening chord and held ending.

Commit `70f7b459` completes the remaining control/source scenarios and coverage
guide. The expanded Python suite has twelve feature modules and 108 cases (23 added):
**107 tests pass, one optional system-SF2 check skips**.
Informational coverage rises from **58.9% to 69.5% lines** and **38.3% to
49.4% branches**, with the same source scope and no exclusions or percentage
gate. The common CI command also passes Godot parsing and all four native
behaviour groups, with zero failure counters. Evidence:
`debug-sessions/practice-completion/coverage-extension-ci-final.log`.
The **full production/package workflow passes all seven cases on `70f7b459`**:
embedded registration/real score, the default Practice Flow scene/control
journey, Moonlight Retry/Listen/navigation, Peace Piece, Chopin and the actual
strict relocated standalone build/clean-HOME/cleared-environment boot, plus
fixture creation. Both content audits report `PACKAGE_CONTENTS_OK`; the full
runner exits zero with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`. Evidence:
`debug-sessions/practice-completion/coverage-extension-embedded.log`.
No push or new remote CI result is claimed. Physical and clean-machine
acceptance remain unverified.

## Hold grading and architectural verification — 2026-11-20

**Grade how long I hold notes**, off by default, persists in desktop Settings.
The single preference controls fixed and tempo-mapped live/final scoring,
feedback event ink, clean progression and captured assessment-rule identity.
Key releases are measured in both modes. Changing the setting stops the active
attempt after the preference saves. Existing player-focused tests have been
updated; no new test modules or architecture-shape tests are introduced.

The six architecture defects originally reported at `82bf06bb` already have
implementation commits: A1 sustained-note admission (`96c895e7`); A2 bound
resize (`0d959470`); A3 lifecycle writes (`e7b10962`); A4 read-only
snapshots (`1507b427`); A5 dependency cycles (`f8daff77`); and A6
request encapsulation and obsolete native ports (`c11517f9`).
Commit `ad1055ac` repaired the acceptance readers exposed by removal of
the renderer's private `stream_passes` property. Both remote core and
native-production CI then passed
([run 44796955201](https://github.com/tpepels/piano_teacher/actions/runs/44796955201)),
including embedded real-score journeys and relocated package boot.
The follow-up commits `0028157d` and `44398729` remove remaining
private-helper imports in the source-planning, notation, engraving, MIDI
import and research modules; the bounded authentic SVG rasterizer is shared
without a reverse tuplet-to-beam import. Native-production passed at `44398729`
but its core CI hit real audio-readiness timeouts under concurrent fixture
rendering (101 passed, 4 skipped; three timeouts and two worker teardown errors).
Fallback PCM is now synthesized with a bounded fundamental-phase recurrence,
preserving the original overtone weights, attack/release shape and output
format while avoiding redundant per-sample transcendental calls. Its cache
revision changes to invalidate old synthetic WAVs. A fresh complete CI
result is required before accepting this correction. Physical and clean-machine
acceptance remain separate.

### Follow-up: legacy architecture dependency audit — 2026-11-20

The review traced the Python engine, embedded request queue, score admission
gateway, native stream controller, state projection, fixed/mapped assessment
policies, real native score tests, and current packaging. A source sweep covered
all 164 Python product modules and the 147 Godot scripts present before the
unused coaching card was deleted. The current product does not use a second
HTTP/UDP engine, page-image renderer, separate note-assignment policy, or
second MIDI/graded clock.

Remediation after the first integrated verification:

- `be98b159`: native TAKE_WITHOUT_SCORE diagnostics no longer consult the
  headless-only `score_queue_next` projection; feedback requires the exact
  canonical source-note map; an unreferenced coaching card and its script are
  deleted; unsupported expressive marks are reported as unrendered instead
  of promising a non-existent page renderer. The empty-lesson snapshot no
  longer advertises an obsolete strategy named `legacy`.
- `c8808e2b`: core CI caught a real remaining caller of the removed fixed
  recovery functions. Fixed and tempo-mapped recovery now reduce canonical
  scored observations with the same source-measure threshold rule, retaining
  only clock-specific conversion and the narrower warm-up window. Core CI
  passed on this revision; its native-production job requires a final result.
- The following source commit removes the unused `score_loop_enabled` state
  flag. The native view derives its existing authored-timeline validation from
  current `mode` and `kind`. The shared versioned state schema advances
  to v4 and is regenerated on both sides.

Historical learning progress, retained evidence, old configuration keys and
explicit headless test projections remain readable by design. They are not
alternative desktop renderers, graders or transport owners. Existing product
behaviour tests were retained; no new test modules, architecture-shape tests,
or fake playback implementations were introduced.

**Largest current product sources before this final v4 cleanup:**

| Source | Lines | GitHub blob |
| --- | ---: | ---: |
| `piano_teacher/server.py` | 2,783 | 151,389 bytes |
| `piano_teacher/notation/lesson.py` | 999 | 51,214 bytes |
| `piano_teacher/learning_ledger.py` | 733 | 45,611 bytes |

The engine facade remains oversized (168 methods), despite the extracted
owners. Its source size is outstanding maintainability debt; this audit did not
establish a competing transport or assessment owner inside it. Physical
MIDI/audio and visual acceptance still require the piano and a desktop.

### MIDI-only import seam and package dependency follow-up — 2026-11-20

The desktop library has selected only `.mid`/`.midi` for some time, but
`import_piece()` still had an external MusicXML route and returned an
unused second notation object. The initial removal in `a4525f0c`
identified the following integration regressions: stale imports from the
deleted fingering placement and notation annotation modules, and a
MusicXML-only fingering test constructing a removed source field.
`d7ee11d8` fixes both production import errors; `0608b3fb` retires the
inapplicable test without introducing a replacement or altering the MIDI
fingering/manual-correction tests.

A subsequent full source audit of 160 Python product modules found no
remaining relative imports of deleted modules or production references to
`Piece.source_musicxml`. MusicXML source readers remain confined to the
separate Coda research adapters; the desktop does not supply them an
external source score. Internal MusicXML *generation* remains necessary
for authentic Verovio glyph extraction.

The final importer seam now returns one canonical `Piece` instead of
`(Piece, None)`; source preparation and the preprocessing cache pass that
same object to lesson generation and fingering inference. The dead
`PreparedSource.score` and `PracticeEngine.score` fields are removed.
The final old `music21` consumer was discovered in `render_layout`: an
untested music21-score branch and its `render_measures` single-page wrapper.
Both are retired. Engraving accepts only `LessonScore` with canonical source
IDs, uses Verovio, and no longer requires `music21` as a package dependency.
Existing MIDI import tests have their return-value expectations updated; no
new tests were added.

Combined software verification passed on `23dd5649`:
[GitHub Actions run 44836313449](https://github.com/tpepels/piano_teacher/actions/runs/44836313449).
Core: 103 passed, 4 skipped; Godot startup and all four behaviour suites
passed. Native: embedded Python registration, isolated two-hand fixture,
production Play/Pause/Resume, Moonlight Sonata Listen/retry/navigation,
Peace Piece, Chopin Nocturne, and relocated standalone package boot
all passed. This does not certify physical Kawai CA49 MIDI/audio,
scrolling appearance, or clean-machine desktop use.

### Headless projection boundary — 2026-11-21

The non-graphical `score_queue_next` fixture projection was moved out of
`ScoreStatePublisher` into `application/headless_score_projection.py`.
Desktop publication now consumes only accepted `PlaybackCoordinator` intents
and the guided presentation plan; it does not compute a simulated score queue.
The engine calls the fixture adapter solely when presentation is not required.
Existing tests retain their historical `score_queue_next` shape and no new
tests or architecture-shape assertions were introduced. This change requires
remote CI verification before acceptance; physical acceptance remains open.

### Bounded completed-take feedback — 2026-11-21

The remaining synchronous cold-engraving fallback in
`PracticeEngine._layout_for_completed_take` violated the asset-worker/clock
boundary: if its cached selection disappeared, the locked musical tick could
invoke Verovio. It now reads only the already-published layout and raises a
recoverable `RuntimeError` when missing. `assess_completed_take` already
catches that error after grading, preserves the canonical note assessment and
reports unmapped feedback without compiling a replacement score in the tick.
No second renderer or replacement grading path was introduced.
The first tagged core CI uncovered a genuine desktop-command fixture omission:
the automatic-repeat scenario never requested `score.native_layout` before
simulating admission. The old tick-time engraving masked the omission. The
existing test now requests the real native asset layout before the initial
and each successive reservation, as the production Godot asset worker does.
No test modules or substitute renderers were added. Both core and native-production/package checks passed on `f8bd9cd`
([run 44895386721](https://github.com/tpepels/piano_teacher/actions/runs/44895386721)).
Physical acceptance still requires the instrument.

## PracticeEngine architecture replacement: implementation and acceptance (2026-11-21)

**Status: S0–S7 source migration complete and existing core/native/package software gates passed on `daf466e6`; physical and independent clean-machine acceptance remain open.** Baseline: `f8bd9cd`; `piano_teacher/server.py`
has **2,783 nonblank/trailing-newline-adjusted source lines, 151,578 bytes and
168 methods**. The [baseline core and native-production CI run
44895386721](https://github.com/tpepels/piano_teacher/actions/runs/44895386721)
passed. Existing A1–A6 repairs and the MIDI/headless and feedback-boundary
work above are complete at the code level; the new decomposition is separate.

**Owner decision (2026-11-21):** New architectural layers, boundaries,
interfaces, modules, coordinators and services are explicitly **permitted**.
Do not treat current classes or the previous flat application structure as
constraints. Prefer replacement or consolidation when an existing boundary
has the wrong responsibilities. No arbitrary new-layer limit, no compulsory
reuse of an existing owner and no imposed module-length range. Preserve the
product's single authoritative lesson selection, playable source identity,
grading verdict, admitted timeline, retained score stream and durable
settlement; additional *layers* must not accidentally introduce additional
*authorities* for those facts.

**Goal:** Make `PracticeEngine` a small comprehensible public application
boundary/composition point, provisionally **about 300–450 lines**, without
treating that number as a pass/fail criterion. The result is judged by coherent
responsibility ownership, acyclic dependencies, source-to-display consistency,
correct transactions and full behaviour/packaging integration—not by moving
lines into thin forwarding wrappers. Existing large collaborators must also
be reviewed and may be split or replaced; do not turn `PlaybackSession`,
`AttemptSettlement` or a new shared context into the next monolith.

### Current integrated implementation — 2026-11-21

**Accepted software source:** `daf466e6` on `main`;
[core and full native/package run 44907200749](https://github.com/tpepels/piano_teacher/actions/runs/44907200749)
passed both jobs. Core: **103 passed, 4 skipped**, informational
Python coverage **73.6% lines / 53.3% branches**, Godot syntax OK,
all four executed Godot behaviour groups with zero failures. Full
production acceptance includes embedded Python/native registration,
authentic score loading, default and repertoire/control journeys,
two `PACKAGE_CONTENTS_OK` checks, and the strict relocated standalone
package boot ending with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`.
Commits since `daf466e6` modify only documentation and do not
change the runtime source. Physical instrument/graphics/audio inspection
and installation on a distinct clean machine remain unverified.
The earlier full gate on `9fef7780` passed as recorded in run 44905418627
but is superseded by this final exact-source verification.

| Phase | Implemented ownership and remaining exit gate |
| --- | --- |
| S0 design | All baseline engine methods and writer hotspots inventoried; owner, dependency-direction, transaction and re-entry map in `docs/architecture.md` |
| S1 state | `SourceIdentity`, `LessonCursor`, `SessionNotices`, `AttemptRuntime`, `VisualTransport` and `SessionLifecycle` own current state and ordered cleanup. Final native acceptance outstanding |
| S2 source/history/device | `SourceWorkflows`, `HistoryManagement`, `DeviceWorkflows`, `SettingsWorkflows` and `PolicyRegistry` implement the supported source, data and device workflows; no separate server or policy instance |
| S3 lesson/exposure | `TeachingDecisions`, `ExposureWorkflows`, `ExposureInstaller`, `LessonExecution` and `LearningActions` apply one accepted generator decision |
| S4 transport/commands | `TransportTiming`, `TimedPlayback`, `TransportActions`, `PracticeControls`, `MidiApplicationInput` and `ApplicationWorker` use one admission coordinator and worker clock |
| S5 settlement/recovery | `PracticeTimeline`, `RecoveryWorkflows`, `PostAssessmentEffects` and `CompletionContinuations` consume the sole `AttemptSettlement` and configured grader. Same-tick follow-on is bounded, not recursive |
| S6 read/presentation | `SessionReadModels`, `ScoreReadServices`, `ScorePreloadWorkflow` and `LiveFeedbackWorkflows` separate queries and single-revision presentation from grading and admission |
| S7 facade and legacy | `PracticeEngine` contains 343 lines (12,131 bytes); `composition.py` wires owners without a facade backreference. 86 old unused imports, four unused owner ports, redundant command routing and nested Resume command invocation are removed. Full native/package and physical acceptance are outstanding |

**File-size diagnostic** (source files, excluding the non-runtime editor
MCP addon): `piano_teacher/learning_ledger.py` 45,611 bytes (733 lines);
`piano_teacher/notation/lesson.py` 43,054 bytes (860 lines);
`godot/settings_screen.gd` 36,961 bytes (722 lines).
They do not contain a second practice engine. The ledger is the one
durable evidence/schema/export/retention owner; the notation module is the
one MIDI-to-authentic-notation builder; Settings is a UI screen. Those
responsibilities are substantial, but splitting them solely by file size
would risk duplicate persisted data, notation or screen authority.
The remaining large core collaborators, `PlaybackSession` and
`AttemptSettlement`, retain the one playback and durable grade authority.

**Dependency and re-entry review:** 32 new/extracted application modules
were examined for `PracticeEngine` imports; none import the facade.
The production Godot main scene uses the single in-process native adapter.
`inprocess.py` is the intentional embedded import of `PracticeEngine`.
No HTTP/UDP runtime transport or second score/grade policy was identified
in those inspected paths. The grouped command actions now share one outer
RLock and one classification, restore command state even on failed
preparation, and Resume performs its deferred acknowledgement in the
existing transport transaction. A package import-closure check and
full native/embedded use cases remain necessary to close software S7.

### Target architecture — to validate and finalize in Phase S0

A proposed dependency direction, subject to evidence from the S0 inventory:

1. **Embedded entry/transport:** existing Godot and `EngineCommands` expose
   typed public operations and schedule command, musical-tick and asset work.
2. **Application boundary:** `PracticeEngine` supplies the stable public
   command/query surface, session transaction/lock boundary, composition and
   lifecycle cleanup. Read-only query execution cannot advance the workflow.
3. **Application use cases / workflow layer (new where justified):** explicit
   source/history, lesson/exposure, playback/command, attempt/outcome and
   projection operations coordinate several domain owners. Define narrow
   input/output facts and effect contracts; avoid passing the whole engine.
4. **Domain state and policies:** the authoritative selection, source,
   playback, assessment, progression and evidence owners make their own
   decisions. A coordinator applies a decision; it does not independently
   choose tempo, stage, grade or deadline.
5. **Ports and infrastructure:** persistence, MIDI, audio, engraving,
   workers and clocks are reached through explicit, replaceable interfaces
   where a real dependency seam needs one. Do not create ports solely to
   satisfy a pattern. Strict musical-tick, asset-worker and native-thread
   boundaries remain enforced.

Allow new boundaries such as a session-transaction service, a workflow
executor, a domain event/effect dispatcher or immutable session snapshot
where justified by ownership and lifecycle. Reject cyclic dependencies,
indirect `PracticeEngine` backreferences, global service locators, a
universal mutable `EngineContext`, duplicated transport/grading clocks,
shadow selection state and transitional alternate runtime paths. Cross-layer
events/effects must declare identity, generation and ordering when relevant.

### Implementation record — session state ownership (in progress)

The first production migration gives installed source identity/revision,
selected lesson opening/course-guided state, and learner-facing notices
independent storage owners (`SourceIdentity`, `LessonCursor`,
`SessionNotices`). `AttemptRuntime` now owns the active remedial assignment
and clears it on stop. `PracticeEngine` exposes read-only observations and
keeps existing public feedback setters while remaining command/transaction
entry. All source revision writes, opening selection writes, course-guided
writes and remedial assignment writes now target their respective owners.
The selected LearningPlan now lives beside its source identity, instead of
having a second mutable engine field. The visual transport owns the
remaining continuation scheduling metadata (announced start, physical rest,
post-take rest, horizon, next boundary); SessionCommands owns the current
action reason. S1 still requires a complete semantic-writer/transaction
audit before its exit gate can be declared. The first state-owner commit
`f01e2960` passed
[core CI 44900868358](https://github.com/tpepels/piano_teacher/actions/runs/44900868358).
This follow-up must pass CI separately; native production and physical
acceptance have not been rerun on it.

The active stop transaction has now been moved to
`application/session_lifecycle.py` with individually injected lifecycle
owners, not an Engine reference. The facade retains a short private command
entry for its 22 callers. This is an S4 foundation, not completion of S4;
public command handling and transport execution remain to be extracted.

### Phase S0 — Full responsibility and dependency design

- Inventory **all 168 methods**, engine fields and assignment sites; map
  callers, public native operations, read-only queries, update/tick paths,
  import/deferred-import edges and state transitions. Include the large
  neighboring `application/` modules rather than assuming their current
  responsibilities are correct.
- Trace the high-fanout paths: `_stop` (22 callers), `feedback` (45
  writes), `next_action` (34 writes), `open_from_beat` (16 writes),
  `course_guided` (13 writes) and `score_revision` (11 writes).
  Determine authoritative, derived, transient and duplicated state.
- Specify a concrete target module/dependency graph, command/query and
  worker boundaries, atomic transaction model, state owners, public
  compatibility surface, proposed interface types and migration order.
  Use new layers where they solve demonstrated coupling.
- Record current exact file/method sizes and software gates; preserve a
  full baseline inventory for no-legacy audit.

**Exit gate:** Every method and mutable fact has an intended destination;
each cross-owner operation has a stated authority and transaction boundary.
The proposed graph is documented in `docs/architecture.md`, with explicit
reasons for significant new/replaced abstractions. No implementation is
declared complete in S0.

**S0 evidence:** The complete current method/line mapping, target
responsibility groups, owner matrix and command/settlement re-entry
components are recorded under
[the S0 inventory](docs/architecture.md#s0-responsibility-inventory--implementation-baseline-2026-11-21).
This is a design inventory, not a statement that subsequent refactoring
is complete.

**S1 last direct-writer cleanup (2026-11-21):** All remaining
cross-service assignments to VisualTransport's rest, next-boundary,
runway and scheduled-strip fields have been migrated to owner methods:
`bind_scheduled_start`, `clear_scheduled_start`,
`record_take_end`, `clear_take_end`, `advance_boundary`,
`report_rest_geometry` and `configure_reading_horizon`.
The owner enforces the existing native clearance/horizon validation;
transport/assessment/application services consume the accepted facts.
No source identities, deadlines, native rendering or grading authorities
were changed. Core and production/relocated package verification must
confirm this complete caller migration.

**S1 command-context ownership completion:** Both public action
transactions and Resume's internal score-ready acknowledgment now use
`SessionCommands.reason(...)`, a single owner-managed context manager
that restores the outer command reason even on exceptions. The application
services no longer assign directly to that state. This removes the last
independent reason-writer/restore pattern without adding another command
router. Core and full embedded/native/package acceptance are required.

**S1 further owner-source audit:** `PlaybackSession` still directly
cleared three `AttemptRuntime` review flags, assigned its Recorder on a
failed capture start and wrote `VisualTransport.pending_rewind`.
Those remaining mutations now use `AttemptRuntime.begin_timed_review()`,
the existing `suspend_recording()`, and
`VisualTransport.finish_rewind()`. The caller's existing order and
exception handling remain intact. No other direct
`self._attempt`/`self._transport` field writers remain in
`PlaybackSession`. Integrated native/package verification must rerun.

### Phase S1 — State authority and transactional foundations

- Establish explicit ownership and semantic updates for `feedback`,
  `next_action`, selection/window position, source generation/revision,
  guided state, pending preparation, recovery and transport deadlines.
  Remove redundant stored fields when a read-only derivation suffices.
- Introduce narrowly scoped transaction/effect and state-snapshot boundaries
  if the audit shows they are needed. Preserve the existing lock, durable
  savepoints, command/tick ordering, cancellation and failure recovery.
- Convert all relevant writers/callers **in the same integrated phase**.
  Do not leave duplicate mutable fields or temporary bidirectional shims.

**Exit gate:** One writer/decision authority per state fact, explicit
cross-owner operations, no engine-wide mutable dependency bag; all existing
affected behaviours and core CI pass.

**S2 implementation underway:** Durable learner-history status, statistics,
export, scoped deletion, full deletion and current-lesson reset are now
centralized in `HistoryManagement`. It has explicit dependencies and uses
the same lifecycle, settled evidence and plan identity owners; no second
LearningPlan store is introduced. MIDI loading, validated installation, fingering correction and library
listing/open/health now execute through `SourceWorkflows`, with the
source-mutation guard and application lock retained around installation.
`PracticeEngine.load` composes the atomic installation with course entry;
the source service receives no engine backreference. Settings validation, persistence, assessment/diagnosis policy replacement,
evidence-retention controls and exercise diagnostics now use
`SettingsWorkflows` and a single `PolicyRegistry` that every other
consumer resolves dynamically. MIDI connection loss, preferred restoration, selection and calibration now
run through `DeviceWorkflows`, which returns settings effects for the
existing ordered settings transaction. The boundary retains the lock and
the teaching-interruption precondition. The final shutdown ordering now belongs to `SessionLifecycle.shutdown`.
The S2 operations are extracted; S2 remains **in verification** until
core CI confirms all source, device, settings, history and shutdown paths.
The public application boundary still applies the lock and source/course
installation effects. Verify this
commit in core CI before accepting its source mutation paths.

### Phase S2 — Source, device, configuration and history workflows

- Move the full implementations of source loading/install and source
  revision invalidation, library loading/health, fingering correction,
  preferences, device connection/disconnect/calibration, learning-history
  status/statistics/export/delete, and persistence restore/save.
- Evaluate and reorganize existing `SourcePreparationSession`,
  `MidiConnection`, `LearningEvidenceSession`, repositories and ports.
  Create a source-lifecycle use case/boundary when it is cleaner than
  fragmented direct calls; do not automatically preserve existing shapes.
- Handle in-flight stale source installs, affected take cancellation,
  worker/read-only snapshots, user data migrations and error propagation.

**Exit gate:** No device/source/history workflows implemented inside the
facade; native operations and persistence behaviour remain compatible;
cancellation and exact source generation are intact; required CI passes.

**S3 implementation underway:** `TeachingDecisions` now builds the one
source-bound `TeachingEvent`/`TeachingState`, routes manual commands through
the configured lesson generator and applies the accepted decision. It
resolves the current policy instance, not a cached pre-settings copy, and
owns no grading or transport clock. Guided/timed/Listen source creation is now in `ExposureWorkflows`; the
ordered state/persistence effects of an accepted preparation belong to
`ExposureInstaller`. `SessionEvidenceContext` builds the exact source,
transport and learning capture facts without entering a second clock.
The source-bound lesson execution, guided completion, course entry, manual
navigation, lesson review and seek are now in `LessonExecution`, with all
23 identified methods moved and the facade retaining the public display
phrase method. The initial commit `7ec9b0a4` failed core CI (56 failures) because two
snapshot read ports still held removed engine method references. The
`SnapshotReadPorts` bindings now resolve the migrated
`LessonExecution.seek_grid` and `learner_snapshot` operations.
S3 still needs a passing core CI run and remaining command-dispatch
course transitions before completion.

### Phase S3 — Lesson selection and exposure workflow

- Extract the complete `_flow_*`, `_begin_learn`,
  `_enter_selected_exposure`, `_apply_exposure_preparation`,
  `_prepare_practice`, `_prepare_listen`, `_prepare_teaching`,
  `_commit_pending`, stage navigation and guided-return workflows.
- Separate *selection* from *execution*. Preserve the one authoritative
  generator/lesson decision, `SessionCommands`, the exposure source,
  Practice Flow windows and alternatives including Coda/Fukuda.
- Permit a new lesson workflow/application layer; remove duplicate
  decision branches and obsolete access paths instead of routing them
  through a second class.

**Exit gate:** Listen → Free → Tempo, each authored measure and its
backward-growing four-bar windows, Right/Left/Together, resumes, return aids,
alternate courses and full-original examination follow a single
selection/execution contract with passing existing behaviour CI.

**S4 implementation underway:** `TransportTiming` now owns the source
tempo-map cache read, authored elapsed conversion, count-in, exact
source-bound playback facts, continuation/rest clearance, presentation
lead and musical-seconds projections. It retains the existing
PlaybackCoordinator/PlaybackSession/VisualTransport authority. Authorized timed starts, exact continuation scheduling, Listen readiness
and Pause/Resume execution now use `TimedPlayback`. The engine's
public `start` entry remains, and the sole deferred score-ready command
is issued by the application boundary after Resume completes; the
PlaybackSession service never calls an engine method. Control dispatch,
automatic outcomes and tick processing still require extraction;
S4 is **not complete**. The migration must pass core and native CI.

### Phase S4 — Command dispatch and authorized playback

- Extract public `start`/`control`, command classification, musical
  ticks, `_control_transport`, `_start_or_restart`, Pause/Resume/Retry,
  count-in, fixed-deadline repeat, automatic continuation, MIDI shortcuts,
  scheduling/rest measurements and `_stop` orchestration.
- Design an explicit command/use-case execution boundary (new permitted);
  reassess `PlaybackSession`, `PlaybackCoordinator`,
  `VisualTransport` and scheduler responsibilities rather than simply
  moving every method into `PlaybackSession`.
- Preserve exact graphical reserve → present authorization, single
  admission/take identity, immutable ink, source-bound audio/MIDI timing,
  frozen pause time and score, count-in, and forward continuous scroll while
  unpaused. No cold asset
  compilation or blocking worker action inside a musical tick.

**Exit gate:** Every timed route uses the same authorized transaction,
including Listen, stage handoff, Retry, resume and shortcut; rejected/stale
receipts do not grade or sound. Core, native behaviour, embedded runtime and
relevant package checks pass on the integrated phase.

**S5 implementation underway:** Accepted, durable full-passage publication
and its exact stage/asset effects now use `PostAssessmentEffects`.
Performance-review construction, section review and partial-recovery
return effects also moved. The original `AttemptSettlement` remains
the sole assessment commit authority. Registered source-bound recovery preparation, remedial assignment,
mid-take recovery execution and recorded boundary assessment now use
`RecoveryWorkflows`. The policy still chooses every recovery and
`AttemptSettlement` retains the exact evidence transaction. The sealed feedback transition now runs through
`CompletionContinuations`, which commits the single pending receipt and
dispatches the selected exposure/response/remediation/automatic passage.
The locked worker transitions, complete-take result routing,
full-passage progress effects and non-grading course events now
execute in `PracticeTimeline`. It orchestrates the single existing
clock, assessment and selection owners. Command dispatch and the
bounded tick re-entry review remain; S4/S5 are **not complete**.
The new workflow requires core and native CI. The integrated software checks remain mandatory.
This code requires full core/native verification.

### Phase S5 — Attempt result, recovery and durable continuation

- Extract `_complete_attempt`, `_apply_rolling_recovery`,
  `_assess_rolling_boundary`, `_advance_pending_feedback`,
  `_run_pre_assessment_transition`, `_finish_*`, remedial
  assignments and continuation-effect execution.
- Reassess `AttemptRuntime`, `AttemptSettlement`,
  `AssessmentService`, `AttemptProgression` and
  `TeachingContinuation`. Use a new outcome workflow/transaction
  boundary if needed, while keeping one grader and one durable result.
- Preserve original completed-take BPM, sealed evidence, atomic generator
  feedback/progress save, retry idempotence, interrupted-take handling,
  source-bound note feedback and full-tail release timing.

**Exit gate:** No double mastery, duplicate settlement, second grading
policy, incompatible retry or retroactive ink mutation. Existing recovery,
long-note, rolling-window, alternate-course and failure/retry behaviours pass,
plus native and package verification.

**CI correction:** The first S6 preload extraction CI on `02b39c81`
failed at collection because `PreloadedFeedbackSource` was imported
from `teaching_continuation` instead of its actual
`application/playback_facts.py` owner. Corrected in the following
commit; full CI still required.

**S6 implementation underway:** `ScoreReadServices` now owns current
source-bound score selection, native geometry/engraving, guided marks,
completed-take cached-layout lookup and lesson overview. Score source
selection and asset compilation are separate; the original public commands
remain intact. The source/transport state snapshot, score projection and explicit headless
fixture serialization now use `SessionReadModels`. The facade continues
to own public read timing, while named read ports provide the immutable
projection dependencies. Source/take-bound live grading, its single provisional/final publication
channel and the current feedback event identity now use
`LiveFeedbackWorkflows`. The former engine methods and duplicate
snapshot marks port were removed; the existing `AssessmentService`
and `LiveAssessmentPublisher` remain the only grader/publisher.
Preloaded stage selection, exact revision acknowledgment, native
preload failure and subsequent automatic score preparation now use
`ScorePreloadWorkflow`, consuming `TeachingContinuation` decisions.
Remaining S6 integration is read-only snapshot/feedback ownership
verification and removal of obsolete facade read delegates; core/native
CI must confirm.

### Phase S6 — Read models, feedback and score projection

- Extract `_state_snapshot`, `_capture_session_snapshot`,
  `_score_projection_facts`, feedback/readiness projections, live
  assessment and preload acknowledgement. Read-side code consumes stable
  domain facts and never writes transition state.
- Reassess and, where helpful, restructure `SessionSnapshotBuilder`,
  `ScoreStatePublisher`, `LiveAssessmentPublisher`,
  `ScoreArtifacts` and their interface ports.
- Retain the non-graphical `headless_score_projection` only for explicitly
  headless fixtures; desktop must use real native admission and revision
  identities. Cold engraving remains outside the locked musical worker.

**Exit gate:** Queries are side-effect-free; projected generation,
source-note identity and authorized playback match; pending feedback is
acknowledged exactly once; core, Godot/native and packaged read paths pass.

**S7 composition preparation:** The last facade-bound phase projection
is now in `SessionPhase`. TimedPlayback and SessionReadModels receive
that same pure projection instead of a method callback into
`PracticeEngine`. This allows a new factory/composition root to
construct the whole graph without an engine backreference. Core/native
verification and final composer migration remain.

**S7 composition extraction:** The application graph now assembles in
`application/composition.py`; the facade constructor is a short invocation.
The private temporary composition namespace is *not* passed to any service,
which continues receiving explicit named owner dependencies. This removes
the 340-line wiring responsibility from `server.py`. Public native
entry points and live state remain the same. The native-worker entry now uses
`ApplicationWorker` and carries delayed MIDI under the original lock
without another clock or thread. The read-model composition callback
uses the bound TransportTiming method rather than closing over the
temporary wiring namespace. The remaining unreferenced private
forwarding methods (16 delegates) and the unused remediation shim are
removed from the facade. Its imports now reflect only the public boundary,
with module dependencies owned by the separate composition root.
Remaining S7 tasks: dependency-cycle/re-entry audit and full native/package
acceptance on the completed source. No size-only completion claim.

**CI correction:** The first composition run `504ccc13` failed
because the application-local imports still used parent paths. The follow-up
`10d04a5d` fixed those paths and extracted the native worker, but
core CI then exposed a missing `ApplicationWorker` import in the
composition file. The import is now explicit. No tests or alternate
runtime were introduced.

**S7 re-entry correction:** `PracticeTimeline` no longer recursively
re-enters its own musical worker tick during preview/retry or
full-completion handoff. An explicit bounded same-tick transition drain
preserves the previous deepest-first publication count without
creating another clock/worker; pathological handoff loops fail
explicitly. The existing player-behaviour suite and embedded native
acceptance must verify this change.

**S7 dependency cleanup (2026-11-21):** The composition root's
swept-over imports from the old monolithic engine have been reduced to
symbols actually used for wiring. Old comments about state fields that
were already moved were deleted. The `PracticeControls`,
`PracticeTimeline`, `TransportTiming` and `SourceWorkflows`
constructors no longer request unused dependencies, and the composition
call sites no longer provide them. Core CI on `ce6dd8d5` passed; this
change requires its own core and opt-in native-production verification.
Removing these ports does not by itself close the S7 dependency-cycle,
hardware or clean-target-machine acceptance gates.

**S7 command-cohesion and re-entry correction (2026-11-21):**
`PracticeControls` now handles the single command transaction, provenance
capture and typed routing. Lesson/navigation effects live in
`LearningActions`, and authorized playback, transport and score-ready
acknowledgments live in `TransportActions`. The previous Resume path
re-entered `control("score_ready")` inside its own command/receipt
transaction; it now applies the exact infrastructure acknowledgment
directly, with the prior action reason restored in `finally`. No new
grading clock, source decision or admission gate is introduced.
These changes require core and full native/package verification.

**S7 lock/route cleanup:** The private action dispatcher now consumes
the validated route within the command's existing lock and does not
re-enter the RLock or classify the same action twice. The outer command
transaction remains the only owner of failure-safe action-reason cleanup.

**S7 command transaction hardening:** `PracticeControls.control` now
restores `SessionCommands.action_reason` even if route validation or
teaching-decision preparation raises before dispatch. Lesson-stage commands
reuse the generator's accepted `StageChange` from their active command
effect rather than silently preparing a second stage change, and ignore
mismatched active command effects. An unused guided-start local is removed.
Existing command, failure and persistence journeys must confirm these changes.

**S7 complete runtime dependency scan (2026-11-21):**
All **193 production Python modules** were checked for obsolete server,
HTTP/socket, parallel renderer, headless-fixture and MusicXML source
indicators, and all **146 production Godot scripts** (excluding the
dev-only MCP addon) were scanned for the same obsolete native/transport
patterns. The only relevant matches are the intentional
`inprocess.py` import of the public facade, the explicit headless
`score_queue_next` schema (not desktop admission), internal
MusicXML/research expression handling and historical-data coverage
labels/comments. No unintended alternative active runtime route was
identified in this scan. The project config has no developer MCP autoload,
and packaging removes the editor-only addon. This is a targeted source
pattern and import audit, not proof against arbitrary dynamic behavior.
Core and native/package gates passed at `daf466e6`.

**S7 comprehensive application direct-writer audit (2026-11-21):**
All **77** current `piano_teacher/application/*.py` production modules
were inspected for cross-owner direct writes to the visual transport,
attempt, settlement, playback, selected source/lesson and scored MIDI
state (including private `_attempt` / `_transport` references).
The last actual offenders were repaired in `9df6a1ae`,
`0a688d5b` and `daf466e6`; the final 77-module scan found zero
remaining direct assignments matching those owner-write patterns.
This covers explicit Python attribute assignments, not arbitrary
dynamic introspection or physically observed graphics. On
`daf466e6` core CI passed; the complete native/embedded/repertoire
and relocated-package software gate is being verified separately.
No new tests or alternate renderer or source policy were introduced.

### Phase S7 — Final facade, dependency and legacy elimination

- Reduce `PracticeEngine` to justified composition, transaction/public
  entry, clock/worker dispatch and cleanup. Eliminate unnecessary facade
  delegates; retain direct ports only when that is the clean public seam.
- Remove every superseded implementation, old state copy, compatibility
  shim, unused module and caller; audit Python and Godot import/reference
  closure and native/package entry points. Preserve *necessary historical
  persisted-data migrations and explicit headless test fixtures*.
- Check all new/existing services for cohesion, methods/LOC, cycles,
  hidden policy duplication and excessive dependency fanout. Split or
  redesign oversized collaborators as required; do not merely relocate
  the monolith. Update `docs/architecture.md` from the final code.
- Run the entire existing core CI, native behaviour groups, embedded
  production/repertoire journeys and strict relocated package boot on the
  final source. Record SHA, counts, failures, skips and the largest files.
  A real piano and a clean target machine are separate unverified gates
  until the owner actually performs those observations.

**Exit gate:** Every public command/query route and worker path is
accounted for, the dependency graph has no production cycles or accidental
second authorities, no required old architecture remains, and full
software acceptance passes. A ~300–450-line facade is desirable, not
evidence of architectural correctness by itself.

### Implementation discipline and phase reporting

A phase is finished **only** when all its scope is implemented, every affected
caller and documentation reference is migrated, obsolete paths are removed,
and its specified integration/CI checks pass. Phase entries must record
source SHA, module/ownership changes, measured file sizes, observed tests,
failures/skips and any genuine unverified acceptance. Work on `main` with
coherent commits; no branches or worktrees. Do not add architecture-shape,
pixel, parity or infrastructure tests; use the current player-visible
behaviour suite and the existing native/packaging acceptance scripts.
New regression tests require the owner's separately stated approval.
Physical MIDI, audible output and visual acceptance are never inferred
from headless or Dummy-audio CI.

## Post-S7 persistence boundary — learning evidence (2026-11-21)

Source commit [`8eccd16e`](https://github.com/tpepels/piano_teacher/commit/8eccd16eb1b5ea7fa80ef43b56e7fe955925013e)
separates the previously 733-line `LearningLedger` into an explicit
414-line transactional evidence owner, shared canonical JSON/privacy encoding,
SQLite schema/accounting trigger setup, independent detail-budget retention,
and atomic/redacted export. The ledger composes these connection-scoped owners
on the **same** SQLite connection: nested `sqlite_atomic` savepoints,
crash recovery, legacy data import, replay identities, the public history
API and the single authoritative source of assessments remain unchanged.
No architecture-only, pixel, infrastructure or new regression tests were added.

[Core CI run 44908940976](https://github.com/tpepels/piano_teacher/actions/runs/44908940976)
on the source commit passed **103 Python tests, four skips**, Godot startup
parsing, and four existing native behaviour groups with zero failures.
The opt-in embedded native/repertoire/standalone-package gate is separately
running on that same source revision; it must pass before this follow-up is
claimed fully software accepted. Physical MIDI/audio, visual inspection and
installation on another clean target machine are not covered by CI.

Current three largest production source files by bytes after extraction:
`notation/lesson.py` (43,054), `godot/settings_screen.gd` (36,961), and
`godot/practice_screen.gd` (34,101). These remain diagnostic review targets;
size alone does not authorize moving their responsibilities.

### Native visual-effect runtime exception and gate correction

Inspection of the nominally successful full native runs found **239** Godot
`SCRIPT ERROR` lines in [run 44907200749](https://github.com/tpepels/piano_teacher/actions/runs/44907200749)
and **229** in [run 44908940976](https://github.com/tpepels/piano_teacher/actions/runs/44908940976).
All were an invalid access to `PracticeScoreStage.impact_callout` from
`score_effects.gd:19`: the deleted callout was still referenced whenever
ungraded Listen/preview mode was accepted. The processes returned zero and the
old runner incorrectly marked those player journeys passed. Those green jobs
are **not clean native UI acceptance evidence** for that error path.

Source commit [`03de4498`](https://github.com/tpepels/piano_teacher/commit/03de44984438700ca70a38fe517121b487ab331c)
removes the obsolete access. The same existing native acceptance script now
fails each actual Godot journey if its log includes `SCRIPT ERROR:`, even when
the process exits zero; independent cases still run and are reported. No new
test scenarios were added. [The corrected full gate](https://github.com/tpepels/piano_teacher/actions/runs/44909630866)
was started on that source; a final green outcome with zero script exceptions
is required before closing this correction. Physical rendering and MIDI/audio
acceptance remain unverified.

## Pause and current-window display correction — 2026-11-21

Following physical-use feedback that Pause did not stop the moving staff,
that Free continued scrolling without tempo, and that extra measures appeared,
the renderer/control paths were corrected on main:

- [`d1ba66e5`](https://github.com/tpepels/piano_teacher/commit/d1ba66e5fee8e2c941f5b465d60a5952642ced4a)
  freezes the canonical visual projection on an acknowledged Pause, aligns the
  visible Play/Pause decision with backend-pausable phases, and clips each
  admitted score strip to the **selected** authored window. Context remains
  available to the pre-engraving source but not as additional visible bars.
- [`098ff955`](https://github.com/tpepels/piano_teacher/commit/098ff95519695a5227f682f59501d5f09ca4b7ac)
  also maintains the Free target hold throughout `introducing`,
  `disconnected` and completion transitions; these untimed phases can be
  paused through the same backend transport authority.

- [`9eec8103`](https://github.com/tpepels/piano_teacher/commit/9eec8103842a21df927950f5d0592649743365cf)
  gives the Python Free teaching controller the same Pause/Resume lifetime
  in `guided_wait`, `introducing` and `disconnected`; device changes cannot
  silently unpause a frozen controller.
- [`fc65791f`](https://github.com/tpepels/piano_teacher/commit/fc65791f5d6750cfc42c29cb3e2ce787213d42b1)
  prevents neighboring context-role notes and headers from being painted in
  native selected-window strips even when engraving margins overlap them.
- [`b37e7693`](https://github.com/tpepels/piano_teacher/commit/b37e7693076ef4e8059458465d353be5c0559ae6)
  retains the selected window's authentic closing barline (including authored
  repeat styles) without showing the following measure.

**Native acceptance and Resume correction.** The first full run,
[44922019745](https://github.com/tpepels/piano_teacher/actions/runs/44922019745),
failed four scenes because two existing acceptance scripts still expected the
previous moving-during-Pause behavior. The scripts now assert a stationary
score and no new admission during Pause ([`1948651a`](https://github.com/tpepels/piano_teacher/commit/1948651ac82c3d536b2e723d2749f41914b1c17b)).
The following full run,
[44922940896](https://github.com/tpepels/piano_teacher/actions/runs/44922940896),
exposed a **real Resume deadlock**: the backend remained in `admitting`
after Pause with no graphical receipt. Source `ae20d6c4` reconciles the
canonical hold in every presentation frame rather than only at a snapshot.
Source [`81ae006f`](https://github.com/tpepels/piano_teacher/commit/81ae006ff186ce9a6bce39f0293b0d2510390e40)
releases the visual hold when an explicitly pending Resume intent is being
admitted. The backend intentionally retains `paused=true` until authorization;
holding the visual world throughout that admission made the deadline inversion
unable to reach any future source. No separate clock or alternative admission
path was added. Existing acceptance failure witnesses were extended in
`9312b83c` (no new test scenarios).

**Final source acceptance:** [GitHub Actions 44925026112](https://github.com/tpepels/piano_teacher/actions/runs/44925026112)
passed on source `81ae006f`: **103 Python passed, 4 skipped**,
Godot startup and all four existing native behavior groups passed with zero
failures, embedded CPython/native registration succeeded, production
Play/Pause/Resume succeeded, Moonlight/Peace Piece/Chopin journeys succeeded,
strict relocated standalone package contents and boot succeeded, and there
were **zero Godot script errors**. No new tests were added; two preexisting
production scripts were updated to the current Pause contract.

A real piano is still needed to verify immediate Pause/Resume feel, whether
Free remains stationary while thinking, and that source cropping shows exactly
the selected window on screen. No physical, audible or visual success is claimed.

## Physical MIDI session incident — 2026-11-21

The player's Arch Linux / Godot 4.7.2 session on source `9312b83c`
(pre-`81ae006f`) opened Beethoven's *Pathétique* II with a connected piano.
The supplied runtime log contains **10** graded-MIDI `SCRIPT ERROR` exceptions
caused by the removed `PracticeScoreStage.impact_callout` property, and **78**
refused immutable score admissions paired with **78** preflighted
`SCORE_TRANSPORT_COMMIT` failures on an automatic exact repeat. This is a
real production failure despite green automated CI on other music.

Corrective commits on `main`:

- `fc299322`: remove the removed `impact_callout` call from
  `LiveMidiFeedback`; retain `effects.react` and ledger-owned ink.
- `5b6fb3b3`: read printed rest/header geometry from the matching ready
  renderer and forward it in `score_ready`, Play, Retry and Resume commands;
  Python installs it before automatic future deadlines are selected.
- `907f29ad`: make fixed-repeat preflight account for physical printed
  rests and use the existing safe announced-empty-strip policy; committed
  notation and the backend deadline remain immutable.
- `3b3b5a25`, `73adfb7e`: report the actual queue refusal and source
  coordinates; correct the diagnostic's initial Godot syntax error.
- `87a41370`: correct an obsolete assertion in the **existing**
  score-stream checks that allowed an overlap with committed rest ink.
- `584f017a`: fail the **existing** full-native positive journeys on
  score-queue/preflight/commit runtime errors even if Godot exits zero.

No new tests or fixtures. **Full [GitHub Actions run 44927279888](https://github.com/tpepels/piano_teacher/actions/runs/44927279888)
passed on source `584f017a`**: 103 Python tests passed, four optional
skips; Godot startup syntax and all four existing native behavior groups
reported zero failures. Embedded Godot/Python registration, production
Play/Pause/Resume, Moonlight Sonata Retry/Listen/navigation, Peace Piece,
Chopin Nocturne, and relocated standalone package boot/contents all passed.
The stricter positive-journey gate reported no rejected immutable source
admissions or Godot script exceptions. Documentation commit `9877ea93`
also passed its core CI gate. **The actual physical Pathétique MIDI session,
sound and visual layout have not yet been re-tested; green software CI
does not establish those outcomes.**

## Phase status and remaining acceptance

### Historical architecture re-audit — pre-correction log

The statements of remaining A1–A6 implementation below describe intermediate
commits; they do not supersede the latest dependency audit above.

Remediation execution: A1 now validates authored and sounding bounds from the
existing semantic source contract. Targeted Python and all native checks pass;
the direct gateway diagnostic accepts a full held ending and rejects different
prepared coverage (`96c895e7`). A2 now preserves bound crops and committed
horizontal spacing on resize; targeted Python/native checks and the existing
controller journey with a resize diagnostic pass. A3–A6 and obsolete-port
cleanup remain open. Physical resize acceptance remains unverified.
A3 lifecycle transfers now pass all 107 Python behaviour checks (one optional
system-SF2 skip); remaining work is A4–A6 and obsolete internal ports.
A4 now removes transition execution and guided-deadline scheduling from reads.
Full local CI passes (107 Python, one optional skip; native/parser pass).
The remaining implementation is A5/A6 and obsolete internal ports.
A5 now removes the deferred runtime cycles and private source-index coupling;
all 107 Python checks pass, and the one-off runtime import scan is acyclic.
Remaining implementation: A6/private requests and obsolete native ports.
A6 and obsolete native ports are implemented; all six source-audit items now
have code changes. Full local core CI passes, with 69.6% Python line and 49.4%
branch coverage. Integrated review and full embedded/package verification are
pending; physical acceptance remains unverified.

Implementation audited at `640a77f5`. The prior Phase 5 completion assessment
was too broad and is reopened. The [active audit](docs/architecture.md#remaining-work--source-audit-2026-11-20)
records six concrete remaining items, priorities and intended owners:

1. A1: authored-versus-sounding endpoint disagreement can refuse desktop
   admission for a cross-bar held note. Actual existing MIDI/public-command
   diagnostic publishes 4 versus 6 beats; the inspected Godot guard rejects it.
2. A2: viewport resizing can rewrite a retained node's source crop outside its
   admitted immutable stream binding. Source mutation path confirmed; physical
   appearance has not been observed in this audit.
3. A3: remaining Engine/PlaybackSession writes bypass transport, attempt and
   guided lifecycle owners; finish those transfers through semantic operations.
4. A4: snapshot reads still call the mutating transition loop alongside the
   existing worker; remove the compatibility advancement path.
5. A5: deferred statistics, tuplet and course/generator cycles and the private
   alternate-curriculum source-index dependency remain.
6. A6: admission/preloader callers still inspect private request IDs. Also
   remove unused internal mutation facades after checking supported API usage.

No production code or tests were changed for this audit. No new test run,
remote CI result, graphical reproduction or hardware acceptance is claimed.
The existing source/method review and recorded public-command diagnostic are
the evidence. The earlier software gates remain historical scenario evidence.

### Production rerun and correction record

At `75ae738e`, the full embedded workflow passed native registration and the
strict relocated standalone build/clean-HOME boot, but failed four real-scene
checks: stale preparation overlay, missing Retry leading rest, and incomplete
Peace Piece/Chopin context chord atlases. These were actual implementation
failures; their acceptance checks were retained.

The asset correction compiles every authentic atlas from the same complete
notation model before bounded display projection. Source/active IDs and one
renderer are preserved; incomplete cached atlases are invalidated. Retained
command-buffer generations now republish readiness after admission-time crops,
so readiness cannot precede its matching status notification. The five existing
asset-session scenarios pass, the exact Peace/Chopin native assets compile,
and the actual production Play/Pause/Resume journey passes.

At that pre-rebuild source, the Python suite passed **335 tests, one optional audio dependency
skip**. Final native checks and the complete production/package rerun pass.
The first failed run is retained in
`debug-sessions/practice-completion/embedded-production.log`; acceptance below
uses the subsequent complete rerun rather than focused diagnostics alone.

Asset/readiness source commit: `546bdaca`. Retry now creates its complete
leading rest in the same admitted source batch and owner when no full
predecessor rest survives. Stable before/source/after slot identities preserve
FIFO order, archive replay and rollback; a provisional prefix remains hidden
until authorization. The unchanged actual Moonlight journey passes Retry,
count-in state and cue delivery with Dummy audio, Listen, navigation, tempo
changes and saved reopening
(`debug-sessions/practice-completion/retry-fixed-reproduction.log`).

Retry source commit: `242d71ae`. Final review also corrected second Pause
during a Resume reading lead, accepted early first attacks and signed ghost
coordinates. MidiIngress alone applies the temporal gate; Recorder preserves
the accepted timestamp. Backend-selected `release_advisory` keeps accepted flow
notes green while retaining complete measured release dimensions. Native
ghosts use the existing physical strip/header bounds. Existing Python remains
335 passed/one optional skip; the complete final Godot script passes with all
failure counters zero and `GODOT_STARTUP_SYNTAX_OK`. No new tests were added.

Feedback/clock source commit: `ee6ccbf3`. Its complete production run passed
the fixture, native registration, Moonlight journey and strict relocated package
build/boot, but Peace Piece and Chopin exposed a Resume withdrawal of an
unexpired paused source strip. Resume now protects the first retained paused
strip while allowing later unseen measures to withdraw; preview and actual
withdrawal use the same queue policy. Its new admitted copy explicitly retains
the paused transport predecessor without changing existing geometry or keys.
Both unchanged repertoire journeys now pass in
`debug-sessions/practice-completion/resume-fixed-reproduction.log`; the complete
native script also passes with zero scenario failures in
`debug-sessions/practice-completion/godot-resume-final.log`.

Resume source commit: `bc957d37`. The final full production workflow exits zero
and passes every case on that committed source, including the unchanged Peace
Piece/Chopin Resume checks and actual relocated standalone package build/boot
under a clean HOME and cleared environment. Log:
`debug-sessions/practice-completion/embedded-production-accepted.log`.
The same run passes the architecture audit for checkout and packaged source.
That run predates the CI rebuild and manual final-Learn correction recorded
above; it remains historical evidence for that source.

| Phase | State |
| --- | --- |
| Phase 5 — ownership decomposition | A1–A6 implemented. Later commits `be98b159`, `c8808e2b`, `5f685890`, `a4525f0c`, `d7ee11d8`, `0608b3fb`, `acf40e7f` and `23dd5649` remove old score-identity, rolling recovery, state-loop, XML import, music21 and duplicate score-object paths. Full source-era core/native/package acceptance passed on `23dd5649`; no second product renderer or scorer is retained. |
| Phase 6 — software and physical verification | Full core, embedded/native repertoire journeys and relocated standalone package boot passed on `23dd5649` ([run 44836313449](https://github.com/tpepels/piano_teacher/actions/runs/44836313449)). 103 Python tests passed, 4 skipped. Physical MIDI/audio, rendering and clean-machine acceptance remain open. |

Unverified acceptance: Kawai CA49 USB and Bluetooth MIDI, physical press/release
latency, speakers and audible count-in, real-performance grading, on-screen
scrolling/spacing/colour/ghost acceptance, reconnect and drift under real load,
and a clean-machine desktop package. Headless results do not certify these.

The owner should exercise Moonlight Sonata, Peace Piece, Chopin, moving windows,
Listen/Free/Tempo, count-in, Pause/Resume/Retry, automatic continuation, the aid
return and saved final examination using [the physical protocol](docs/development.md#verification-and-acceptance).

## Commands

```bash
./run.sh
bash scripts/test.sh
bash scripts/verify-embedded-production-local.sh
bash scripts/package-inprocess.sh
```
