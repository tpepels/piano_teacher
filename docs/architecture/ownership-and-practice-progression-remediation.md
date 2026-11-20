# Ownership, lesson-window and large-file architectural audit

**Status:** Implementation underway on `main`. This file tracks actual code commits; unfinished items remain explicitly marked. The detailed audit below is historical baseline evidence; it is not a description of current source paths or unresolved behavior.  
**Source baseline:** [main at 9a01a9b7](https://github.com/tpepels/piano_teacher/tree/9a01a9b7d9434ae6a3ef7bc72fd6844222d718ef), 19 November 2026.  
**Scope:** Practice Flow, learning/assessment, playback and score admission, presentation timing, and the three largest first-party production source files.  
**Goal:** One authoritative owner for each domain decision; explicit typed boundaries; no independent recomputation of a decision downstream; preserve the continuous native score and all existing capabilities.

See also the current source-based [PracticeEngine responsibility/dependency audit](practice-engine-decomposition-audit.md), which distinguishes actual mutable owners from wrappers and defines the dependency-ordered extraction work.

## Implementation progress

**Implementation branch:** `main`. **Tests:** No new tests introduced. Existing fixtures were migrated to current public admission/score ports and one legacy parser assertion was retired. Core CI passed on `eee14c54` ([run 44637473989](https://github.com/tpepels/piano_teacher/actions/runs/44637473989)); newer source CI and full native verification are tracked below, not assumed green. Physical audio/MIDI cannot be certified by headless runs.

| Workstream | Status | Notes |
| --- | --- | --- |
| Moving-window curriculum / P01 | INTEGRATED; PHYSICAL ACCEPTANCE OUTSTANDING | `practice_windows.py` selects n, n−1..n, n−2..n, n−3..n (max 4) and emits real source-bounded course exercises; independently identified windows, versioned saved progress and separate final exam; existing CI passed on `f1d3385` |
| Typed course outcomes / O02 | SINGLE TYPED PRODUCTION PATH; LEGACY PARSER REMOVED | `TeachingDecision.flow_outcome` carries `Outcome` directly through course/engine; `outcome_of(message)` and its obsolete parser assertion have been deleted |
| Unified assessment verdict / O03 | INTEGRATED ACROSS TEACHING, EVIDENCE AND SNAPSHOTS; LIVE CHECK OPEN | The selected verdict now drives course progression, recorded acceptance, UI summary and durable trouble clearing; raw grader acceptance is retained under a separate diagnostic field; non-graded legacy adapters remain distinct |
| Unified playback transitions / O01, O04 | GRAPHICAL COUNT-IN SINGLE-TAKE PATH INTEGRATED; LEGACY AND PHYSICAL ACCEPTANCE OPEN | Immutable PlaybackTransition and CountInPlan are accepted once; metronome uses take-keyed authorized segments through Pause/Resume, rejects mismatched deadlines and does not invent unadmitted graphical countdowns; headless compatibility and hardware acceptance remain |
| Asset admission / O05, O08 | ONE PHYSICAL PREFLIGHT + STREAM OWNER; PAINTER COUPLING OPEN | ScoreTransportReservation requires frozen physical facts; ScoreStreamController owns Play/Resume/Retry, recovery, immutable source/rest append, ledger/rollback/serial identities; ScoreSceneController owns renderer promotion. NativeView retains in-process drawing/queue bridge and painter lifecycle |
| Deterministic presentation timeline / O06 | INTEGRATED IN GODOT; PHYSICAL VALIDATION OPEN | Versioned PresentationTimeline owns world-position/rate epochs, Free holds and hypothetical forecasts; ContinuousScoreFlow delegates; Main no longer retroactively integrates tempo debt; native audio/MIDI acceptance unverified |
| Architecture docs / O07 | CURRENT ENTRYPOINTS RECONCILED; REFERENCE SWEEP OPEN | ROADMAP and documentation index now point to the actual moving-window policy and current playback/ownership contracts; ADR-0001 and playback coordinator document authority; old ownership contracts marked historical. Deeper document cross-reference sweep remains open |
| Decompose server.py / L01 | PARTIALLY DECOMPOSED (~3,572 lines); LIVE ORCHESTRATION REMAINS | SourcePreparationSession owns source import/parallel fingering and curriculum preparation. LearningEvidenceSession owns rules and history. AttemptSettlement, MidiIngress, ScoreStatePublisher, PracticeFlowCourseSession, playback coordinator and assessment policy are domain owners. PracticeEngine still has oversized transport/assessment/control orchestration to transfer |
| Decompose native/view.gd / L02 | SUBSTANTIALLY DECOMPOSED (~1,151 lines); PAINTER FACADE NOT THIN | ScoreStreamController exclusively owns queue, source/rest append, Play/Resume/Retry/recovery, preflight, receipt, peer and rest clearance. RetainedNotationPool owns retained source/rest/annotation CanvasItems and compilation lifecycle. View owns glyph measurements, actual painting and public geometry ports. More renderer painting code can be separated |
| Decompose main.gd / L03 | SUBSTANTIALLY DECOMPOSED (~1,060 lines); COMPOSITION ROOT NOT THIN | ApplicationInputSession owns key capture/dispatch; ApplicationStateInbox owns stale-poll rejection/snapshots; PracticePresentationSession one frame-time score presentation; PracticeFeedbackSession owns feedback consumption/ACK; CountInAudioSession owns click playback; navigation, diagnostics and score sessions own their domains. Main still composes screen widgets and translates external commands |
| Existing CI/native integration | FULL SOFTWARE NATIVE + CLEAN PACKAGE PASSED AT `7008a9aa`; CURRENT CORE CI GREEN | [Run 44705537079](https://github.com/tpepels/piano_teacher/actions/runs/44705537079) passed all native/repertoire tests and clean-relocated-package audit at `7008a9aa`. [Core run 44706877402](https://github.com/tpepels/piano_teacher/actions/runs/44706877402) passed for retained-pool refactor. Newest native run on current sources is needed. Physical hardware not verified |

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
