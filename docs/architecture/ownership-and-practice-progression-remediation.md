# Ownership, lesson-window and large-file architectural audit

**Status:** Implementation underway on `main`. This file tracks actual code commits; unfinished items remain explicitly marked.  
**Source baseline:** [main at 9a01a9b7](https://github.com/tpepels/piano_teacher/tree/9a01a9b7d9434ae6a3ef7bc72fd6844222d718ef), 19 November 2026.  
**Scope:** Practice Flow, learning/assessment, playback and score admission, presentation timing, and the three largest first-party production source files.  
**Goal:** One authoritative owner for each domain decision; explicit typed boundaries; no independent recomputation of a decision downstream; preserve the continuous native score and all existing capabilities.

## Implementation progress

**Implementation branch:** `main`. **Tests:** No new tests will be written for this change. Existing checks may be run.

| Workstream | Status | Notes |
| --- | --- | --- |
| Moving-window curriculum / P01 | IMPLEMENTED IN SOURCE, UNVERIFIED AT PIANO | `practice_windows.py` is the single window policy; `practice_flow_course.py` generates n, n−1..n, n−2..n, n−3..n up to 4; per-window course/stage identities; final exam retained; CI and physical acceptance pending |
| Typed course outcomes / O02 | IMPLEMENTED IN PRODUCTION PATH | `TeachingDecision.flow_outcome` now carries `Outcome` directly through course/engine; string parser remains only as a read-only legacy diagnostic for existing tests, without production callers |
| Unified assessment verdict / O03 | IMPLEMENTED IN PRODUCTION PATH, CI PENDING | `AssessmentVerdict` is produced by teaching policy; progression and attempt settlement use the same policy-selected acceptance/trouble-resolution flags |
| Unified playback transitions / O01, O04 | IMPLEMENTED IN BACKEND, GODOT CUES PENDING | `PlaybackTransition` retains the exact manual effect through admission; `CountInPlan` is immutable and applied to every graphical timed take; Godot cue rendering still requires consolidation |
| Asset admission / O05, O08 | PRELOADER TIMING REMOVED; PORT MIGRATION IN PROGRESS | `ScoreRunway` acknowledges only compiled asset identity; backend no longer consumes clearance estimates; public asset/gateway readiness/status ports replace several private field reads |
| Deterministic presentation timeline / O06 | NOT STARTED | Single rate/position authority |
| Architecture docs / O07 | NOT STARTED | Retire conflicting contracts |
| Decompose server.py / L01 | NOT STARTED | Thin facade, authoritative domain owners |
| Decompose native/view.gd / L02 | NOT STARTED | Renderer must not own score-stream policy |
| Decompose main.gd / L03 | NOT STARTED | Composition root, typed event coordinators |
| Existing CI/native integration | IN PROGRESS | Existing tests passed at `ce510621b` before removal of preloader timing; a later run caught an obsolete `handoff_world` snapshot reference, removed at `95b1880`; subsequent CI pending. No tests added or edited |

**Current instruction supersedes the earlier recommended prefix ladder:** For each newly encountered bar `n`, practice `n` alone, then `n-1…n`, `n-2…n`, `n-3…n` (until bar 1), in that order. Every routine practice window is at most four authored bars wide. The distinct whole-piece final examination remains a deliberate exception.

### Implementation checkpoint A — source changes

- `2779dc0`: Added immutable authored source windows in [practice_windows.py](../../piano_teacher/practice_windows.py).
- `e01a289`: Changed Practice Flow exercises to the moving-window order, without adding notes or changing their source IDs.
- `24ffc13` and `62c4c2c`: Added source end to graphical playback intents and reservation receipt validation. The active course phrase already equals the PracticeWindow, so the existing notation and grading source selection use exactly that interval.
- `f5a6607`: Learner status now identifies `Measure n` or `Measures a–b`.
- `6260d29` and `9cdfdb6`: Bumped Practice Flow course version and migrated old phrase-position saves to first-bar source locations without awarding unearned mastery.
- `242a1c3`, `67451c3`, `c6f4621`, `c0d4fd6`, `b35ca0f`, `247504a`: Established a typed course outcome and an immutable policy-bound verdict, then wired those into teaching and durable trouble-resolution.
- `147811e`: Retained the old message-decoder API for existing diagnostic tests only; production flow no longer depends on it.

**Still incomplete:** Playback transition consolidation, count-in ownership, score preloader deadline removal, unified visual-time projection, public renderer/asset ports, decomposition of the three largest source files, documentation retirement, native/hardware verification.

### Implementation checkpoint B — single decisions and preloader timing

- `9ea92eb`, `b1d4efa`, `4a9cbc5`: Added immutable `PlaybackTransition` and `CountInPlan` values and made `SessionCommands` use one route planner.
- `ef38c2c`, `0131c59`, `4b0caed`: Count-in selection is now carried by the coordinator to `AttemptProgression`, including automatic repeats and Listen, with a single authored pulse layout.
- `989629f`, `ce51062`: Manual timed authorization executes the original selected `CommandEffect` rather than selecting a second command at commit; entering Free keeps the original guided exposure.
- `5fdd396`, `0b507ca`, `5756fd5`, `95b1880`: Removed preloader-supplied lead/clear estimates, backend handoff-world scheduling, and obsolete snapshot fields.
- `0296063`, `96178a1`, `a12c949`, `97afb24`: Exposed identity-bound readiness and reservation status ports so ScoreAdmissionGateway no longer inspects several foreign private fields.

**Still unfinished in the architecture:** The native view and presentation controller retain private mutable state; the Godot count-in consumer still has legacy timing paths; source/display timeline projections are not yet consolidated; the three largest production files have not been fully decomposed.

## Executive findings

| ID | Severity | Problem | Evidence |
| --- | --- | --- | --- |
| P01 | Critical product mismatch | Entering Tempo selects the whole 2–4-measure phrase rather than starting with measure 1 | [phrase generator](../../piano_teacher/practice_flow_course.py#L20-L105), [guided completion](../../piano_teacher/practice_flow_course.py#L125-L136), [start/scoring](../../piano_teacher/server.py#L1635-L1720) |
| O01 | High | Restart's route is decided by SessionCommands and interpreted again by separate engine paths | [session_commands.py](../../piano_teacher/application/session_commands.py#L38-L46), [server.py](../../piano_teacher/server.py#L2241-L2310), [server.py](../../piano_teacher/server.py#L2332-L2420) |
| O02 | High | Course progression is derived from human-readable message text | [practice_flow.py](../../piano_teacher/application/practice_flow.py#L145-L162), [server.py](../../piano_teacher/server.py#L2665-L2683) |
| O03 | High | Different assessment pass criteria drive advancement and trouble clearing | [practice.py](../../piano_teacher/practice.py#L94-L133), [teaching_decisions.py](../../piano_teacher/teaching_decisions.py#L167-L182), [attempt_settlement.py](../../piano_teacher/application/attempt_settlement.py#L105-L114) |
| O04 | High | Count-in length/ownership is separately derived in coordinator, attempt progression and Godot metronome | [playback_coordinator.py](../../piano_teacher/application/playback_coordinator.py#L128-L187), [attempt_progression.py](../../piano_teacher/application/attempt_progression.py#L96-L115), [metronome_frame_coordinator.gd](../../godot/metronome_frame_coordinator.gd#L24-L112) |
| O05 | High | Score preloader computes handoff timing also computed during physical admission | [score_runway.gd](../../godot/score_runway.gd#L405-L461), [server.py](../../piano_teacher/server.py#L3783-L3840), [teaching_continuation.py](../../piano_teacher/application/teaching_continuation.py#L158-L166) |
| O06 | Medium-high | Presentation position/rate is reconstructed in several independently stateful projections | [transport_projection.py](../../piano_teacher/transport_projection.py), [visual_transport_clock.gd](../../godot/visual_transport_clock.gd), [continuous_score_flow.gd](../../godot/continuous_score_flow.gd), [main.gd](../../godot/main.gd#L1109-L1223) |
| O07 | Medium | Architecture specifications still describe mutually incompatible owners | [new contract](playback-coordinator.md), [old contract](transport-and-voice-contract.md), [system overview](system.md) |
| O08 | High structural | Cross-component access to private mutable fields substitutes for typed ownership interfaces | [score_admission_gateway.gd](../../godot/score_admission_gateway.gd#L76-L95), [score_runway.gd](../../godot/score_runway.gd#L333-L375), [main.gd](../../godot/main.gd#L1129-L1193) |
| L01–L03 | High structural | Three oversized classes combine several distinct lifecycle and policy responsibilities | See large-file review below |

Severity denotes risk or product mismatch, **not** proof that every listed risk has produced a user-visible failure. P01 is explained directly by the source selection code; O01–O05 have specific conflicting decision paths; O06 and O08 are design risks requiring end-to-end behavior checks.

## P01 — Tempo begins with the complete four-measure phrase

### What the code actually does

1. [practice_flow_course.py](../../piano_teacher/practice_flow_course.py#L20-L66) intentionally creates phrases of **two to four bars** by merging source-safe units. The first exercise points to this entire phrase ([lines 74–105](../../piano_teacher/practice_flow_course.py#L74-L105)).
2. The initial Free path can bind the complete phrase: [server.py _begin_learn](../../piano_teacher/server.py#L1260-L1310) uses the exercise's full end when the exposure has no end bound. The smaller two-bar fragment selector in [guided_fragment.py](../../piano_teacher/application/guided_fragment.py#L26-L42) is **not** the limiting path when an explicit full interval is materialized.
3. On Free completion, [PracticeFlowLessonGenerator.decide_teaching](../../piano_teacher/practice_flow_course.py#L125-L136) creates a timed exposure with **from_beat = 0.0 and end_beat = None**. That asks for the entire current phrase.
4. [PracticeEngine.start](../../piano_teacher/server.py#L1635-L1720) uses the whole active phrase for its recorder and assessment end unless a separate review bound exists. The [PlaybackIntent](../../piano_teacher/application/playback_coordinator.py#L30-L54) carries a start beat but **no explicit selected end beat**. The [ScoreSelection](../../piano_teacher/application/score_artifacts.py#L37-L52) similarly binds the selected phrase, not a separate bounded learning window.
5. The native [view.gd](../../godot/notation/native/view.gd#L729-L817) divides the phrase into separate immutable *drawing strips*, but those strips still cover the full phrase. Splitting rendering buffers into bars does not shorten the music selected for practice.

**Conclusion:** This is not primarily a renderer showing too many measures. The domain model selects and grades a four-measure phrase as one Tempo exposure. The renderer faithfully displays the selected phrase. The current [practice-flow specification](../practice-flow.md#L33-L68) also explicitly requests 2–4-bar phrases. The user's desired **measure-first** behavior is therefore a product-specification mismatch as well as a missing architectural distinction between *phrase*, *learning unit*, *active assessment interval*, and *display context*.

### Required design

Introduce one immutable **PracticeWindow** (or LearningUnit) chosen by a dedicated **WindowProgressionPolicy**:

- **Phrase**: stable larger musical unit (currently 2–4 bars), used to plan eventual joining, context, hand sequence and source-safe boundaries.
- **PracticeWindow**: the exact currently active subset, including source fingerprint, phrase/stage identity, hand, source-note IDs, start/end beats, authored bar numbers, a unique window identity, and whether this is a measure, accumulated prefix, link or final verification.
- **PresentationContext**: adjacent bars may optionally be shown dimmed, but they are not in the active score-stream admission, expected-note set or graded take.
- **PracticeWindowProgress**: explicitly persisted achievement/tempo/failure state per window; advancing to another window cannot inherit false mastery or erase valid progress.

**Default first Tempo exposure:** only the **first authored measure** in the phrase, not all four. If a sustained note/tie, cross-bar beam, slur or required clef context makes a literal cut unsafe, the source-safe window must retain the necessary ink and sounding duration without accidentally grading later attacks. Such exceptions must be explicit and inspectable.

**Recommended gradual sequence:** measure 1, then 1–2, then 1–3, then 1–4 (or to the actual end of the phrase). Each enlargement is an explicit teaching decision made only after the preceding window meets its learning criterion. For a one- or two-bar phrase, shorten this sequence accordingly; skip genuinely empty bars by a documented rule. This prefix ladder retains continuity and is preferable to treating every bar as a disconnected independent lesson. Phrase links and the whole-piece final test remain separate, explicit stages.

The Free and Listen stages must use the intended current window rather than silently reverting to the whole phrase. The selected window identity and **both start and end** must flow through the teaching decision, guided fragment, playback intent and receipt, canonical score selection, score cache identity, expected-note projection, grading scope, learning ledger and UI. The score renderer must never decide which measure is learned, and the teaching policy must not infer an interval from a viewport or from clipping.

**Acceptance gate:** With a four-bar phrase, the first Tempo take contains only first-bar attacks and its correct source-safe release, has exactly that bar's expected notes, stops/settles at that window's end, and does not award credit for bars 2–4. Those later bars cannot silently become fully active at start. Advancement adds one measure per explicitly recorded achievement; Pause, Retry, tempo ladder, hand changes, resumed progress, Coda/Fukuda aids and final verification preserve the selected window identity. Verify a sparse bar and a tie across a boundary. Optional dim context is visually distinguishable and excluded from grading.

## O01 — Restart decisions have competing executors

[SessionCommands.start_route](../../piano_teacher/application/session_commands.py#L38-L46) can select rewind; [server.py _control_transport](../../piano_teacher/server.py#L2241-L2310) sends several routes through admission; [_commit_playback_intent](../../piano_teacher/server.py#L1728-L1796) starts a take via a different path than the preparation and rewind logic in [_start_or_restart](../../piano_teacher/server.py#L2332-L2420). Thus an explicit restart policy is not guaranteed to be executed by the admitted route.

**Resolution:** A single pure **PlaybackTransitionPlanner** returns a typed, immutable transition (start/restart/resume/automatic, selected PracticeWindow, preparation/rest strategy, previous-take cancellation policy, count-in plan). The coordinator executes precisely that transition. Remove engine-local re-routing and prepare/restart fallbacks. A visual retry must preserve the monotonic world axis; any preparation is authored as future notation and silence rather than a hidden rewind/seek.

**Acceptance:** Every input (UI, MIDI shortcut, automatic, pause/resume, recovery) maps to one transition type and one authorization boundary. No route computes a fresh teaching selection during commit.

## O02 — Display messages are parsed as decisions

[practice_flow.outcome_of](../../piano_teacher/application/practice_flow.py#L145-L162) recognizes English message prefixes. [server.py](../../piano_teacher/server.py#L2665-L2683) then uses the parsed result to drive a second flow state. [teaching_decisions.py](../../piano_teacher/teaching_decisions.py#L237-L255) also compares an exact “Piece mastered” string to stop continuation.

**Resolution:** Emit one typed **TeachingOutcome/TeachingEffect** directly from the authoritative pure teaching reducer. Its fields include next step, next PracticeWindow, source/hand change, BPM and progression counters, mastery/continuation, and message *key* with presentation parameters. Persistence applies the immutable effect exactly once. Human-readable text is formatted only in a presenter; localization/rewording cannot change behavior. The second flow state either becomes the single reducer state or a derived read-only projection, never another decision-maker.

**Acceptance:** Rewording any feedback message cannot change course progress, stage, auto-repeat, mastery or pause decisions. No parsing of learner-visible strings for control flow remains.

## O03 — Two incompatible success definitions

[Assessment.passed](../../piano_teacher/practice.py#L112-L120) tolerates some timing warnings, while [Assessment.flow_passed](../../piano_teacher/practice.py#L121-L133) fails on early/late attacks. Practice Flow uses the latter in [teaching_decisions.py](../../piano_teacher/teaching_decisions.py#L167-L182), whereas [AttemptSettlement](../../piano_teacher/application/attempt_settlement.py#L108-L114) clears trouble using the former. A take with one early and three correct attacks can be failed by progression while simultaneously clearing recorded trouble.

**Resolution:** A single **AssessmentPolicy** strategy maps canonical observations to an immutable **AssessmentVerdict** with independently named, explicit decisions (e.g. accepted_for_progression, clean_for_mastery, clears_trouble, valid_for_transfer, valid_for_coda_feedback). The verdict is captured in the same settlement transaction and shared by all consumers. No downstream component calls a different convenience “passed” property to infer a conflicting interpretation.

**Acceptance:** One evaluated take has one policy/version and one recorded verdict; progression, diagnostic tracking and persistence agree, including timing warnings and assisted/partial/preview takes.

## O04 — Count-in plan is recalculated

The [PlaybackCoordinator](../../piano_teacher/application/playback_coordinator.py#L128-L190) calculates the authored bar count-in, while [AttemptProgression.schedule_start](../../piano_teacher/application/attempt_progression.py#L96-L115) sets a continuation's count_in_beats to zero. [MetronomeFrameCoordinator](../../godot/metronome_frame_coordinator.gd#L24-L112) additionally owns its reserved cue schedule and fallback deadline derivation.

**Resolution:** The same immutable **CountInPlan** is attached to the authorized playback transition, with exact bar meter, compound pulse grouping, cue identities, remaining-partial reuse, start/downbeat epochs, and a single deduplication token. AttemptProgression receives it and cannot set another length. The audio/circle/voice consumers render the cue events; they never construct or retime the plan.

**Acceptance:** A fresh take and every automatic repeat speak only the last full bar before the authorized deadline; Paused count-in reuse never repeats already-spoken syllables. No hidden second count-in, including 6/8–12/8 and very slow BPM.

## O05 — Preloader also plans handoff time

[ScoreRunway._short_handoff](../../godot/score_runway.gd#L432-L461) computes clearance/lead and sends it through [server.py](../../piano_teacher/server.py#L3783-L3840) to [TeachingContinuation.handoff](../../piano_teacher/application/teaching_continuation.py#L158-L166), which schedules a handoff. The actual score is subsequently admitted by the physical admission gateway, making the preloader a second physical-timing authority.

**Resolution:** **ScoreRunway** exclusively prepares and retains identity-bound source assets; its acknowledgement reports asset readiness, revision and failure only. The **ScoreAdmissionGateway** is the only owner of current cross-layer physical clearance and reservation. **MusicalScheduler** converts those constraints into one absolute deadline. **PlaybackCoordinator** authorizes the result. Remove readiness-carried lead/clear fields, handoff estimates and their obsolete storage from PracticeEngine.

**Acceptance:** Preloading cannot start, delay or retime playback by itself. Late assets wait while the world continues, and the next stage is admitted from actual geometry exactly once.

## O06 — Multiple independent presentation time integrators

[transport_projection.py](../../piano_teacher/transport_projection.py), [VisualTransportClock](../../godot/visual_transport_clock.gd), [ContinuousScoreFlow](../../godot/continuous_score_flow.gd) and [main.gd](../../godot/main.gd#L1109-L1223) each project or correct presentation time. In particular, **ContinuousScoreFlow._slow_debt** amortizes late tempo corrections based on the arrival history of snapshots. This creates a risk that two clients evaluating the same nominal timestamp compute different world positions.

**Resolution:** One immutable, versioned **PresentationTimeline** defines monotonic origin, piecewise speed epochs, source/world mappings, deliberate holds and exact point transitions. A single deterministic **PresentationProjector** is responsible for time → world position, derivative/speed and inverse world-position → time queries. Godot frame rendering, preflight admission and cursor positioning all use it. The engine publishes timeline revisions and cannot rely on an unrelated projector producing equivalent positions. Eliminate rate-debt repayment, guessed clock offsets and duplicate rate-switch handling. Keep musical source time and continuous visual time distinct but linked by one versioned mapping.

**Acceptance:** The same timeline version and timestamp yield the same position regardless of frame/poll cadence, delayed snapshots or a late tempo change. No backward motion or repositioning of exposed ink.

## O07 — Conflicting architecture contracts

[playback-coordinator.md](playback-coordinator.md) declares one authorization protocol; [transport-and-voice-contract.md](transport-and-voice-contract.md) still describes Main owning reservation and timed score_queue_next. [system.md](system.md) also retains previous ownership descriptions.

**Resolution:** Maintain one current architecture overview and explicit Architecture Decision Records for major decisions. Mark old contracts as superseded (and preserve historical rationale separately); update code-facing documentation when each old path is removed. Avoid contradictory “sole owner” statements.

**Acceptance:** Searching current documentation for a given responsibility yields one active owner and one documented public interface.

## O08 — Private state crosses component boundaries

Examples: [ScoreAdmissionGateway._matching_renderer](../../godot/score_admission_gateway.gd#L76-L95) reads score_session._fingerprint, runway._future, runway._acknowledged and runway._bundle; [ScoreRunway](../../godot/score_runway.gd#L333-L375) directly changes stage.renderer and calls score_session.replace_renderer; [Main](../../godot/main.gd#L1129-L1193) coordinates the same instances. These consumers depend on internal storage and method call order instead of an explicit bounded port.

**Resolution:** Introduce narrowly typed public operations: **ScoreAssetProvider.lookup_ready(identity)**, **ScoreAdmissionPort.prepare/commit/cancel/status**, **RendererStagePort.promote_authorized(segment_id)**, and **PresentationSnapshotPort**. Give a single owner responsibility for replacing the active renderer and retaining its predecessors. Other components receive immutable identity-bound capabilities/receipts rather than mutating private fields. Do not create pass-through wrappers that still expose the old dictionaries.

**Acceptance:** No cross-component mutation of another module's private underscore fields; stage promotion and rollback have one API and stable idempotent ordering.

---

## Largest first-party production source files — detailed responsibility review

Measured from the Git tree at the source baseline; excludes binary assets, tests and vendored Godot MCP toolkit. Size is a signal to inspect **cohesion and ownership**, not a reason to split files mechanically.

| Rank | File | Bytes | Lines | Approx. top-level method declarations |
| --- | --- | ---: | ---: | ---: |
| 1 | [piano_teacher/server.py](../../piano_teacher/server.py) | 216,648 | 3,892 | 150+ |
| 2 | [godot/notation/native/view.gd](../../godot/notation/native/view.gd) | 97,601 | 1,986 | 68 |
| 3 | [godot/main.gd](../../godot/main.gd) | 68,677 | 1,468 | 90 |

### L01 — PracticeEngine/server.py: application god object

**Evidence of mixed responsibilities:** It constructs the device, library, settings, progress repository, assessment, listening, teaching policy, preloader and playback coordinator ([initialization](../../piano_teacher/server.py#L130-L278)); directly manages MIDI callbacks ([receive](../../piano_teacher/server.py#L736-L801)); owns course flow and message policy ([flow methods](../../piano_teacher/server.py#L1088-L1172)); selects/installs exercises ([1260–1360](../../piano_teacher/server.py#L1260-L1360)); schedules transport and count-in ([1635–1975](../../piano_teacher/server.py#L1635-L1975)); routes commands and restart behavior ([1984–2575](../../piano_teacher/server.py#L1984-L2575)); settles, persists and triggers recovery ([2612–3204](../../piano_teacher/server.py#L2612-L3204)); projects a snapshot including graphical/headless branches ([3461–3652](../../piano_teacher/server.py#L3461-L3652)); and governs native score/preload readiness ([3726–3885](../../piano_teacher/server.py#L3726-L3885)). Dozens of mutable flags such as pending_result, review_end_beat, _future_stage_clear_beats, _short_rest, _pending_rolling, session_commands.prepared and awaiting_score_revision encode overlapping life cycles.

**Why it matters:** A method can alter course selection, transport, score revision, learner evidence and GUI readiness without a bounded transactional interface. Small changes to a lifecycle edge have cross-domain consequences. The previous playback-coordinator replacement did not remove all old scheduling responsibilities.

**Target:** Keep **PracticeEngine** as a thin locked application facade/composition root (and explicit public command surface), with separate cohesive owners:

- **CourseSession**: authoritative teaching reducer, current PracticeWindow and selected exposure, stage/revision and navigation.
- **PlaybackSession**: transition planner, PlaybackCoordinator and immutable count-in/presentation authorization.
- **AssessmentSession**: recorder, timing policy, AssessmentVerdict, rolling/whole completion.
- **AttemptUnitOfWork**: settlement and durable evidence/progress transaction, failure reconciliation.
- **AssetSession**: current/next score selection, readiness and identity-bound handoff.
- **InputSession**: MIDI device/callback timestamp, queued semantic controls and graded-note ingestion.
- **SessionProjection**: immutable state capture and mode-appropriate presentation adapters, without domain mutation.

Existing pure modules and repositories should be moved under these ownership boundaries rather than duplicated. Prefer one typed command result/effect and a single mutation transaction. **Remove** obsolete fields and branch implementations instead of leaving delegating facades with parallel state.

**Completion:** PracticeEngine coordinates ports/transactions only, no second lesson policy, no direct score-geometry timing, no direct persistence policy and no fallback graded-start path. Public behavior, headless adapter, shutdown and saved progress remain supported.

### L02 — notation/native/view.gd: renderer + admission controller + mutable ledger

**Evidence of mixed responsibilities:** The same Node handles score loading, fingering input and glyph preparation ([206–461](../../godot/notation/native/view.gd#L206-L461)); computes ink-safe clipping and retains source/rest textures ([462–728](../../godot/notation/native/view.gd#L462-L728)); selects/appends source windows and rests ([729–857](../../godot/notation/native/view.gd#L729-L857)); owns transport preflight, queue withdrawal and rollback ([857–1357](../../godot/notation/native/view.gd#L857-L1357)); processes guided/recovery score announcements and active segment binding ([1358–1707](../../godot/notation/native/view.gd#L1358-L1707)); and renders cursor, staff, beams and note status ([1708–1986](../../godot/notation/native/view.gd#L1708-L1986)). Its own mutable _stream_live_serial, _stream_armed_serial, _stream_arm_rollback and _scheduled_score_plan_ids overlap the separate ScoreStreamQueue, Gateway and PlaybackCoordinator concepts.

**Why it matters:** Rendering and transaction state share the same object. An innocent repaint/recompile, palette or density update can reset or mutate state needed by score admission; the native view also still offers old publication and announced-copy helpers.

**Target composition:**

- **NativeScoreView**: strictly the CanvasItem/Node façade, draw/resize/input forwarding and retained visual asset presentation.
- **ScoreAssetAssembler**: source/model/glyph loading and immutable atlas/geometry generation.
- **NotationClipPlanner**: source-safe windows and header/tie/slur clipping, a pure calculation.
- **ScoreStreamController**: sole owner of source/rest FIFO, immutable segment/serial ledger, safe suffix withdrawal, rollback and archived tails; bounded commit/ack/cancel APIs.
- **ScorePresentation**: binds one authorized segment to projected world and paints visible source/rest/cursor/feedback; never admits or reselects music.
- **FingeringEditPort**: independent annotation interaction and commands.

Use existing ScoreStreamQueue, StreamAdmission, StreamLifecycle, painters and retained-segment modules as implementation parts; avoid making new parallel queues. Eliminate retired READY/autopending machinery and any renderer path capable of starting graded music.

**Completion:** Score drawing cannot mutate playback ownership, no renderer controls teaching deadlines, no raw queue state is read by external coordinators, and load/recompile cannot erase already-exposed strips.

### L03 — godot/main.gd: composition root that still orchestrates business logic

**Evidence of mixed responsibilities:** It creates screen/UI hierarchy and scaling ([182–733](../../godot/main.gd#L182-L733)); manages asset requests and score warmup ([741–825](../../godot/main.gd#L741-L825)); handles library/settings/navigation/devices ([829–939](../../godot/main.gd#L829-L939)); polls state and feedback ([939–1019](../../godot/main.gd#L939-L1019)); implements guided hold, tempo-switch compensation and ordering of renderer/promotions in a long _on_state ([1022–1225](../../godot/main.gd#L1022-L1225)); and routes many actions, keyboard shortcuts and debug diagnostics ([1226–1468](../../godot/main.gd#L1226-L1468)). Despite already owning a ScoreAdmissionGateway, Main still accesses renderer internals and independently integrates presentation epochs.

**Why it matters:** The order of callbacks inside a top-level screen script is an accidental domain protocol. Adding a new screen or changing when a snapshot is handled can change score admission, audio sync or retained-tail lifetime.

**Target:** Main is a **composition root and scene lifecycle owner only**, wiring dependencies and top-level navigation. Extract:

- **ApplicationEventRouter / StateInbox**: one ordered, revision-checked path for command replies, state snapshots and backend events; no screen-specific parsing.
- **PresentationSession**: the only owner of frame-time sampling, canonical visual timeline and sequencing renderer projection after admission.
- **PracticeSceneController**: binds PracticeScreen state, controls, guided hints and feedback without re-deriving policy.
- **ScoreSceneController**: public adapter for asset readiness, authorized promotion and native visual layers, including source picker.
- **AudioSession**: cue/Listen/click coordination consuming the authorized timeline.
- **NavigationSession**: screen selection, back/exit, library and settings routes.
- **DiagnosticsPresenter**: logging and bounded observability, never treatment of an error as an implicit control event.

Retain actual reusable screen components/coordinators; transfer responsibility, do not wrap the same giant _on_state in another file. Enforce ordering with a typed event queue/reducer and explicit effects.

**Completion:** Main contains scene composition and lifecycle wiring only; a state-poll ordering change cannot silently authorize, cancel or move notation.

## Intended owner map

| Decision or mutation | Exactly one owner | Other components |
| --- | --- | --- |
| Next lesson, hand, PracticeWindow and tempo | TeachingReducer/CourseSession | Read typed TeachingEffect |
| Assessment interpretation and mastery eligibility | AssessmentPolicy | Consume one immutable AssessmentVerdict |
| Meaning of UI/MIDI Play, Retry, Resume and Stop | PlaybackTransitionPlanner | Emit semantic intent |
| Absolute musical start and lifecycle | PlaybackCoordinator | Execute authorized take |
| Actual feasible note geometry | ScoreAdmissionGateway + one ScoreStreamController | Return receipt / immutable geometry facts |
| Full count-in and compound cues | CountInPlan embedded in authorized take | Audio and UI render cue events |
| Monotonic visual position | PresentationTimeline + one projector | Renderer and admission consume coordinates |
| Current/preloaded score identity and readiness | AssetSession | Return identity-bound prepared assets |
| Current renderer replacement and outgoing-tail retention | ScoreSceneController | Others never set stage.renderer |
| Durable progress and attempts | AttemptUnitOfWork | Apply one typed teaching effect/verdict atomically |
| Display text and visual feedback | Presenters | No policy decision parses display messages |

Use dependency inversion at Python/Godot boundaries; explicit immutable value objects instead of stringly typed option dictionaries, magic action names, writable foreign underscore fields or implicit acknowledgement ordering. A design pattern is useful only when it *removes* authority from the wrong place.

## Dependency-ordered implementation plan (future work; not authorized by this document)

**Phase 0 — Freeze domain and acceptance contracts.** Define the exact typed PracticeWindow, TeachingOutcome/Effect, AssessmentVerdict, PlaybackTransition, CountInPlan, PresentationTimeline and score admission receipt contracts. Map their current producers/consumers, migration strategy for progress, and event order. Resolve how cross-bar holds behave and which later bars may be dim context. This phase is complete only when every reader/writer and obsolete route is accounted for.

**Phase 1 — Consolidate teaching and assessment authority.** Make the teaching reducer the sole owner of progression, remove outcome-from-message parsing, unify all assessment consumers on the same verdict and settle exactly one decision via Unit of Work. Integrate manual controls, adaptive Coda/Fukuda, progress persistence and interrupted attempts. Delete secondary mutations/counters, not just add an adapter.

**Phase 2 — Implement measure-first progression end-to-end.** Select and persist PracticeWindow identity and a first-bar active range; integrate it into generated courses, Free and Listen, all note IDs, source-safe clipping, score caching, playback admission, MIDI grading, recovery, tempo ladder, hand changes, context rendering and saved-resume migration. Add deliberate prefix growth across the phrase, links and final performance. Phase 2 is complete only when there is no four-bar initial active Tempo exposure and no hidden later-bar grading.

**Phase 3 — Finish one playback transition and count-in authority.** Replace the old Restart/routing and automatic handoff branches with typed PlaybackTransition execution; unify the count-in schedule and partial Resume; remove score-preloader timing, speculative deadlines and competing start/retime paths. Keep the native perpetual visual clock and immutable exposed notes. Complete UI/MIDI/Listen/Free/Tempo/recovery/hand-off coverage.

**Phase 4 — Deterministic presentation and physical admission.** Implement one PresentationTimeline/Projector with exact forward/inverse mappings; migrate all frame, reserve, recovery, audio and tempo-change consumers; remove independent projection/slow-debt correction logic. One public gateway owns physical clearance, reservations and rollback; one stage owner owns promotion.

**Phase 5 — Decompose the three oversized production classes.** Transfer all fields, methods and side effects from server.py, view.gd and main.gd into the owner components above. Keep only thin composition facades with explicit ports. Remove old code and stale private-field access in the same phase, not in a deferred cleanup. Preserve persistence, native rendering, keyboard, audio, fingering, navigation and diagnostics.

**Phase 6 — Retire obsolete contracts and validate the complete product.** Rewrite the active architecture docs; mark historical decisions superseded. Run existing Python/Godot CI and production native-build checks, then conduct full physical MIDI, timing, count-in, Listen/Free/Tempo, low BPM, changing meter, long score, Pause/Resume/Retry, sparse measure, cross-bar sustain, recovery, preloaded transition, crash/restart and saved-progress acceptance. The prior request to write no new tests is respected by **this audit**: no test or application code is created here. Any later test-suite expansion is a separate implementation decision.

No phase is complete while an old second authority, old shortcut or duplicate projection is still active. Refactoring must preserve full behavior, not just pass isolated unit tests.

## Evidence versus assumptions

- **Confirmed in source:** phrase generation is 2–4 bars; Free completion selects the entire phrase; the timed intent lacks an end; the three largest files and their responsibilities; outcome parsing; conflicting pass properties; duplicated countdown and preloader timing paths.
- **Inferred product expectation:** the first Tempo exposure should be one bar with gradual prefix growth because the learner reported that seeing/receiving all four at entry is wrong. The exact later growth order above is a recommended design, not a claim about existing behavior.
- **Not established without live playback:** how many measures are simultaneously visible within a given viewport, audio and physical MIDI latency, actual display drift in a particular piece, or every possible asynchronous ordering failure. These remain acceptance scenarios rather than claims of reproduced defects.
