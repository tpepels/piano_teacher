# Ownership, lesson-window and large-file architectural audit

**Status:** Implementation underway on `main`. This file tracks actual code commits; unfinished items remain explicitly marked. The detailed audit below is historical baseline evidence; it is not a description of current source paths or unresolved behavior.  
**Source baseline:** [main at 9a01a9b7](https://github.com/tpepels/piano_teacher/tree/9a01a9b7d9434ae6a3ef7bc72fd6844222d718ef), 19 November 2026.  
**Scope:** Practice Flow, learning/assessment, playback and score admission, presentation timing, and the three largest first-party production source files.  
**Goal:** One authoritative owner for each domain decision; explicit typed boundaries; no independent recomputation of a decision downstream; preserve the continuous native score and all existing capabilities.

See also the current source-based [PracticeEngine responsibility/dependency audit](practice-engine-decomposition-audit.md), which distinguishes actual mutable owners from wrappers and defines the dependency-ordered extraction work.

## Implementation progress

**Implementation branch:** `main`. **Tests:** No new tests introduced. Existing fixtures were migrated to current public admission/score ports and one legacy parser assertion was retired. Core CI passed through `586e37b5` ([run 44733911571](https://github.com/tpepels/piano_teacher/actions/runs/44733911571)); the latest native-only queue diagnostic change awaits that same core check. Full native+repertoire+package CI passed earlier at `dedc7bd5` ([run 44732784904](https://github.com/tpepels/piano_teacher/actions/runs/44732784904)); subsequent source needs the same complete suite. Physical audio/MIDI cannot be certified by headless runs.

| Workstream | Status | Notes |
| --- | --- | --- |
| Moving-window curriculum / P01 | INTEGRATED; PHYSICAL ACCEPTANCE OUTSTANDING | `practice_windows.py` selects n, n−1..n, n−2..n, n−3..n (max 4) and emits real source-bounded course exercises; independently identified windows, versioned saved progress and separate final exam; existing CI passed on `f1d3385` |
| Typed course outcomes / O02 | SINGLE TYPED PRODUCTION PATH; LEGACY PARSER REMOVED | `TeachingDecision.flow_outcome` carries `Outcome` directly through course/engine; `outcome_of(message)` and its obsolete parser assertion have been deleted |
| Unified assessment verdict / O03 | INTEGRATED ACROSS TEACHING, EVIDENCE AND SNAPSHOTS; LIVE CHECK OPEN | The selected verdict now drives course progression, recorded acceptance, UI summary and durable trouble clearing; raw grader acceptance is retained under a separate diagnostic field; non-graded legacy adapters remain distinct |
| Unified playback transitions / O01, O04 | GRAPHICAL COUNT-IN SINGLE-TAKE PATH INTEGRATED; LEGACY AND PHYSICAL ACCEPTANCE OPEN | Immutable PlaybackTransition and CountInPlan are accepted once; metronome uses take-keyed authorized segments through Pause/Resume, rejects mismatched deadlines and does not invent unadmitted graphical countdowns; headless compatibility and hardware acceptance remain |
| Asset admission / O05, O08 | ONE PHYSICAL PREFLIGHT + STREAM OWNER; PAINTER COUPLING OPEN | ScoreTransportReservation requires frozen physical facts; ScoreStreamController owns Play/Resume/Retry, recovery, immutable source/rest append, ledger/rollback/serial identities; ScoreSceneController owns renderer promotion. NativeView retains in-process drawing/queue bridge and painter lifecycle |
| Deterministic presentation timeline / O06 | INTEGRATED IN GODOT; PHYSICAL VALIDATION OPEN | Versioned PresentationTimeline owns world-position/rate epochs, Free holds and hypothetical forecasts; ContinuousScoreFlow delegates; Main no longer retroactively integrates tempo debt; native audio/MIDI acceptance unverified |
| Architecture docs / O07 | CURRENT ENTRYPOINTS RECONCILED; REFERENCE SWEEP OPEN | ROADMAP and documentation index now point to the actual moving-window policy and current playback/ownership contracts; ADR-0001 and playback coordinator document authority; old ownership contracts marked historical. Deeper document cross-reference sweep remains open |
| Decompose server.py / L01 | DOMAIN OWNERSHIP MOSTLY EXTRACTED; APPLICATION ORCHESTRATION STILL LARGE (~3,366 lines) | Immutable PlaybackFacts, AttemptRuntime/RecoveryStreak, LearningEvidence, AttemptSettlement, PassageOutcomePresenter, TeachingContinuation, GuidedSession, SourcePreparation, ListenSession, MidiIngress and source-metrical notation now own their domains. Engine still executes command/start/resume/completion/recovery and handles roughly 150 API methods; not a thin facade |
| Decompose native/view.gd / L02 | NATIVE PAINTING/COMPOSITION OWNER (~1,100 lines); MULTI-POLICY MUTATION REMOVED | ScoreStreamController owns the mutable queue, deadlines and future-only sources; RetainedNotationPool owns compiled CanvasItems. Public online/offline ledger snapshots are deep-copied. NativeView still has about 74 renderer/composition/painting functions; native recheck pending |
| Decompose main.gd / L03 | ROOT SCENE COMPOSITION (~1,028 lines); EVENT OWNERS EXTRACTED | ApplicationInputSession, ApplicationStateInbox, PracticePresentationSession, PracticeFeedbackSession, CountInAudioSession, navigation, score admission, settings and diagnostics own inputs and effects. Root scene still wires 81 UI, viewport and backend lifecycle methods |
| Existing CI/native integration | FULL NATIVE + CLEAN RELOCATED PACKAGE PASSED `dedc7bd5`; CURRENT CORE GREEN THROUGH `586e37b5` | [Native run 44732784904](https://github.com/tpepels/piano_teacher/actions/runs/44732784904) passed real CPython/Godot, Moonlight/Peace Piece/Chopin, and relocated archive boot. [Core run 44733911571](https://github.com/tpepels/piano_teacher/actions/runs/44733911571) passed most recent back-end lifecycle changes. Further source changes require latest full native check; USB/Bluetooth/CA49 and audible sound are not verified |

### Phase completion status

| Phase | State | Outstanding completion gate |
| --- | --- | --- |
| 0 — Domain and acceptance contracts | **Documented; integration audit open** | Full producer/consumer migration, versioned presentation and physical acceptance assertions |
| 1 — Teaching/assessment authority | **Substantial source integration; not complete** | Collapse remaining overlapping course/flow decision state and verify assisted/interrupted/recovery paths in native product |
| 2 — Moving-window pedagogy | **Source implementation complete; native acceptance pending** | Physically observe every window/hand, sparse and cross-bar sustained notes, saved reopen; no new tests requested |
| 3 — Playback/count-in authority | **Integrated graphical gate; exceptions still to audit** | Confirm all manual, MIDI shortcut, automatic, recovery and preloaded pathways with real score+audio |
| 4 — Presentation and admission | **Canonical projector and read-only preflight implemented; native acceptance pending** | Validate immutable ink/cross-layer clearance under changing tempo and real runtime |
| 5 — Three large-class decomposition | **Incomplete** | Remove remaining policy/ledger logic and transitional property adapters from PracticeEngine, NativeView and Main |
| 6 — Retire docs and accept product | **Historical docs reconciled; product acceptance incomplete** | Run existing embedded production and packaging scripts; physical Kawai CA49 exercises and manual scenarios in acceptance matrix |

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

### Implementation checkpoint C — presentation, source clipping, and actual class decomposition

- `9aa3861` and `7d7452e`: Godot consumes the authoritative CountInPlan with its exact segment identity. A mismatched future deadline does not silently rebase already audible syllables.
- `5895e96` and `b47dd36`: Created pure NotationClipPlanner and removed native-view geometry/clipping calculations.
- `01f7902`, `a269da7`, `56a9692`, `d3b63e4`, `63a34a8`, `54134aa`, `57c6360`, `83aad64`: Created PresentationTimeline with explicit rate epochs and source-map forecast; removed historical tempo-debt compensation and Main's dual rate-switch authorities. Existing flow behavior check passed at `83aad64`.
- `da92cc7`, `9fa83e8`: Moved untimed guided Free note target, hold and presentation ownership out of Main.
- `9a46b47`, `4624397`: Moved graphical/headless score projection and stable Free display epochs out of PracticeEngine and into ScoreStatePublisher.
- `34b855d`, `3b39a12`: Moved renderer/asset/admission clock reconciliation and promotion ordering out of Main into PracticePresentationSession.
- `0b78482`, `411781e`: Extracted timed physical reservation orchestration to StreamAdmissionExecutor.
- `db0233e`, `9dabb38`, `9ac0e1b`: Removed diagnostic file ownership and renderer's private failure reads from Main.
- `9c558cf`, `8e2a6fa`, `23d886f`: Marked historical architecture documents superseded and added [ADR-0001](decisions/ADR-0001-single-authority.md).
- `f1d3385`: Kept the existing headless reservation fixture on its read-only geometry interface while production uses the new public geometry port. Existing CI green.

**Explicitly not complete:** Full decomposition of `server.py`, `view.gd` and `main.gd`; eliminating every remaining private cross-component mutation and legacy/adaptor decision branch; full-reader policy verdict audit; in-process/native-device/physical acceptance. Do not report the whole remediation as finished.

### Implementation checkpoint D — assessment readers and runtime ownership (19 November 2026)

- `a9a7bbb`, `5fe2414`, `ac722de`, `805f315`: Unified persisted acceptance, pending take projection, feedback, and clearing of trouble against the exact `AssessmentVerdict`. Stored `raw_grader_passed` remains diagnostic and is not an alternative mastery decision. Full passage selects its decision before sealing; an existing pending decision is reused during settlement.
- `d9795a0`, `4497ef8`, `85bebf9`: Introduced a single ScoreStreamController for the mutable queue, admitted serial, paused/live/armed segment identities and rollback state; moved storage from NativeView and registered retained predecessor layers through a port.
- `3108588`, `981e929`, `835d25a`: Added ScoreSceneController as the one writer of `stage.renderer` and coordinated asset revision adoption for normal and preloaded stage promotion.
- `d3ed624`, `3124a0e`: Moved MIDI successor suppression and immutable-timestamp rollover deferral from PracticeEngine into MidiIngress, preserving the existing semantic command path for configured piano-key shortcuts.
- `ea86083`, `daf2012`: Extracted navigation screen state, settings/back routes and pause/navigation effects from Main into NavigationSession.
- `8ed13d9`, `ea53d71`, `31d7dc5`, `104fa98`: Unified graphical count-in cues under an authorized take identity; removed the second graphical countdown fallback and corrected agreement checking against `playback_timeline.current`.
- `65c889c`, `069b24e`: Moved keyboard shortcut interpretation and input-capture policy from Main into ApplicationEventRouter. [GitHub Actions passed at `069b24e`](https://github.com/tpepels/piano_teacher/actions/runs/44617308164).
- `7fd4e4d`: Removed the unused old phrase/link generator so Practice Flow has one production source-window selector.
- `df0052c`, `b648154`: Archived the stale November 17 application comparison and revised the living Practice Flow specification for authored moving windows.

**Current limits:** The three large classes have fewer responsibilities but are **not yet thin facades**. A few old fallback branches and compatibility accessors still exist; no full physical MIDI/audio acceptance has occurred. Standard CI parses but does not execute the existing production Godot journey script. Avoid conflating syntax/isolated checks with actual application acceptance.

### Implementation checkpoint E — snapshot-based physical preflight and flow-state owner

- `550fd05`: Fixed a real startup-order regression: the scene no longer requests navigation before NavigationSession has all stage/screen dependencies. [Existing CI passed](https://github.com/tpepels/piano_teacher/actions/runs/44618612691).
- `46e2088`: Updated the active playback contract with ScoreStreamController, ScoreSceneController and current production/native acceptance limitations.
- `21c3653`, `fd74559`, `6dbad68`: Physical admission's transaction executor now reads the queue via controlled snapshot/count and uses explicit rollback/receipt methods, not direct private FIFO mutation.
- `4abaca0`, `2044151`, `ae5ea91`: ScoreTransportReservation consumes one frozen native renderer preflight model, containing peer clearance, authenticated source windows and paused identity. The separate isolated Godot fixture path preserves its minimal, read-only preflight interface without requiring nonexistent paused metadata. An existing CI run exposed this omission; the subsequent fix is committed.
- `dd31edf`, `29c1d0c`: Moved the Practice Flow step/messaging/status owner from PracticeEngine into PracticeFlowCourseSession. The engine now applies already-typed transitions rather than writing a second flow-state field itself.


### Implementation checkpoint F — remove cross-renderer queue introspection

- Changed the physical peer-clearance calculation to request `NativeScoreView.stream_peer_clearance_facts()`, an identity-bearing snapshot of only source/rest end coordinates, ink density and playhead offset. `ScoreStreamQueue` no longer calls `view.get("_stream_queue")` or inspects another renderer's mutable FIFO/retained nodes. The same clipping formula and peer pop-in rules are preserved.
- Moved expired source/rest retirement's active/armed-identity cleanup and one-per-plan diagnostic deduplication to `ScoreStreamController`; `NativeScoreView` now delegates without keeping duplicate ledger state. No new tests.
- Existing `tests/godot/tempo_score_reservation.gd` fixture now implements the same public peer-clearance facts port as the native view. Its existing Pathétique deadline assertions are unchanged. CI at `9fa2237c` failed because its isolated fake only exposed the retired private queue accessor; fixing the fixture preserves the production boundary. **No new tests were introduced**. Verification of the corrected commit remains pending.
- **Not complete:** The current renderer still performs the live admission/binding and retained painting algorithms and exposes internal forwarding properties. Phase 5 remains open. Existing CI and physical/native acceptance must be checked against this commit; do not mark them green merely because the code is committed.


### Implementation checkpoint G — one stream transport-state reducer

- Moved paused-owner resolution, live/armed take binding, Play/Resume acknowledgement, safe future suffix retirement, and frame-state reconciliation from `NativeScoreView` into `ScoreStreamController`. The renderer samples transport and supplies a redraw/physical-rollback port; the stream controller now applies the identity state transition once.
- The new `observe_transport` method consumes the published backend segment ID and never binds an unacknowledged or mismatched graded take. The existing source/rest FIFO, append geometry, right-tail withdrawal rules, and no-backward-ink contract remain unchanged. No new tests were introduced.
- **Remaining L02 work:** move physical append/reuse and rollback orchestration out of the view without adding another FIFO; remove transitional private-property forwarding and any foreign mutation, then validate the actual native session. Phase 5 is not complete.


### Implementation checkpoint H — renderer warmup ownership out of Main

- Introduced `StatusHeadPreloader`, which owns cross-stage Verovio head-interior texture reuse and the temporary GPU warmup layers for the first note-status paint. The existing cache key, retained render passes, early-teardown lifetime and timing diagnostics are preserved.
- Removed `Main._status_head_interiors` and the full `_warm_status_heads` implementation. The score-published callback now requests warmup through the dedicated owner, without carrying rendering caches in the scene composition root.
- No new tests. **Remaining L03 work:** extract state-event routing and command/result ownership from the scene root while preserving UI lifecycle and all wired controls. Native/physical acceptance stays open.


### Implementation checkpoint I — one debugging and schema-diagnostics owner

- Moved the debug-only state-schema validation and one-error-per-contract-problem tracking from `Main` into the existing `DebugSessionLogger`, consolidating diagnostics without another parallel log/cache.
- Removed `DebugSessionLogger`'s access to `renderer._unscored_take`; it now reads the existing public `unscored_take_status()` capability consistently.
- No new tests or test changes. This reduces the Main scene's policy/diagnostic state but does not yet finish event/scene decomposition.


### Implementation checkpoint J — retire private preflight compatibility route

- Removed `ScoreTransportReservation.plan`'s alternate path that selected source windows, the live queue, reading header, right margin and future withdrawal by directly accessing private `NativeScoreView` properties. The planner now **requires** `transport_preflight_facts()` and fails closed when the public snapshot is absent or incomplete.
- Updated the existing `tempo_score_reservation.gd` fixture to publish the exact same frozen preflight data as the real renderer; all previously existing Pathétique clearance/placement assertions stay in place. **No new tests or assertions**.
- This closes the external private-field inspection branch for the physical planner. Remaining work is extracting internal view append/rollback code and removing transitional property forwarding; full physical acceptance remains outstanding.


### Implementation checkpoint K — arm rollback belongs to the stream ledger

- Moved `cancel_stream_arm` state restoration into `ScoreStreamController.cancel_arm` and the exact archived source/rest suffix re-enqueue into `ScoreStreamController.restore_future_suffix`. The renderer retains only public delegation and provides the retained segment pools and redraw capability; the queue remains the single mutable FIFO.
- Preserve the old transactional order: withdraw only newly allocated unexposed arm strips, otherwise restore owner snapshot; recover the withdrawn suffix; restore previous live identity; reject mismatched armed owners.
- This closes another mutable decision path in `NativeScoreView`. **No new tests or test changes.** Live MIDI/audio, immutable display and native packaging acceptance are not established by a successful headless run.


### Implementation checkpoint L — current roadmap and contract index reconciled

- Corrected `ROADMAP.md`'s obsolete two-to-four-measure phrase-and-link description to the exact authored measure-first, trailing moving-window sequence selected by the owner. The separate whole-piece final test, per-window mastery, hand progression and Listen/Free/Tempo stages remain explicit.
- Corrected `docs/README.md` so it links to the *active* playback and single-authority contracts; the superseded November 4 system inventory is labelled as historical rather than presented as current architecture.
- Updated the roadmap with the current Phase 5 completion gates and linked the detailed tracker. **No new tests**. No physical/native acceptance is claimed.


### Implementation checkpoint M — verified core CI and historical status cleanup

- Existing `bash scripts/test.sh` GitHub workflow passed at `27f7f580` ([run 44625683191](https://github.com/tpepels/piano_teacher/actions/runs/44625683191)), after source checkpoints F–K and the current roadmap/index correction. The configured Python and Godot checks are green; the embedded native journey and physical MIDI/audio checks remain unverified.
- Removed contradictory “current ownership contract” sentences from the 4 November system inventory and the now-superseded transport/voice contract, retaining their historical technical rationale.
- **Phase 5 is still incomplete:** current first-party largest files include `server.py` (~3,745 lines), `godot/notation/native/view.gd` (~1,715 lines), and `godot/main.gd` (~1,175 lines). Remaining private-field adapters, view admission/recovery orchestration and application event/assessment lifecycle ownership must be moved and integrated before marking the phase done.
- **Phase 6 is still incomplete:** real embedded Godot/native bridge runs, packaged release and Kawai/USB/Bluetooth acceptance matrix have not been executed here. No new tests were introduced.

### Implementation checkpoint N — append transaction belongs to stream controller

- Moved the entire immutable source/rest strip append loop from `NativeScoreView._stream_add_take` into `ScoreStreamController.append_take`. The controller allocates serials, invokes the single `ScoreStreamQueue.enqueue` owner, rolls back an incomplete append and publishes the live/admitted identity only after all selected windows commit.
- The renderer now supplies authentic precomputed source windows, Verovio header clearance and the authored rest gap. The stage renderer does not choose queue serials or alter the source window. No new tests were added.
- **Phase 5 remains open** pending ready/reuse/resume/recovery admission extraction, elimination of transitional state accessors and PracticeEngine/Main decomposition.

### Implementation checkpoint O — execute existing Phase 6 verification in CI

- Added an opt-in `native-production` GitHub Actions job alongside the unchanged core checks. It provisions CPython 3.14 and Godot 4.7.2, compiles the real GDExtension, and runs the repository's existing `scripts/verify-embedded-production-local.sh` in **full** mode (embedded runtime, native score/Play/Resume, Moonlight, Peace Piece, Chopin, packaged runtime audit).
- Triggered by `[native]` in the commit message or a manual workflow dispatch; ordinary source pushes retain fast CI. **No tests added**; the job only runs already existing acceptance scripts.
- Native acceptance is **pending result**. This does not simulate a real Kawai MIDI device, USB/Bluetooth input latency or audible speaker/visual synchronization.

### Implementation checkpoint P — one application state inbox

- Introduced `ApplicationStateInbox` to own pending state-request epochs, stale-before-command rejection, JSON response validation, sampled callback midpoint and last accepted UI snapshot. `Main` no longer stores its own `last_state`, `state_pending`, `last_state_tick` or request-start timestamp; no duplicate snapshot can drive the scene.
- Preserved the source-picker exclusion: a valid response is not published while its local source selection is open. CommandCoordinator still owns command request/ACK, PresentationSession still owns score/admission ordering; Main applies only accepted projection effects.
- Moved transition diagnostic deduplication from `Main._on_state` into the existing `DebugSessionLogger`, so render callbacks do not own diagnostic state.
- This is an actual state-ownership transfer rather than another shadow cache. No tests added.

### Implementation checkpoint Q — native build environment repair

- Full native acceptance run [44633040983](https://github.com/tpepels/piano_teacher/actions/runs/44633040983) reached the `native-production` setup job but failed while building `python-rtmidi` for Python 3.14: runner was missing the ALSA pkg-config/development headers. The original core checks passed.
- Installed ALSA/JACK development headers in the opt-in native verification environment; production sources and application tests are unchanged. **This is infrastructure validation, not hardware acceptance.** A subsequent full native run must still finish before marking the embedded and packaging gates verified.

### Implementation checkpoint R — evidence context and retry history leave PracticeEngine

- Introduced `LearningEvidenceSession` to own exact policy/version snapshots, authored source-note evidence, rule-id persistence, calibration provenance and compatible prior-assessment query used in adaptive retry context. It receives explicit selected plan, source identity, tempo map and transport facts; no mutable engine pointer or callback bag crosses the boundary.
- Removed the ~150-line evidence construction and SQL retry-history logic from `server.py`; the engine only assembles an explicit call with current captured facts. Recorder, learning ledger, progress repository, MIDI grading and teaching policy retain their existing sole owners.
- No new tests. Hardware and embedded native acceptance still pending.

### Implementation checkpoint S — preserve native verification across source pushes

- The initial CPython 3.14 native run exposed missing ALSA headers; those were installed. Its retry was **cancelled** by the workflow-wide `tests-main` concurrency key when subsequent Phase 5 source was committed, not by a native-test assertion.
- Separated `native` and `core` workflow concurrency groups so source refactoring no longer aborts a long native compile/embedded/package verification. An explicitly tagged `[native]` push starts the full existing production audit.
- This changes only the runner scheduling and runs no new tests. CI and physical acceptance remain separate.

### Implementation checkpoint T — unified source reservation and arming

- Transferred READY reservation selection, automatic/paused take reuse, failed pre-commit candidate compensation and complete Play/Resume/Retry arm ownership to `ScoreStreamController`. The score view now exposes one bounded `arm_stream_take` port and source-geometry preparation.
- The controller is the only writer of armed/live serials, rollback snapshots and the selected owner for these routes; it uses the one source/rest queue and the same immutable preflight placement.
- Native recovery-batch orchestration, retained-painter lifetime and transitional forwarding properties still require extraction. No new tests.

### Implementation checkpoint U — distinguish queue serial from selected owner

- Corrected a shadowed local variable introduced during extraction of `arm_take`: `candidate_serial` is the selected source take; `self.serial` is the stream's monotonically allocated immutable generation. This preserves the original new-append detection and rollback validity across retries.
- No new tests. The inherited Godot syntax/behavior checks remain the acceptance gate for this refactor.

### Implementation checkpoint V — restore real embedded acceptance fixture

- Full native run [44634101804](https://github.com/tpepels/piano_teacher/actions/runs/44634101804) successfully **compiled and linked the real Godot GDExtension** on CPython 3.14. Its next step exposed a removed import in the existing fixture generator (`scripts.smoke_phase0` no longer exists).
- Repaired the existing `verify-embedded-production-local.sh` to generate the required eight-measure, two-hand MIDI fixture directly with `mido`; no additional test script or independent fake engine was introduced.
- Added `Main.current_state()` as an immutable-snapshot public port and migrated both existing native production journeys from their old direct `app.last_state` field dependency to that read-only port. Main's accepted state continues to have only one owner (`ApplicationStateInbox`).
- Full native/package replay is still pending after these source corrections; physical piano acceptance remains open.

### Implementation checkpoint W — recovery queue admission owner

- Moved full exact-deadline recovery preflight, reserved queue suffix withdrawal, plan identity deduplication, source/rest admission, partial failure compensation and recovery diagnostics from `NativeScoreView` into `ScoreStreamController.schedule_recovery`.
- `NativeScoreView.enqueue_recovery_queue` now only supplies authenticated source geometry through the public admission boundary. The queue's peer-layer clearance is a public operation. No parallel queue, independent musical decision or additional test was created.
- Remaining L02: remove transitional forwarding state accessors and separate retained painting/resource lifecycle from physical admission.

### Implementation checkpoint X — learner deletion keeps one evidence-capture owner

- Fixed a real shared-reference defect in `PracticeEngine.delete_learner_history`: the old code replaced `self.measurement` while `MidiIngress`, `AttemptSettlement` and the newly extracted `LearningEvidenceSession` still referenced the discarded capture.
- Added `LearningCapture.begin_fresh_learner_session` to establish a new run/session ID and durable session entry **in the existing owner object**, after deletion and stop. Every reader/writer retains the same authoritative capture. No second ledger or new tests.
- Resume, manual MIDI and interrupted-attempt physical acceptance remains open.

### Implementation checkpoint Y — native Listen and header acceptance corrections

- Full native run [44635120261](https://github.com/tpepels/piano_teacher/actions/runs/44635120261) **passed native GDExtension compilation, isolated MIDI generation, and embedded Godot/Python + real-score registration**. It stopped on the existing production UI acceptance: BPM and Settings were not vertically aligned. The original bridge smoke also printed `PIANO_NATIVE_STARTUP_FAILED` after a score ACK, because it had assumed every new piece skipped Listen; that is no longer true for the default Practice Flow.
- Centered the practice header context/navigation/BPM/Settings controls on one vertical row. Kept the existing assertion but included exact geometry in its failure diagnostic. Updated the existing native bridge smoke to explicitly enter Practice after the correctly pending Listen stage before testing its low-level start/pause/resume protocol; the normal Listen/Free/Tempo path remains reserved for production-scene acceptance.
- No new tests. Repeat native UI and package audit are still required for latest source.

### Implementation checkpoint Z — evidence queries and history status out of PracticeEngine

- Moved `learning_history_status` formatting and the independent SQLite/WAL read-only learning-statistics query/retention verification into `LearningEvidenceSession`. The engine now exposes only its locked current-fingerprint status port and a non-blocking statistics call.
- This preserves snapshot transaction boundaries, quantile computation outside the read transaction, learner identity and deletion-race validation. Evidence capture and querying share one domain owner; no new tests.
- PracticeEngine still contains transport commands and complex automatic continuation/assessment lifecycle and therefore Phase 5 is **not closed**.

### Implementation checkpoint AA — remove native-view mutable state forwarders

- Deleted the transitional writable forwarding properties for stream take key, pause owner/source, live/armed serials, rollback dictionary, acknowledgement flag, planned IDs/openings, and Retry placement. The controller is now the only owner/writer of those fields; the renderer reads only its public transport owner port where needed.
- Added bounded, read-only `stream_owner_status()` and `stream_has_take()` capabilities for runtime diagnostics. Existing production UI and native journey fixtures now use those ports and `admission_queue_generation()` rather than writing/reading private transport fields; assertions are unchanged.
- `NativeView` retains its internal `_stream_queue` bridge for retained rendering and one isolated test fixture. Painter/resource lifecycle and backend PracticeEngine/Main decomposition remain open. No new tests.

### Implementation checkpoint AB — real native admission acceptance and fail-closed bridge gate

- Full native run [44636775570](https://github.com/tpepels/piano_teacher/actions/runs/44636775570) passed extension compile, isolated two-hand MIDI and embedded Python/Verovio integration, but the **bridge smoke did not reach count-in** after switching to the new Practice stage and the existing UI smoke still required the retired speculative READY preloading route.
- Native bridge smoke now acknowledges the actual newly selected Practice score revision before requesting timed transport. The existing verification shell script now explicitly rejects `PIANO_NATIVE_STARTUP_FAILED` and requires `PIANO_NATIVE_REAL_SCORE_WORKFLOW_OK`; Godot's zero exit status alone can no longer produce a false success.
- The existing production UI smoke now measures the perpetual READY clock and the first **coordinator-authorized** source's immutable admission facts, with future-only/offscreen (or explicit empty-strip) placement. Existing retained-ink, pause/restart, audio cue and Resume checks remain in place. No new test was introduced; old assertions contradictory to the active playback contract were replaced by stronger source-authorization checks.
- Native/packaging acceptance remains open pending the next full run.

### Implementation checkpoint AC — verify the relocated standalone package runtime

- Extended the existing full production acceptance script to build the distributable `.tar.gz` (rather than stopping at an assembled-directory audit), extract it into a clean temporary location and launch its own `PianoTeacher` binary under an empty environment and isolated HOME.
- The bundled Godot/CPython bridge must publish `PIANO_PACKAGE_NATIVE_READY` from the real startup path; Python/extension load errors and absent success are treated as package failures. The archive's actual native shared library and launcher are checked after extraction. No separate test suite or simulated service was introduced.
- This completes the **verification procedure**, not the package's acceptance result: the full native run must reach and pass this gate before the checklist can be marked verified. The Kawai speaker, MIDI/USB and Bluetooth observations remain physical-only.

### Implementation checkpoint AD — retire feedback-message decision parser

- Deleted the no-longer-used `application.practice_flow.outcome_of` string-prefix parser. Production decisions already carry a typed `Outcome`; preserving a parser exclusively to satisfy an old test advertised an alternate message-based decision authority.
- Removed only that obsolete assertion from the existing `test_practice_flow_machine.py`; all typed state-transition assertions remain. No new test was introduced.
- This completes the residual O02 compatibility-path removal. Additional session-lifecycle/physical acceptance remains open.

### Implementation checkpoint AE — correct the remaining existing assertion indent

- Core run [44638697127](https://github.com/tpepels/piano_teacher/actions/runs/44638697127) found an `IndentationError` in `test_practice_flow_machine.py` after deleting its obsolete message-parser assertion. Corrected the indentation of the existing tempo-bound assertion; no assertion semantics were changed and no tests added.
- Prior compiled production changes were not the cause of this collection error. Latest existing core CI is required for this correction.

### Implementation checkpoint AF — eliminate direct glyph-cache mutation

- Removed `StatusHeadPreloader`'s direct write to `VerovioGlyphs._head_interiors`. A validated public `VerovioGlyphs.install_head_interior` accepts an identity-matched previously rendered Texture2D and owns its private cache.
- The preloader continues sharing equivalent masks across stage revisions without duplicating the expensive first-attack fill calculation; the glyph atlas owns all internal writes. No new tests.
- Further application/renderer decomposition is open until the remaining production cross-owner reads are eliminated and native journeys pass.

### Implementation checkpoint AG — one click-audio owner and accurate native smoke

- Extracted locally generated high/low metronome WAVs and the persistent `AudioStreamPlayer` from Main into `CountInAudioSession`, with a count of successfully started cues. The existing count-in coordinator still decides cue timing; no second countdown clock was added.
- Corrected existing native UI acceptance to require either a real scheduled **click** or a spoken cue. The default Practice Flow uses click + large number; Japanese voice playback is explicitly opt-in, so the old unconditional voice-count assertion was invalid. This continues to enforce audio scheduling, without claiming that a dummy headless driver proves audible speakers.
- Corrected isolated `native_bridge_smoke.gd` to validate catalog, real MIDI, Verovio geometry and exact Listen score revision ACK only. It cannot start the instrument without physical score admission; the embedded production-scene acceptance is the sole transport owner. `verify-native-bridge.sh` now requires `PIANO_NATIVE_REAL_SCORE_PREPARATION_OK` and rejects every explicit failure marker.
- Full UI and clean relocated package acceptance remain pending next native run. No new tests.

### Implementation checkpoint AH — one feedback delivery and acknowledgement session

- Created `PracticeFeedbackSession` as sole owner of the acknowledged backend `FeedbackEventInbox`, score-revision-bound `LiveMidiFeedback`, MIDI attack reaction and post-consumption acknowledgement sequencing. No UI state polling or scene composition code can independently acknowledge, drop or regrade an event.
- Removed the feedback event inbox, reaction instance and read/ingest/dispatch algorithms from `Main`; it now forwards score revision publications and samples the session once per visual frame. The backend's take identity, timestamp adjustment and sequence-gap reporting are unchanged.
- No new tests. The existing core and native production checks remain the verification gates.

### Implementation checkpoint AI — protect live source strips on Pause

- Full native UI run [44639590153](https://github.com/tpepels/piano_teacher/actions/runs/44639590153) verified compiled GDExtension, embedded Python, authentic two-hand MIDI, source geometry, authorized count-in, Play and Pause. It exposed a **real stream-ownership defect**: Pause removed the unexpired source of the current take before Resume.
- `ScoreStreamController.observe_transport` now supplies its authenticated `paused_owner` to the queue's existing protected-tail withdrawal policy. That current musical owner remains immutable and visible until natural expiry; separate safe speculative successors can still retract. If the paused owner cannot be identified, withdrawal fails closed rather than deleting unknown current music. No renderer-local workaround, second queue or new test was introduced.
- Continue to require full Pause/Resume native acceptance and the relocated package audit on this corrected source before closing either gate.

### Implementation checkpoint AJ — one frame-time native score presentation owner

- Consolidated the duplicate `NativeView.present_flow` / `present_clock` callers. The accepted-state owner `PracticePresentationSession` now exclusively projects the native score once per frame with a single `PresentationTimeline` world sample; `PracticeFrameCoordinator` only handles stage effects, progress markers, diagnostics and visible-note feedback.
- Main samples `visual_world` once per frame, then passes that same coordinate to both the presentation owner and outgoing-score runway instead of separately projecting the world twice. The graded transport remains the separate Python-owned musical clock.
- This removes conflicting queue/arm lifecycle evaluation from the frame-effects component. No additional tests. Native Play/Pause/Resume and full package acceptance must confirm the changed frame ordering.

### Implementation checkpoint AK — current Retry journey and single frame authority

- Native run [44640770507](https://github.com/tpepels/piano_teacher/actions/runs/44640770507) passed compiled bridge, embedded source, native Play/Pause/Resume and immutable world-flow checks; Moonlight failed because the old journey waited for removed `reverse/preparing` backend phases, although the new graphical coordinator had already authorized transport 3 and future-only source.
- Migrated the existing Moonlight acceptance route to the active graphical contract: monotonic world, authored rest, distinct committed transport identity, exact score revision, one authorized CountInPlan, visible and scheduled-audio count-in, and source admitted strictly to the right or on an explicitly empty strip with an immutable geometry witness. Listen/stage navigation checks remain intact.
- Removed the second snapshot-time `present_flow` invocation from `PracticePresentationSession.accept`. Stream reconciliation now happens once in `present_frame`; unloaded/reloading states continue projecting old clips until their natural expiry, preserving the continuous bar. No new test files were added.
- Re-run the existing native journey and package audit. No physical CA49/audio measurement has been conducted.

### Implementation checkpoint AL — distinguish the preceding gap from the following gap

- Corrected the existing native Retry witness: a future rest after the newly admitted source cannot count as its preceding silence. The acceptance now selects the nearest real rest that ends at or before the retry's source onset. The invariant still rejects a retry with no predecessor rest.
- The clipping calculation uses a single class-level admission import. No new tests or product policy changes.

### Implementation checkpoint AM — transfer all keyboard event routing out of Main

- Created `ApplicationInputSession` as the single semantic keyboard dispatcher. It owns modal-first source-picker capture, library search focus, press/release consumption and the key-to-intent routing via the existing pure `ApplicationEventRouter`. It emits typed navigation, Play/Pause/Retry/Listen/Stop and fullscreen/exit signals; the root scene only connects those ports to the same handlers used by visible controls.
- Main's `_input` and `_unhandled_key_input` now delegate to this session and only mark accepted events as handled. Source-picker pointer events remain available for normal GUI delivery. No other musical timing or backend action is independently decided in Main.
- No test additions. Existing core CI and the production keyboard/physical MIDI acceptance matrix remain the verification gates.

### Implementation checkpoint AN — move physical queue preflight and transport receipts to the ledger

- `NativeScoreView.transport_preflight_facts` now supplies measured source/header/staff geometry to `ScoreStreamController.preflight_facts`. Only the stream controller may snapshot unseen-strip withdrawals, peer-floor clearance, paused-owner facts and the live queue.
- Moved the full admission receipt computation (earliest printed ink, actual first-ink lead, source onset, online strip count and diagnostic publication) into `ScoreStreamController.receipt`. `NativeScoreView._transport_admission_receipt` is now a renderer-geometry delegation port and no longer reads the live queue.
- Removed a remaining independent view-level admission computation; no new tests. CI and native admission checks are still required on this revision.

### Implementation checkpoint AO — continuation and rest placement owned by the one stream ledger

- Removed the remaining musical placement/queue-peer decision algorithms from `NativeScoreView`: `earliest_continuation_world`, `empty_strip_onset`, `short_rest_geometry` and `announced_copy_onset` are now bounded delegations that supply measured pixels/clef header/rest duration to `ScoreStreamController`.
- The controller alone computes physical continuation starts, safe-tail previews, peer SOURCE/REST floors, preparation margins and the reuse onset of an already announced copy. Its Play/Resume/Retry/recovery paths call its own empty-strip implementation rather than routing another queue decision back through the renderer.
- All existing entrance geometry, rest-gap rules and offscreen margins are preserved. The view retains canvas painting and source-glyph measurement. No new tests.
- Phase 5 remains open because the renderer's retained-painter lifecycle, PracticeEngine orchestration and Main composition still need decomposition.

### Implementation checkpoint AP — independently run every existing native/product/package scenario

- The full embedded production runner no longer exits on the first failed UI/Moonlight acceptance: after a successful build it executes the existing bridge, generated-MIDI UI, Moonlight, Peace Piece, Chopin and clean relocated-package checks separately, logging each failure and returning an overall nonzero result only after all independent scenarios have run.
- Each scenario is executed in a fresh strict Bash subprocess to retain `errexit` inside its nested packaging and fixture functions, not the parent shell's conditional-invocation exception. The same isolated HOME/case-specific XDG directories and existing acceptance scripts are used. Native compilation remains a hard prerequisite.
- No new test cases, no bypassed failures and no automatic background retry. CI's native job now yields a complete failure matrix from one run, including packaging even when a UI scenario fails.

### Implementation checkpoint AQ — first complete native/repertoire/package run passed

- [Full CI run 44703830421](https://github.com/tpepels/piano_teacher/actions/runs/44703830421), tested at `89d364d1`, passed core Python CI, CPython 3.14 GDExtension build, embedded Godot startup, authentic MIDI/Verovio geometry, Play/Pause/Resume continuous native UI, Moonlight Sonata Retry/Listen/stage navigation, Peace Piece, Chopin Nocturne and the assembled standalone runtime package audit.
- This is a concrete **Phase 6 software acceptance result at that exact revision**, not acceptance of subsequent Phase 5 refactors or of a physical instrument/audio path. The improved runner now tests the extracted archive/launcher and continues through all independent scenarios even if one fails.
- A new full native run is being requested against current `main` to cover the subsequent event input, preflight, continuous-rest and queue-ownership changes; the CA49/USB/Bluetooth/speaker checklist stays unchecked.

### Implementation checkpoint AR — one live grading interpretation

- Moved live grading policy selection, per-note mark calculation error handling and pending-held-release projection out of `PracticeEngine._live_feedback` into the established `PracticeAssessmentPolicies.live_projection` owner. The engine only captures the currently bound score, source hand, tempo map, MIDI note snapshot and elapsed time, then requests the existing grading policy's projection.
- No alternative grader was created. The same fixed/tempo-mapped policy and hold tolerance are used; `LiveAssessmentPublisher` still alone emits changed per-note feedback events, and final verdict/mastery remains with assessment settlement.
- This reduces another backend policy responsibility inside the application facade. No tests added; existing core and native checks remain required.

### Implementation checkpoint AS — source preparation and concurrent fingering leave PracticeEngine

- Added `SourcePreparationSession` as the source/curriculum/fingering preparation owner. It reads and imports MIDI, fingerprints the exact bytes, runs the original Node/ONNX fingering inference concurrently with course compilation, reads Fukuda learning evidence and restores saved progress under the existing short state lock. Only a fully prepared `PreparedSource` can be published; neither an importer failure nor a fingering failure replaces an active score.
- `PracticeEngine.load` now retains the outer fingering/correction serialization and the single atomic state-locked source commit. The preparer receives current explicit dependencies rather than a mutable engine pointer, preserving injectable preprocessors and code-owned score revisions. MIDI timestamps, lesson selection and transport admission are unchanged.
- Reduced the backend application's source-import/parallel-preparation implementation substantially. No new tests; the existing Python and full native score-load checks remain required.

### Implementation checkpoint AT — retained CanvasItem lifecycle leaves NativeScoreView

- Introduced `RetainedNotationPool` as the sole allocator, precompile-pool owner, invalidation manager and releaser of the authentic first source, reusable measure strips, rest strips and annotation overlay. `NativeScoreView` now exposes read-only rendering handles and delegates retained readiness/compilation publication and pool resizing; it does not allocate or free those nodes.
- The existing `ScoreStreamController` retains sole queue/serial/transport ownership. The view continues to own glyph measurement and CanvasItem painting, the pool owns retained resources, and Godot's only `retained_ink_compiled` signal is emitted by the view outside draw notifications.
- The old pool fields cannot be independently assigned by a renderer consumer. No new tests; the real native rendering/glyph and package checks remain the verification gate.

### Implementation checkpoint AU — clean extracted archive and complete repertoire checks passed

- [Full production run 44705537079](https://github.com/tpepels/piano_teacher/actions/runs/44705537079), tested at `7008a9aa`, passed core tests and every independently reported native case: embedded Godot/Python/GDExtension, score/Verovio source, production Play/Pause/Resume, Moonlight Retry/Listen/stage navigation, Peace Piece, Chopin and the **clean relocated standalone archive's executable startup**. The runner continued across cases and reported no failures.
- Later Python source preparation and native retained-pool decomposition also passed the existing core CI at [44706877402](https://github.com/tpepels/piano_teacher/actions/runs/44706877402), but this does not parse and execute the new Godot retained-pool source. Initiating the same full native/software/package acceptance once more at the current revision.
- Phase 5 and the physical portion of Phase 6 remain open. Software checks do not constitute Kawai USB/Bluetooth, speaker latency, nonheadless install or real performer mastery acceptance.

### Implementation checkpoint AV — single snapshot-to-musical-beat projection in Godot

- Removed Main's duplicate `VisualTransportClock.matches` / `score_beat` fallback algorithm. Metronome and control callback `_transport_beat_at` now delegates to the existing `PracticePresentationSession.transport_beat` owner; before session construction there is only a static published-beat fallback, never another estimated clock.
- The Python MIDI grading clock remains authoritative and unchanged, and the global visual world position still comes from one forward-only presentation timeline. No additional tests.
- Physical count-in and timing acceptance remains open.

### Implementation checkpoint AW — freeze current software candidate for full acceptance

- This checkpoint fixes the software candidate for one complete opt-in native run covering the newly extracted SourcePreparationSession, RetainedNotationPool, single presentation/beat projector, queue-owned preflight/receipt/continuation, all existing musical repertoire journeys and the clean extracted package launcher. Run all independent cases, collect their actual results, and leave any failed cases explicitly open.
- No new automated tests or hidden compatibility transport were introduced. Hardware-specific CA49, USB, Bluetooth, nonheadless speaker output and precise audiovisual drift remain manual-only and unverified in this environment.

### Implementation checkpoint AX — source-level server.py dependency/ownership audit

- Examined all 158 PracticeEngine method/property definitions and the ~99 mutable fields initialized at startup, inspected the largest start, Resume, Retry, recovery, full-attempt settlement, continuation and state snapshot methods and the actual implementation of PlaybackCoordinator, AttemptSettlement and TeachingContinuation.
- Published the [PracticeEngine extraction audit](practice-engine-decomposition-audit.md): ownership table, overlapping setters/state, engine-pointer cycle through playback admission, private transport access, durable settlement hazards, and a dependency-ordered migration plan. This is evidence against the current source, not the historical 19 November line references.
- Next work is to implement the bounded state/ownership transfers, not add forwarding functions or claim Phase 5 done because a single file is shorter.

### Implementation checkpoint AY — transport-owned retry, preview and preparation gates

- Replaced all PracticeEngine reads/writes of VisualTransport's private `_preview_loop_pending`, `_retry_previous_pass` and `_preparation_pending` fields with bounded public semantic facts and operations. Only `VisualTransport` can now mutate those three lifecycle flags; MIDI ingress and passage progression consume its observed state.
- Existing source preparation, graded retry and continuous-rest timing semantics are preserved. No new transport state cache or second scheduling authority was created.
- This removes a direct cross-owner field mutation found in the full server.py audit. Existing CI and native passage loops remain the verification gate.

### Implementation checkpoint AZ — playback coordinator can no longer hold engine authority

- Removed `PracticeEngine` arguments from every `PlaybackCoordinator` operation and replaced them with frozen `PlaybackSourceFacts` and `PlaybackRuntimeFacts` (source revision, hand, source bounds, bar/meter, tempo, current timeline and input grading gate). The coordinator cannot mutate foreign state or infer a second start-time clock.
- A bounded `commit(intent,receipt)` callback activates the graded take once, `capture()` independently verifies the post-commit musical state, and `abort(reason)` rolls back mismatched starts. A separate `notify_failure(reason)` port handles failed displayed scores. In-process dispatcher passes these exact ports under the existing engine lock.
- Existing source-bound request, reserve, present, withdraw, fail and state/timeout idempotency remain in the original coordinator. No new tests or engine-pointer compatibility branch. This resolves the audit's highest-risk circular dependency.

### Implementation checkpoint BA — one attempt-scoped state owner and atomic reset paths

- Introduced `AttemptRuntime` as the sole storage owner for seventeen related fields: recorder, pending complete/rolling assessments and BPM, feedback marks, persistence failure, performance review, retry/recovery and consecutive trouble state. The engine no longer has independent writable fields for them.
- `PracticeEngine._open_take` now calls `AttemptRuntime.begin_take`; `_stop` calls `reset_for_stop` once **after the authoritative evidence interrupt/flush**; trouble-history resets use the same owner. Final assessment marks and review completion use explicit state-install operations rather than independent writes scattered through the main completion method.
- Existing tests that intentionally inspect or inject a live recorder/pending result were migrated to `engine.attempt` without changing assertions. No new tests, compatibility shadow fields or replacement of the shared LearningCapture.
- Settlement still owns durable progress/evidence; the attempt object owns only the lifetime of transient grading/retry state. Remaining `PracticeEngine` orchestration must continue to move before L01 closes.

### Implementation checkpoint BB — preserve cross-attempt recovery streak and repair old assertion

- Core run [44715763141](https://github.com/tpepels/piano_teacher/actions/runs/44715763141) reported 318 passed, 17 skipped and one obsolete direct `second.recorder` assertion. Migrated that existing assertion to `second.attempt.recorder`; no test was added or disabled.
- Corrected the attempt-domain boundary discovered during review: the consecutive two-take trouble key/count must **survive** Stop/Retry. Moved them from `AttemptRuntime` into `RecoveryStreak`, whose explicit `record` and `clear` operations are driven only by the teaching transition or stage change. `AttemptRuntime.reset_for_stop` now clears only genuinely take-scoped recorder/evidence/review state.
- Existing CI must confirm the full retry/reconnect behavior; headless CI still does not certify the CA49 physical note path.

### Implementation checkpoint BC — future stage identity and native preload acknowledgement have one owner

- Moved source-identity-safe next-stage selection, serialized ahead-of-time engraving, staged-score labels, native compilation failure matching, exact revision acknowledgement and farther warmup into the existing `TeachingContinuation` / `FutureScore` owner. `PracticeEngine` no longer independently chooses or validates multiple future-stage revisions.
- Removed the writable `_future_stage_ready` and `future_score` forwarding properties. Native preload failures and the prepared-published flag are now stored on `TeachingContinuation`, alongside its reservation and acknowledged identity. The engine retains only the already-authorized settlement timing effect after the expected asset becomes ready; no independent preloader deadline was introduced.
- This shrinks the `server.py` stage/preloading section while keeping selected source metadata, failure messages and future handoff behavior. No tests added.

### Implementation checkpoint BD — preserve original curriculum projection import

- Corrected the moved `manual_progress` import to its original `teaching_course` owner. The new TeachingContinuation asset selector must use the same existing manual course projection as PracticeEngine previously did; importing it from `teaching_manual` was invalid.
- No test or lesson policy changed. Latest core CI must validate the integrated relocation before native acceptance.

### Implementation checkpoint BE — all guided and graded completion seals belong to AttemptSettlement

- Moved guided-completion capture sealing plus its typed decision commit into `AttemptSettlement.seal_guided_preparation`. PracticeEngine retains the error handling that preserves/resumes the same teaching exposure when a durable write fails, and still accepts the single result returned by that owner.
- Moved full-passage and focused/performance evidence sealing, immutable verdict capture, mastery-eligibility annotation and immediate focused settlement into `AttemptSettlement.seal_completed_take`. The method returns only whether a decision was settled now; the full-passage teaching decision stays pending for its already-announced transition, preserving the existing atomic staged handoff.
- This removes a second durable evidence writer from the engine without creating a parallel settlement transaction or changing grader selection, source identity or saved progress. No new tests.

### Implementation checkpoint BF — guided score source and flow step delegated to their owners

- `GuidedSession.display_phrase` now owns source-safe guided fragment selection, original bar/note identity and cached fragment reuse. The engine supplies only its explicitly selected phrase and guided range.
- `PracticeFlowCourseSession.execute` returns one frozen `FlowStepEffect` (typed Listen/Free/Tempo step, BPM, feedback text and next action). PracticeEngine applies that effect and no longer constructs rival labels for the same course decision. No new tests.
- Core and native checks remain the integration gates for these owner migrations.

### Implementation checkpoint BG — one authored next-count-in tuple from AttemptProgression

- Removed the two independent Engine implementations of upcoming full-bar count-in duration and meter. `AttemptProgression.next_count_in` now returns one pair `(beats,meter)` from the selected original authored starting bar, reusing the already-active bar on Pause/Resume and preserving the existing scheduler/compound-meter calculation.
- Backend snapshots and PlaybackSourceFacts use the same AttemptProgression bar-count authority; the engine's public getters are bounded projections without a second policy. No new tests or independent clock.

### Implementation checkpoint BH — one completion grading/settlement boundary

- `assessment_settlement.complete_grading_and_settlement` now owns the complete graded-take transition: one source-mapped assessment, one full/focused/performance route, one performance summary, one typed teaching-decision preparation, and one `AttemptSettlement.seal_completed_take` call. The immutable `CompletedTake` result carries the selected decision, optional policy response, feedback projection and actual settlement result.
- `AttemptRuntime.hold_full_result` records the one pending source-tempo result *before* its teaching decision is prepared. The original `PracticeEngine._complete_attempt` now requests this transaction and applies the one returned presentation/recovery effect; `_finish_full_passage` no longer reinitializes the pending result. No second grader or evidence writer has been introduced.
- No new tests. The same existing CI and native Play/Retry/automatic continuation tests must verify this integration before software acceptance is claimed.

### Implementation checkpoint BI — one course-owner settlement projection

- The Practice Flow course session now owns the stage-key-on-completion rule and the single projection from an already-decided typed flow outcome to stage, hands, BPM and user-facing status. PracticeEngine no longer reads the old/current FlowState to select another stage key after durable teaching settlement.
- This moves an actual overlapping course progression decision out of the engine while keeping LearningPlan the only source of the selected exposure. No tests added. The existing software suite still validates the exact one/two/three/four-bar moving windows.

### Implementation checkpoint BJ — source-clearance geometry leaves native CanvasItem

- Moved all ambient moving-meter barline coverage checks and source/rest clip exclusion into the stateless `AmbientMeterGeometry.exposed_lines` helper, consuming a read-only snapshot of the actual StreamController's queue. The native view only paints returned X positions; neither the view nor the helper changes a source's identity, deadline or immutable geometry.
- Moved the fixed cursor's binary-searched engraved-note/rest contour exclusions into `CursorInkClearance.exclusions`, also consuming the same immutable source snapshot and authored layout. The fixed playhead and glyph painter now share one native geometry result without `NativeScoreView` directly inspecting the live mutable strip FIFO.
- This reduces mixed queue/paint responsibility and leaves `NativeScoreView` closer to a rendering facade. No tests added; the existing native graphics and real repertoire journeys must verify the extracted drawing helpers.

### Implementation checkpoint BK — SettingsScreen commands and saved-device selection leave Main

- Added `SettingsInteractionSession` as the single translation of every SettingsScreen event (MIDI picker/range, tempo, exercise/diagnosis/learner/mistake strategy, history deletion/export, evidence retention, metronome, volume, fullscreen and exit) into a bounded command or intent. Statistics invalidation precedes deletion in this owner rather than being an incidental Main UI closure.
- Settings preferences and saved-device reconnect selection now belong to this session. Main only builds the scene, connects typed signals to the existing command coordinator, and applies the explicitly returned device selection. No alternative command route or setter is introduced.
- Reduced the main scene's settings-specific event handling without moving screen composition or changing application policy. No new tests; native Settings and MIDI-device acceptance must verify integration.

### Implementation checkpoint BL — MIDI callback ordering has one owner

- `MidiIngress.dispatch` now exclusively sequences hardware shortcut classification, any accepted range/command, the **post-command** transport-gate snapshot, successor suppression, original-timestamp boundary deferral, and final live/graded note delivery. It retains the original frozen incoming-take identity even when an accepted shortcut synchronously changes the session; a key cannot silently earn credit in a replacement take.
- PracticeEngine supplies only one immutable `MidiInputFacts`, a separate immutable `InputTransportFacts` port, the calibrated timestamp and explicit shortcut/grading-output callbacks. It no longer independently decides when to defer or deliver a note or repeats the MIDI ingress sequence.
- No new tests. Existing reconnect, shortcut, calibration, delayed-boundary and repeated-take tests remain the acceptance gate.

### Implementation checkpoint BM — remove final private transport read and run complete native candidate

- PracticeEngine no longer reads or writes any `VisualTransport._private` member. The one remaining preparation deadline is read via a public `preparation_deadline` fact on the original transport owner; no additional clock or timeout fallback exists.
- Reconciled the top-level Phase 5 status table with the actual current production file sizes and domain owners instead of the historical initial metrics.
- This `[native]` checkpoint requests the existing full production CI: Python core, actual Godot/GDExtension and embedded Python, authentic score rendering, Play/Pause/Resume, Moonlight Retry/Listen/navigation, Peace Piece, Chopin, and clean relocated package extraction/boot. All assertions must pass on this exact commit; hardware-specific CA49, USB/Bluetooth and physical audible timing are explicitly **not** asserted by headless CI.

### Implementation checkpoint BN — all durable attempt endings have one transaction owner

- Consolidated every remaining direct `LearningCapture.seal`, `persist`, `finish`, `interrupt` and `checkpoint` call in `PracticeEngine` behind the existing `AttemptSettlement` owner. This includes preview completion (never earns progress), rolling recovery, mid-piece checkpoints, Start/Retry interruption, Stop interruption/phase flush, defensive full-passage seal and exact-source Lesson Path reset.
- The reset operation still performs interrupt, interval flush, piece progress reset, Fukuda source-feedback reset, replacement course save and the reset event in **one original SQLite transaction**; Engine stops after it without repeating evidence writes. Rolling recovery still settles the immutable pending decision once, and `AttemptSettlement.settle` alone finishes the capture.
- All outcomes are still tied to the same current attempt and source identifier; no alternative evidence store, timeout path or grader was added. No new tests; explicit core/native acceptance required.

### Implementation checkpoint BO — score-bound fingering correction admission is asset-owned

- Moved the entire source/revision/native-layout/command-busy validation and source-identity payload creation for persistent fingering edits out of Main into `ScoreAssetSession.fingering_correction_request`. A stale popup cannot submit a correction to a new score, nor can a partially engraved revision accept a write.
- Main only forwards the selected source note/finger and the accepted UI snapshot, presents an explicit rejection, or submits the one bounded accepted operation. This removes another scene-owned source-identity policy decision without changing how fingering overrides are persisted or projected. No new tests.
- Core and Godot production tests remain the execution gate for the native score/fingering UI integration.

### Implementation checkpoint BP — playback status transition precedes snapshot publication

- Moved `PlaybackCoordinator.advance(frozen_facts)` from `PracticeEngine._state_snapshot` into the single backend `_update` clock-transition step. Native worker ticks now reconcile pending/active playback even when the UI stops requesting snapshots, and a snapshot cannot capture session state **before** invalidating or advancing the admission state that it then displays.
- `_state_snapshot` now reads the already-reconciled playback status without mutating its owner mid-serialization. Existing compatibility state polling still calls `_update`, so it uses the same transition ordering and continues to advance time when no dedicated timer exists.
- This removes a mixed-epoch state-publication bug without adding a clock, changing source deadlines, or writing tests. Existing backend/native CountIn/Play/Pause/Retry integration must verify.

### Implementation checkpoint BQ — bounded and observable full native verification

- The existing full native/package runner now announces `RUN` for every case and streams the actual subprocess output into GitHub Actions while retaining each isolated case log and the complete combined debug log. It no longer hides all progress until a case returns, which made long-running native and packaging work impossible to distinguish from a stall.
- Every case is additionally bounded by a 600-second outer `timeout` with termination and kill-after; individual authentic Godot, repertoire, package and relocated-boot deadlines remain stricter. A timeout records `FAIL` and runs the remaining independent scenarios rather than consuming the entire 55-minute CI budget.
- No case, assertion or acceptance path was skipped or added. This improves the existing Phase 6 verification procedure, not the application behavior.

### Implementation checkpoint BR — fingering correction and original-source projection belong to source owner

- `SourcePreparationSession` now validates finger values and source-note IDs, applies user corrections with the same `FingeringService` worker, and prepares complete original-piece fingering status. PracticeEngine remains solely responsible for generation-locked installation into the *current* LearningPlan after the expensive correction returns, never an obsolete captured piece.
- This removes an independent source-validation path from the application facade; load and correct still share their existing serialized fingering lock, and reopening/resetting a piece rejects stale in-flight corrections. No tests added.

### Implementation checkpoint BS — repair frozen-source admission guard found by native integration

- Full native [run 44729438368](https://github.com/tpepels/piano_teacher/actions/runs/44729438368) compiled the GDExtension and embedded Python and **passed the clean relocated package**, but Play/Pause/Resume, Moonlight Retry/Listen, Peace Piece and Chopin UI checks failed because `PlaybackCoordinator.advance` called `_valid_source(engine,...)` after retiring its engine argument. This caused a `NameError` whenever a graphical playback intent was pending. Core CI alone had not executed this graphical path.
- Fixed that final stale argument to the source-identity validation port's frozen `PlaybackRuntimeFacts` and reviewed the entire coordinator for any remaining live `engine` references. There are none. No extra clock, policy, tests or compatibility engine adapter were introduced.
- Trigger the complete native/playback/repertoire/relocated-package acceptance on this exact corrected source; physical Kawai, speaker and Bluetooth remain unchecked.

### Implementation checkpoint BH — eliminate duplicate stage-readiness state mutation

- Fixed an unreachable polling deadline in `TeachingContinuation.advance`: the source-awaiting branch now advances its bounded 100 ms readiness check; an actual native compilation failure still stops and reports the fault.
- Moved post-settlement preloader `prepared_published`/acknowledged-identity consumption into `TeachingContinuation.apply_settled_effect`. PracticeEngine no longer writes the same flags in both the handoff and non-handoff branches.
- The already existing `PracticeFlowCourseSession.settle_decided` remains the sole selected flow outcome owner. No tests added. Current native/software acceptance must be repeated after this change.

### Implementation checkpoint BI — passage outcome text is a pure projection

- Moved the remaining `PracticeEngine._teaching_instruction` decision-to-text logic and full-passage Retry/slowdown/mastery recommendations into `application.passage_outcome_presenter`. Its functions consume only the already-selected immutable `PendingTeachingDecision` and explicit numeric source facts, and cannot alter the plan, select another policy or schedule transport.
- `PracticeEngine._finish_full_passage` now applies one output string. Recovery timing and graded settlement are unchanged. No tests added; existing core CI is the regression gate.

### Implementation checkpoint BJ — preview-repeat musical rest owned by VisualTransport

- Moved the ungraded/no-MIDI preview repeat's complete authored-rest deadline calculation and continuation announcement out of `PracticeEngine._complete_attempt` into `VisualTransport.schedule_preview_repeat`. The owner uses the existing sole `MusicalScheduler` with the same measured-rest fallback and immutable next-source announcement; the engine supplies its measured source duration, BPM and reading horizon.
- `AttemptSettlement.finish_preview` remains the only evidence writer, so this path cannot earn a graded press, clean pass or mastery. Source playback and UI notices are unchanged. No extra clocks or new tests.
- Core and native acceptance will verify that repeated preview admission remains strictly future-only.

### Implementation checkpoint BK — correct the extracted presentation decorator

- Core CI found that retiring the static `_teaching_instruction` method accidentally left its `@staticmethod` on the following instance method `_finish_full_passage`. Removed the stray decorator, restoring the original bound-method signature; previously this raised `TypeError` at completion on flow/midi state-contract tests.
- No test was added, skipped, or weakened. Existing CI must pass again before any native/product acceptance claim.

### Implementation checkpoint BL — remove duplicate private guided-session property aliases

- Removed the writable `_guided_return` and `_guided_prepared` property forwarding descriptors from `PracticeEngine`. Every transition now reads and writes `GuidedSession.return_context` and `GuidedSession.prepared` on the sole existing guided owner, including retry reintegration, selected Free completion, source reset and snapshot capture.
- Public guided controls and source notation handling remain unchanged. This eliminates two more transitional engine properties and redundant mutation entrypoints. No new tests; existing guided/recovery CI must validate source behavior.

### Implementation checkpoint BM — full embedded/product audit on current architecture

- The existing core CI passed on `ea6f9432` ([run 44732402194](https://github.com/tpepels/piano_teacher/actions/runs/44732402194)), including the corrected static-decorator binding and the immutable continuation preview. The private guided-session alias removal is undergoing core verification.
- Trigger the existing **unmodified production native matrix** using the workflow's `[native]` release-check opt-in: GDExtension compilation, embedded CPython/Verovio/MIDI, graphical playback/pause/retry, Moonlight/Peace Piece/Chopin and relocated package startup. No new tests. Physical USB/Bluetooth and acoustic-latency observations remain a separate manual gate.

### Implementation checkpoint BN — move source-metrical retry rest lookup into notation ownership

- Removed the engine's inline traversal of source measure dictionaries, fallback meter and pickup/following-measure resolution inside graphical Retry. The pure `notation.practice_timeline.retry_preparation_rest_beats` now obtains the exact original source-metrical rest; `PracticeEngine` passes only the selected source model and authored restart beat.
- Eliminated the accidental local `selected` shadowing of the immutable teaching exposure in the rewind branch. No second scheduler or musical clock was created: `MusicalScheduler.reserved_retry_reverse` still computes the actual deadline.
- This is especially relevant to pickup measures and changing time signatures. No new tests; existing end-to-end mixed-meter/glyph and native Retry acceptance remain required.

### Implementation checkpoint BO — atomic source adoption lives with future-stage reservation

- Moved `PracticeEngine._commit_pending`'s direct read/validation of preloaded reservation and manual `FutureScore.adopt`, `prepared_published` and reservation cleanup into `TeachingContinuation.reserved_asset` and `consume_committed_asset`.
- The first operation validates the exact source/revision/identity **before** durable `AttemptSettlement.settle` without consuming the prepared source; the second promotes or invalidates the reusable asset only after a successful settlement, clearing the reservation exactly once. PracticeEngine now only installs the returned authoritative asset and advances its existing score revision/visual offset.
- This removes another duplicate future-score writer. No new tests; existing core/native settlement and prepared-handoff tests remain the acceptance gate.

### Implementation checkpoint BP — atomic Listen score/audio count-in authorization

- Moved the real Listen audio-versus-engraved-source CountInPlan equality check out of `PracticeEngine._commit_playback_intent` into `ListenSession.authorize_playback`. The owner now checks the selected score revision, prepared audio, exact bar/meter/beat plan and started flag *before* changing its `_started` state.
- A stale or mismatched graphical receipt cannot consume Listen or open a graded recorder. The engine performs only the subsequent authorized transport/evidence commit, preserving its existing one-time start and rollback path.
- No new test, alternate cue clock or decoder. Existing native Listen/Free/Tempo and core source-ack tests are the acceptance gates.

### Implementation checkpoint BQ — single AttemptRuntime pending/feedback transitions

- Consolidated the remaining scattered pairs of `pending_result`/`pending_assessed_bpm` mutations into `AttemptRuntime.clear_pending` and `finish_settlement`. Successful settlement clears the failure marker in the same operation; explicit Retry/restart keeps its original cancellation semantics.
- Source publication now uses `AttemptRuntime.reset_source_presentation`, feedback handoff uses `clear_feedback`, and rolling-grading snapshots are installed by `publish_live_marks`. `PracticeEngine` cannot accidentally clear only one half of an assessment result at these boundaries.
- The durable `AttemptSettlement`, source-specific feedback and cross-attempt `RecoveryStreak` remain independent owners. No new tests. Core and native completion/recovery assertions remain the acceptance gates.

### Implementation checkpoint BR — offline queue diagnostics cannot mutate the real history

- `NativeScoreView.offline_stream_queue` now returns a deep diagnostic snapshot, matching `stream_passes`, instead of exporting the mutable `ScoreStreamQueue.offline` Array. An external HUD/fixture can inspect retired source/rest history but cannot clear or reorder it.
- The renderer's private retained-pool and stream-ledger ports are unchanged. No new tests; native/packaged rendering acceptance is still required on this change.

### Implementation checkpoint BS — reconcile latest source and rerun the complete native matrix

- [Full native Actions run 44732784904](https://github.com/tpepels/piano_teacher/actions/runs/44732784904) passed against `dedc7bd5`: compiled Godot GDExtension, embedded CPython and source notation, live production UI Play/Pause/Resume, Moonlight Retry/Listen/navigation, Peace Piece, Chopin and the clean extracted standalone package/launcher audit.
- Subsequent source commits removed mutable guided aliases, consolidated exact measured Retry preparation, authoritative preloaded-score adoption and attempt-state clearing, validated Listen CountInPlan prior to consuming audio and made the retired offline FIFO public port read-only. [Core run 44733911571](https://github.com/tpepels/piano_teacher/actions/runs/44733911571) was green through the preceding AttemptRuntime update.
- Triggered a new opt-in `[native]` run from the current code to validate every existing software scenario again. No new test files; an app-visible success still cannot certify real MIDI cables, Bluetooth stability, speakers or timing offset.
- Phase 5 **remains incomplete** while `PracticeEngine` carries large command/continuation orchestration and Main/NativeView are not fully thin. Phase 6 is software-passing only on the tested old revision; current source and physical gates are separate.

### Implementation checkpoint BT — one authored source-meter selector for both retry paths

- Removed duplicate source-measure lookup from `VisualTransport.schedule_source_preparation` and `retry_preparation_rest_beats`. Both now call the pure `notation.practice_timeline.source_preparation_measure`, which resolves the same actual source/pickup/meter context and adjoining measure.
- Preview display and retry deadline still belong to the one VisualTransport/MusicalScheduler; notation owns only duration and silent measure geometry. This prevents the new source-metrical read and the existing transport reverse preparation from selecting different meters at the same source opening.
- No new tests or timing fallback. The existing mixed-meter, source-boundary and native Retry checks remain the acceptance gate.

### Implementation checkpoint BU — transport-owned cancellation and restart epochs

- Replaced the four recurring `next_at=0; announced_continuation=None` engine mutation pairs with the semantic `VisualTransport.cancel_continuation` transaction. The three locations that must preserve their existing rest/deadline while only withdrawing an advertised successor use `VisualTransport.withdraw_announcement`.
- Replaced two manual `paused=False; paused_at=0` pairs with `clear_pause_for_restart`. This is intentionally distinct from normal `resume()`, which must shift the authoritative run epoch; an explicit Restart instead abandons the paused clock without retiming old graded evidence.
- No deadline recomputation, second clock, or new tests. The remaining clock/assessment coordination inside PracticeEngine is not yet a thin facade; current core/native tests remain the integration gate.

### Implementation checkpoint BV — one physical MIDI grading resume gate

- Consolidated all three duplicate `resume_grading_after=0` / `resume_ignored_pitches.clear()` engine mutations in `MidiIngress.clear_resume_gate`. Starting a fresh take, stopping, or restarting cannot retain only half of a previous key-release suppression interval.
- MIDI Resume calls the ingress owner's `shift_resume_gate` and `authorize_grading_after` operations for its exact already-authorized deadlines, validating finite nonnegative times. Previously the engine could write the deadline directly while the MIDI callback separately owned its ignored held-key set.
- The frozen transport facts and existing musical clock remain authoritative; MIDI ingress only suppresses ungradable attacks/releases until its selected grading epoch. No new tests. Existing physical/journey CI remains the gate.

### Implementation checkpoint BW — migrate the original pure source-preparation mock to its owner

- Core CI on `ed372688` and `b266ceba` found one existing fixture `test_source_preparation_uses_nearest_authored_measure_and_absolute_deadline` monkeypatching `visual_transport.preparation_measure_descriptor`. The production path now correctly resolves the source meter through `notation.practice_timeline.source_preparation_measure`, which calls that module's descriptor.
- Updated only that fixture's monkeypatch import to the canonical notation module. All assertions of selected source bar, following meter, exact deadline, pending rewind and preparation geometry are unchanged; no test was added or skipped.
- Full core CI and current native acceptance still required.

### Implementation checkpoint BX — finish stream identity writes and retained reparent ownership

- `NativeScoreView.load_score` no longer invokes the private `ScoreStreamQueue.bind_score` or reads its private `last_error`; `ScoreStreamController.bind_source_identity` and `source_identity_error` are the sole bounded port for restoring offline source material across score reloads.
- The final direct `StreamLifecycle.attach_compiled` call in the renderer now belongs to `RetainedNotationPool.attach_compiled`, alongside the pool's already-owned CanvasItem allocation, precompile, invalidation and retirement. The native view only requests the prepared pool be attached before its visual projection.
- This removes two remaining non-painting writes from the view without changing clip source, world position, pause or retry. The renderer still reads the internal online source for efficient paint projection; it does not mutate queue membership. No new tests. Native compile/repertoire/package CI remains the acceptance gate.

### Implementation checkpoint BY — evidence phase selection belongs to LearningCapture

- Introduced frozen `CapturePhaseFacts`; `PracticeEngine._update_transition` captures its current musical/mode facts but no longer selects and writes pause, guided, preparation, count-in, active, preview, feedback or idle intervals itself.
- `LearningCapture.observe_phase` now owns that evidence projection, including precise closure of a running count-in at the scheduled activation timestamp (instead of the potentially late worker poll). The MIDI grading clock and musical scheduler are untouched.
- All existing intervals and source/attempt identities use the one existing capture ledger. No new tests; core timing/ledger and native playback checks remain required.

### Implementation checkpoint BZ — polling cadence and sparse discovery leave Main

- Created `ApplicationPollSession` as the sole owner of the 150 ms state poll, five-second context-dependent library/ALSA discovery, and 1.2-second library-health refresh. It consumes explicit read-only screen/device/health facts through narrow Callables and emits semantic request signals; it cannot change musical playback or an engine snapshot.
- Removed all three Timer creations, timer callbacks and their discovery rules from `Main._ready`. Main only connects existing backend request handlers and supplies the selected `state_timer` to `PracticeStatePresenter`.
- Preserved all exact intervals and the prior device-discovery suppression during an already-connected practice session. No new tests; Godot parse/native UI and package CI remain required.

### Implementation checkpoint CA — resumed source time belongs to VisualTransport

- Continued from verified source `12f50e66`, rather than replaying the earlier `619bc29c` work. [Core CI 44736734032](https://github.com/tpepels/piano_teacher/actions/runs/44736734032) passed; recent failed runs 44734763275, 44735018269 and 44735265422 all referenced the retired preparation helper in an existing fixture, already migrated at `d608ec3f`.
- Moved the held-note pause floor, source-time clamping, resumed source epoch and scheduled-admission timing out of PracticeEngine into VisualTransport and the pure transport command reducer. MidiIngress still owns the one graded-input gate; transport returns the exact gate to apply, without holding a duplicate gate.
- Existing baseline `bash scripts/test.sh` passed (335 Python tests, one skipped, Godot checks). This transport step passed `bash scripts/test.sh --python-only` (335 passed, one skipped). Native production validation remains due after integration. No tests added or changed.
- Ruling: use the existing audit/phase plan, existing tests, direct main commits and autonomous execution as explicitly requested; do not create a worktree, add tests or request another design approval. The referenced machine file `/home/tom/.codex/RTK.md` is absent; repository instructions were read directly.
- Remaining work: complete durable completion/publication, facade decomposition and public ports; rerun full native, repertoire and relocated package checks. Physical acceptance remains unverified.

### Implementation checkpoint CB — one pending result and durable completion transaction

- `fdf21b4b` implements checkpoint CA. This step removes the second writable pending assessment/BPM from AttemptRuntime: AttemptSettlement now exposes the exact pending decision's result and performed BPM as read-only facts.
- Moved complete-take grading/decision/sealing/settlement orchestration into AttemptSettlement; the assessment helper now only grades/projects. A cached immutable completion preserves the chosen grade through storage retries. No second decision or evidence writer remains in that helper.
- Full-passage settlement freezes a CommittedAttempt before source publication. Publication retries use its original source revision, prepared asset, duration and visual offset; applying the same receipt cannot increment the source revision/offset twice after the database already committed. AttemptRuntime applies review/reset display effects from that receipt.
- Updated the existing unplug fixture to prepare a real canonical assessment through the decision owner instead of writing the retired shadow pending field. No new tests. `bash scripts/test.sh --python-only` passed (335 passed, one skipped); integrated run also passed Python, with native extraction parser issues being corrected before full Godot verification.
- Remaining work: facade and continuation effects extraction, final owner audit, full native/package acceptance and documentation reconciliation. Physical acceptance stays unverified.

### Implementation checkpoint CC — Practice screen construction and layout owner

- `1028dd32` implements checkpoint CB. PracticeChrome now owns its widget tree, responsive layout, modal presentation and voice status; PracticeScreen consumes backend snapshots and handles interaction through semantic signals.
- Chrome is a composed VBoxContainer, retains no application/screen reference and stores no duplicate transport or teaching policy. Existing public widget observations remain available to preserve current UI contracts.
- Existing Godot checks passed after integration, including all Practice UI scenarios and source-marker assertions. The existing Python suite also passed (335 passed, one skipped). No tests were added; physical display/input behavior remains unverified.
- Remaining gates: renderer/stream, root scene and backend ownership commits; fix the fresh-review Free→Tempo authority and failed-journal teardown findings; full embedded production and package run.

### Implementation checkpoint CD — native source, drawing, binding and journal ownership

- `9c493ec1` implements checkpoint CC. NativeScoreView now composes ScoreEngraving (authentic source assembly/fit), ScorePainter (canvas/retained presentation), ScoreStreamController (the one FIFO/serial transaction owner), StreamTakeBinding (arm/ACK/Pause/compensation) and StreamRecoveryPlanner (identity-bound untimed placement). StreamGeometry carries frozen physical facts; no downstream admission executor receives the whole view.
- GlyphAssets owns authentic catalogs/images; GlyphHeadMasks owns derived status-mask caches; Glyphs only composes ink on a canvas. Retained CanvasItems bind their painter directly; no raw view or private method access is required.
- Removed dead announced-copy/automatic-horizon APIs and the old graded automatic claim of guided ink. Free publication remains explicitly tagged by its guided plan identity and cannot start a graded take. Fixed the actual guided consumer's nonexistent renderer property with scheduled_plan_opening(identity).
- Fresh review found failed-journal teardown could keep queue records while freeing their CanvasItems. Reset now journals every owner before retiring any clip and returns success through controller/view/asset lifecycle. On failure it preserves ink, binding, compiled assets and feedback, blocks replacement requests and reports the failure.
- Existing Godot checks passed against this integrated source (`GODOT_STARTUP_SYNTAX_OK`, every existing failure counter zero). Existing fixtures were migrated only from retired private queue/geometry/void-clear interfaces; assertions retained, no new tests.
- Full native production/repertoire/package execution remains due. Physical engraving/display, audio and MIDI acceptance remains unverified.

### Implementation checkpoint CE — Main is scene composition and application lifetime

- `acb26db9` implements checkpoint CD. Main now creates/wires scenes and owns viewport/application lifetime. ApplicationStateInbox sequences accepted command/poll state once; PracticePresentationSession samples/project frames and sequences score publication; ApplicationPollSession owns polling/discovery cadence.
- Existing command, settings, library, navigation, audio, lesson and MIDI owners now receive their own replies and apply their own effects. Shared InProcessRequest decoding replaces callbacks into Main. Settings→MIDI presentation references avoid a RefCounted ownership cycle.
- Removed obsolete root property/callback forwarding and moved startup reopen/fingering/control request lifetime to their corresponding owners. The existing smoke-facing observation/command ports remain intact.
- Existing Godot syntax/UI/ownership/lesson/score checks passed (`GODOT_STARTUP_SYNTAX_OK`). The existing snapshot-consumer fixture now inspects the actual inbox/presentation/command owners instead of the deleted Main._on_state method; its schema assertion is unchanged, no new test.
- Remaining software gates: backend lifecycle/effect integration, final source review and full production/repertoire/relocated-package run. Physical acceptance remains unverified.

#### Phase 6 acceptance matrix

| Required acceptance | Current evidence | Status |
| --- | --- | --- |
| Python, Godot parse and existing isolated checks | [GitHub Actions 44625683191](https://github.com/tpepels/piano_teacher/actions/runs/44625683191) passed at `27f7f580`; existing core checks only | **Verified for tested source revision; native/full physical journeys open** |
| Actual embedded Python/Godot native boot + authentic score | [Full native run 44703830421](https://github.com/tpepels/piano_teacher/actions/runs/44703830421) passed source, Play, Pause, Resume, Moonlight Retry/Listen, Peace Piece and Chopin at commit `89d364d1` | **Passed at tested revision; later refactors pending** |
| Pathétique Listen → Free → Tempo near 52%, notes visible and admitted before grading | Source transactions wired; exact user reproduction needs live runtime | **Not verified** |
| Bars 1; 2,1–2; 3,2–3,1–3; 4,3–4,2–4,1–4; sliding at max width 4 | Authoritative generator and progress identity updated; no physical MIDI observation | **Source implemented; live acceptance pending** |
| Cross-bar holds, sparse bars, changing meter, very slow BPM, long score | Source-safe windows and count-in map implemented; full native journey not executed | **Not verified** |
| Pause, Resume and Retry including counted syllables and lowest/highest physical-key shortcuts | Shared route and count-in session integrated; actual Kawai timing not measured | **Not verified** |
| Auto retry/recovery, preloaded lesson, interruption/close/reopen, saved progress | Source-bound admission + durable settlement implemented; physical and crash/restart cases outstanding | **Not verified** |
| Self-contained packaged release | [Native run 44705537079](https://github.com/tpepels/piano_teacher/actions/runs/44705537079) passed strict relocated archive extraction and bundled Godot/Python entrypoint boot at `7008a9aa`; current retained-pool/source-preparation changes need repeat | **Software package passed at tested revision; physical desktop install open** |

**Existing acceptance commands** (do not add new tests):

```bash
bash scripts/test.sh
bash scripts/verify-embedded-production-local.sh --without-package
bash scripts/verify-embedded-production-local.sh
```

The native runner requires Godot 4.7.2, Python 3.14 dependencies and a compiled matching GDExtension. Running the existing native scripts on a configured Linux machine and physically testing the Kawai are still required. All incomplete items stay open; CI success by itself must not close them.

#### Physical acceptance protocol — not executed in CI

These are manual owner observations, not new automated tests. Record the app commit, host OS, MIDI device, connection (USB/Bluetooth), actual speaker/headphone output, source MIDI fingerprint, selected source measure/window, BPM, calibration offset and a timestamped debug ZIP for every failure. Do not mark a case passed merely because an API snapshot claims the correct state.

- [ ] **USB MIDI startup and reconnect:** select the Kawai CA49, play/release and sustain real notes, unplug/reconnect mid-session, verify the correct input device and one active take without duplicate callbacks or stale grading.
- [ ] **Bluetooth MIDI startup and timing:** perform the same notes with Bluetooth, calibrate several rounds, reject outliers and verify that timing offset improves observed attack judgements, including after reconnect.
- [ ] **Measure-first course:** demonstrate 1; 2, 1–2; 3, 2–3, 1–3; 4, 3–4, 2–4, 1–4; 5, 4–5, 3–5, 2–5. Record the actual graded source attacks and confirm every window stays at four authored bars maximum.
- [ ] **Hand progression:** for each window, Right → Left → Together when those hands have notes. No skipped or combined hand earns mastery without an actual clean attempt.
- [ ] **Listen and Free:** Listen plays the selected window at source tempo with actual sound, visible moving notes and no grading; Free awaits each real key at a fixed playhead, shows a red wrong-note hint, and advances only after the correct key.
- [ ] **Tempo and count-in:** start at 50% source BPM, increase by 10% of target after clean takes, follow two-failures slowdown/return to Free and require two consecutive clean source-tempo attempts. Check audible click and large numbers, plus optional speech when enabled; verify voice/click and playhead timing on real speakers.
- [ ] **Monotonic score and controls:** Pause leaves the world clock moving with no new source, Resume admits notes strictly in the future, Retry preserves every exposed strip's immutable world position and ends each take with the authored rest. Check lowest/highest piano shortcuts.
- [ ] **Cross-bar and difficult notation:** use an authored sustained/tied note across a window boundary, sparse measures, changing meters (including compound), slow BPM, beams/slurs, and a long Chopin score. Verify release and grading don't include later-window attacks.
- [ ] **Automatic continuation and recovery:** confirm failed takes, repeated recovery, simplified Coda/Fukuda announcement when offered, preloaded stage handoff, count-in reuse and no “Score not ready” race with visible/graded music.
- [ ] **Saved interruption and progress:** stop mid-take, close/reopen, resume the same moving window in Free, preserve achieved windows and forbid mastery from partial/interrupted takes.
- [ ] **Audio/video witness:** capture audible acoustic or line-out clicks/notes together with the screen/playhead using an external recording; measure drift and latency under load. Headless Dummy audio-driver observations are insufficient.
- [ ] **Packaged desktop on a clean machine:** install and launch the built archive without the development venv or system Python project dependencies, perform a real MIDI session, and confirm user data/graphics/audio persist across restart.

No item above has been checked on physical hardware in this environment. The owner must record pass/fail and any corresponding corrections before Phase 6 is closed.

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

## Dependency-ordered implementation plan (authorized by subsequent user instruction; tracked above)

**Phase 0 — Freeze domain and acceptance contracts.** Define the exact typed PracticeWindow, TeachingOutcome/Effect, AssessmentVerdict, PlaybackTransition, CountInPlan, PresentationTimeline and score admission receipt contracts. Map their current producers/consumers, migration strategy for progress, and event order. Resolve how cross-bar holds behave and which later bars may be dim context. This phase is complete only when every reader/writer and obsolete route is accounted for.

**Phase 1 — Consolidate teaching and assessment authority.** Make the teaching reducer the sole owner of progression, remove outcome-from-message parsing, unify all assessment consumers on the same verdict and settle exactly one decision via Unit of Work. Integrate manual controls, adaptive Coda/Fukuda, progress persistence and interrupted attempts. Delete secondary mutations/counters, not just add an adapter.

**Phase 2 — Implement measure-first progression end-to-end.** Select and persist PracticeWindow identity and a first-bar active range; integrate it into generated courses, Free and Listen, all note IDs, source-safe clipping, score caching, playback admission, MIDI grading, recovery, tempo ladder, hand changes, context rendering and saved-resume migration. Add deliberate prefix growth across the phrase, links and final performance. Phase 2 is complete only when there is no four-bar initial active Tempo exposure and no hidden later-bar grading.

**Phase 3 — Finish one playback transition and count-in authority.** Replace the old Restart/routing and automatic handoff branches with typed PlaybackTransition execution; unify the count-in schedule and partial Resume; remove score-preloader timing, speculative deadlines and competing start/retime paths. Keep the native perpetual visual clock and immutable exposed notes. Complete UI/MIDI/Listen/Free/Tempo/recovery/hand-off coverage.

**Phase 4 — Deterministic presentation and physical admission.** Implement one PresentationTimeline/Projector with exact forward/inverse mappings; migrate all frame, reserve, recovery, audio and tempo-change consumers; remove independent projection/slow-debt correction logic. One public gateway owns physical clearance, reservations and rollback; one stage owner owns promotion.

**Phase 5 — Decompose the three oversized production classes.** Transfer all fields, methods and side effects from server.py, view.gd and main.gd into the owner components above. Keep only thin composition facades with explicit ports. Remove old code and stale private-field access in the same phase, not in a deferred cleanup. Preserve persistence, native rendering, keyboard, audio, fingering, navigation and diagnostics.

**Phase 6 — Retire obsolete contracts and validate the complete product.** Rewrite the active architecture docs; mark historical decisions superseded. Run existing Python/Godot CI and production native-build checks, then conduct full physical MIDI, timing, count-in, Listen/Free/Tempo, low BPM, changing meter, long score, Pause/Resume/Retry, sparse measure, cross-bar sustain, recovery, preloaded transition, crash/restart and saved-progress acceptance. The prior request to write no new tests is respected by **this audit**: no test or application code is created here. Any later test-suite expansion is a separate implementation decision.

No phase is complete while an old second authority, old shortcut or duplicate projection is still active. Refactoring must preserve full behavior, not just pass isolated unit tests.

## Baseline evidence versus assumptions (archived; source baseline 9a01a9b7)

- **Confirmed in source:** phrase generation is 2–4 bars; Free completion selects the entire phrase; the timed intent lacks an end; the three largest files and their responsibilities; outcome parsing; conflicting pass properties; duplicated countdown and preloader timing paths.
- **Inferred product expectation:** the first Tempo exposure should be one bar with gradual prefix growth because the learner reported that seeing/receiving all four at entry is wrong. The exact later growth order above is a recommended design, not a claim about existing behavior.
- **Not established without live playback:** how many measures are simultaneously visible within a given viewport, audio and physical MIDI latency, actual display drift in a particular piece, or every possible asynchronous ordering failure. These remain acceptance scenarios rather than claims of reproduced defects.
