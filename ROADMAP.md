# Piano Teacher — single development roadmap

**Authoritative plan • 2026-11-04 • MIDI input only**

This is the sole active phase plan. Other `docs/` files are technical
specifications, dated research evidence, verification protocols or archived
historical records. They do not define competing implementation phases.
The replaced October roadmap is archived at
[ROADMAP-2026-10-historical](docs/archive/development/ROADMAP-2026-10-historical.md).
[Documentation index](docs/README.md) explains which sources are authoritative.

## Product contract

One Godot 4.7 desktop application, one embedded CPython practice engine and
a typed in-memory GDExtension command queue. No network service, HTTP
adapter, Qt UI or compatibility facade. MIDI (.mid/.midi) is the **sole user
input**. Internally generated MusicXML is an engraving interchange, not
another input backend. The canonical MIDI source IDs, authored durations,
selected `ExerciseStage` and stage-specific tempo policy must agree across
native notation, Listen, visual transport, physical MIDI grading, feedback
and saved progress. The unchanged original MIDI is the final performance.

New installations select adaptive **Coda + Fukuda**. Existing explicit
preferences are respected. Lessons are meaningfully transformed from
source material, not editorial renamings of the same notes. No artificial
mastery from visual previews; three accepted full-target performances required
(the exact warning allowance is defined by `Assessment.passed`, below).

## Phase status and acceptance gates

| Phase | Scope | Status as of this document | Exit evidence |
|---|---|---|---|
| **0 — Foundation** | MIDI import, library, native startup, one process | **Software acceptance complete**: cold production UI, saved real MIDI, native notation and Play/Pause/Resume passed in CI at `aecbb09` | [Production scene and embedded runtime evidence](https://github.com/tpepels/piano_teacher/actions/runs/41663899894) |
| **1 — Practice engine** | Count-in, transport, recovery, retry, tempo ladder, progress | Implemented in software; physical behavior open | Real full session with no clock/stage divergence |
| **2 — Notation fidelity** | Source IDs, hands, ties, rests, tuplets, native ink and geometry | Broad test/evidence coverage; real-score visual gaps remain possible | Independent framebuffer/original-note parity on required corpus |
| **3 — Original Coda, MIDI-domain** | Four algorithms; pinned author-differential reproduction and source-safe desktop lesson path | **Algorithm scope complete; post-consolidation Coda tests green** | Existing 1,273-request differential and whole-piece/17-piece corpus, then current refactor regression |
| **4 — Fukuda + composed strategies** | MIDI-domain reductions, source-local feedback, recorded-MIDI alignment, generic whole-piece/adaptive composition | **Code integrated**; live combined-path acceptance and paper figure parity not established | Focused + corpus tests, source-effect comparison, physical original-to-remediation loop |
| **5 — One architecture, no compatibility layers** | Canonical engraving, native-only score assets, typed IPC, pluggable generator ownership; delete obsolete Qt/HTTP/facades | **COMPLETE — 2026-11-03** | All required fast/focused/corpus, native load, Godot parser, source graph and staged-package checks passed; see evidence below |
| **6 — Real instrument + UX performance** | Beethoven opening, READY ink, scrolling vs BPM, Listen, error/retry, rests, reconnect, latency, longer pieces | **Software recovery suite green; physical acceptance open** | Signed real Godot + USB/Bluetooth MIDI evidence across full checklist |
| **7 — Teaching study + release** | Independent pedagogical effectiveness, clean-machine distribution, long-session reliability | **Synthetic endurance passed; release and human study open** | Prespecified learner comparison, reproducible package and unattended real-time session acceptance |

Phase 3 deliberately covers the original *MIDI-domain* algorithms. Neither
importing MusicXML nor reproducing Fukuda's acoustic front-end is silently
added to the product scope. Original Fukuda paper thresholds and figure
reproduction remain research claims until independently checked.

## Completed Phase 5 — verified implementation

**P5 — Architecture consolidation.** Implemented and accepted on 2026-11-03.
The product uses one MIDI-only, native Godot/embedded-CPython runtime, one typed
in-memory operation queue, and explicitly registered independent whole-piece
lesson generators. Unregistered generators fail rather than selecting a
heuristic fallback. `LegacyStrategy`, `HeuristicLessonGenerator`,
`with_mistakes`, unversioned lesson reconstruction, stale LearningPlan
forwarders and obsolete Qt/HTTP/page-image paths are removed. Graded
source-ID evidence enters every adaptive generator through `with_feedback`.
Saved strategy/version stage identities isolate BPM and mastery; unversioned
records remain in storage but cannot award credit.

**Recorded acceptance evidence:**

| Gate | Reproducible result |
|---|---|
| Fast architecture, import graph and Python state contracts | [403 passed, 6 skipped at `f9ae15b`](https://github.com/tpepels/piano_teacher/actions/runs/41637045068) |
| Fukuda source MIDI contracts | [43 passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328757) |
| Composed Coda+Fukuda and course persistence | [98 passed, then 17-piece real MIDI corpus passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328743) |
| Independent Coda research and full MIDI repertoire | [235 passed / 1 skipped, 51 passed; stage audit passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328719) |
| Godot GDScript parser | [Green at `e47ec35`](https://github.com/tpepels/piano_teacher/actions/runs/41631177422); commit comparison through `f9ae15b` contains no `godot/` changes |
| Compiled native CPython/Godot bridge | [Build passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328908) |
| Embedded Godot typed `library.catalog` and assembled standalone runtime | [Both passed at `f9ae15b`](https://github.com/tpepels/piano_teacher/actions/runs/41637102956), including `PIANO_NATIVE_CLASS_OK`, `PIANO_NATIVE_LIBRARY_OK` and `PHASE5_ARCHITECTURE_AUDIT_OK` |

The native smoke uses the matching built artifact and confirms one registered
`PianoNative` class with a working embedded Python typed operation. The staged
package audit checks the actual copied runtime, relative import graph,
required binaries and removal of editor-only runtime code. As intended, it
does not certify a clean-machine launch of the final compressed release; that
is Phase 7. Hardware latency, visual note alignment, physical grading and
pedagogical effectiveness belong to Phases 6 and 7, not Phase 5.

## Phase 6 — MIDI calibration redesign

Five uninterrupted eight-tap rounds now follow a single four-beat count-in.
The input callback and displayed/clicked pulse use the same monotonic epoch
and total beat count. A clearly mistimed tap per round and at most one
outlying/unreliable whole round can be excluded; at least four consistent
rounds are required. Apply is explicit and the saved correction remains
unchanged after cancellation or rejected samples. Python tests cover timeline,
outliers, missing/double taps and persistence; Godot checks cover the pulse's
single preparation period. USB/Bluetooth timing accuracy remains a physical
Phase 6 gate, not certified by synthetic samples.

The calibration-to-grading regression passes through the MIDI callback,
recorder, final assessment and saved correction after reopening the engine.
It checks 180 ms delayed attacks both before Apply (late) and after Apply
(correct), plus an unchanged wrong-pitch rejection. The bounded Python CI
run https://github.com/tpepels/piano_teacher/actions/runs/41694522464
passed 426 tests (6 skipped) at c5a898d. No hardware measurement was involved.

## Repository housekeeping

The root README and this roadmap are the only active entry points. Historic
notation/raster plans are under docs/archive/development/ and the optional
RubricNet reference tooling is explicitly research-only. Godot .godot/ editor
caches are untracked and source .gd.uid files are retained; fast CI rejects
reintroduced generated/indexed debris. Editor-only MCP tools remain in the
development tree but are excluded from release staging.

## Maintainability hardening — completed 2026-11-03

This review and targeted implementation cover the backend practice settlement,
frontend command lifecycle and the transport/score-preparation ownership gaps
identified after Phase 5. They do not reopen Phase 5's completed architectural
consolidation and do not certify physical MIDI or release readiness.

**Completed changes on `main`:**
- Unified graded evidence, Fukuda mistakes, learner trouble resolution and
  persisted mastery/progress with SQLite nested savepoints. Failures in evidence
  observation, adaptive feedback or the final progress write rollback every
  durable change, restore the current `LearningPlan` and retain the pending
  take. Automatic transition retries stop with an explicit save failure
  rather than attempting writes on every frame. Injection and subsequent
  successful-retry tests exercise each failure boundary.
- Godot in-process command requests unregister canceled/timed-out callbacks
  and ignore duplicate, obsolete or out-of-order completions. Dispatch failures
  reset outstanding command state and publish an error rather than leaving a
  busy indicator. The real request/command-state fixtures run in Godot 4.7.
- Deleted all 17 `TransportField` forwards from `PracticeEngine` and the
  entire descriptor class. The engine, all audited tests and development tools
  now use the single `VisualTransport` state owner. A tracked-source check
  rejects reintroduced field aliases; zero remaining aliases were found.
- Replaced obsolete HTTP request tests with typed `EngineCommands` tests.
  Old clock assertions were updated to the current metronome coordinator.
  Native-engraving-dependent instructional-recovery tests run only in the
  full, optional Godot/Verovio environment, never in dependency-minimal CI.
- Native score fragment extraction fails with explicit stage-specific errors
  instead of publishing empty tie, beam, chord, tuplet or slur fragments after
  exceptions. Error injection covers all fragment builders and verifies that
  unsuccessful layouts are not cached.

**Verified gates:**
- [Fast CI at `e99902b`: 507 passed, 6 skipped](https://github.com/tpepels/piano_teacher/actions/runs/41708617452).
- [Godot parser and request fixtures](https://github.com/tpepels/piano_teacher/actions/runs/41705203537) passed after the request lifecycle change.
- [Fukuda](https://github.com/tpepels/piano_teacher/actions/runs/41707025702)
  and [composed strategy](https://github.com/tpepels/piano_teacher/actions/runs/41707025653)
  regression gates passed after transport ownership migration.
- [Phase 6 real-score framebuffer](https://github.com/tpepels/piano_teacher/actions/runs/41708452848)
  passed after the native fragment error behavior change.

**Subsequent software acceptance (2026-11-03):**
- [Real Verovio/music21 engraving recovery: 51 passed](https://github.com/tpepels/piano_teacher/actions/runs/41710805927). All tests in the targeted instructional-recovery, silent-bar, retimed-source and isolated-tuplet modules passed in a full score runtime; no optional-import skipping.
- [Extended fast CI: 513 passed, 6 skipped](https://github.com/tpepels/piano_teacher/actions/runs/41711521908). In-process worker endurance covers 250 preview repeats with ten simulated 10-minute pauses, 100 rapid pause/resume sequences and 100 real-imported-MIDI full performances with intentionally wrong notes. Source bytes, saved mastery and notation revisions remain stable in these synthetic-clock runs. The transport alias audit remains at zero.
- MIDI library opening preflights lesson generation and persisted-stage restoration before stopping a running session. Typed command tests inject invalid MIDI, generator failure and restore failure and verify the original transport, MIDI recorder, source ID and score revision survive unchanged.
- A bounded [full-engraving recovery workflow](https://github.com/tpepels/piano_teacher/blob/main/.github/workflows/phase6-engraving-recovery.yml) now runs on affected source changes and supports explicit manual reruns; it retains failure artifacts.

**Still unproven:** physical USB/Bluetooth input and audio latency, target-device frame cadence, continuous real-time operation under actual system suspension, all-repertoire rendered correctness, clean-machine release installation and comparative teaching effectiveness. Virtual-clock endurance does not establish uninterrupted real-time reliability. These are Phase 6/7 acceptance issues, not an alternate architecture or a reason to introduce compatibility layers.

## Phase 6 — continuous lesson runway and developer launch

**Implementation (2026-11-03):** The scrolling native score is now the
primary practice interaction. Stage numbers, hand and current/next notation
level are projected at musical positions on that same beat axis; the former
step selector lives in **Lesson Path**, where explicit navigation remains
possible without cluttering the practice stage.

- A bounded background **FutureScore** worker pre-engraves the next exact
  source-keyed Coda/Fukuda stage, including semantic notes, authentic Verovio
  assets and fingering projection. Its large reply is serialized off the
  authoritative MIDI command worker. Two upcoming stages are cached with one worker and bounded memory.
- The in-process Godot **ScoreRunway** builds the future retained native
  ink ahead of use and sends an exact stage-key/revision acknowledgement.
  On a passing third clean full-target run, the engine adopts the already
  prepared source model, commits mastery, and continues at the same musical
  deadline **without a new count-in or score-load panel**. The outgoing
  stage stays visible to the left until it scrolls out. No new scoring clock
  or alternate teaching implementation is introduced.
- Failed takes keep the backend's original source-bound recovery and
  preparation deadlines. The front-of-house staff now **never reverses**:
  Retry and Resume admit another already-engraved copy ahead of the fixed
  playhead. Pausing keeps the empty staff moving but stops new admissions.
  A changed source/revision cannot adopt stale ink.
- `./run.sh` now checks actual native inputs, binary and CPython ABI. It
  rebuilds when the compiled bridge is stale, and rechecks Godot registration
  and embedded Python when source/runtime inputs change. A Python-only pull
  no longer requires a manual native rebuild; an unsuccessful preflight exits
  with an error instead of opening a broken UI.

**Software gates:** `tests/test_future_score_lookahead.py` verifies
two-stage caching and exclusion of stale in-flight jobs;
`tests/test_seamless_stage_runway.py` covers clean
consecutive transitions, preloader failure, guided-origin practice and
unchanged failure recovery; `tests/godot/seamless_score_runway.gd` checks
retained renderer promotion and outgoing scrolling ink;
`tests/test_real_future_score.py` prepares the actual Coda/Fukuda MIDI
notation/Verovio bundle in the full engraving workflow. The existing
`run.sh` fingerprint regressions also run in fast CI.

**Preloading-failure closure (2026-11-04):** Automatic mastery settlement
now waits for authentic, acknowledged next-step notation while the source
camera keeps moving on the existing monotonic beat axis. A late prepared
stage receives an exact two-beat reading runway, and its already-compiled
Godot renderer promotes without another score revision handshake or count-in.
The source's repeated ink is clipped at the upcoming boundary until the
next authentic score exists; stale notation never appears as the new stage.

FutureScore retries transient engraving errors three times with bounded
backoff. The native Godot renderer has its own three-attempt bound and
reports exhausted source-specific errors over the typed in-process command
bus using the precise fingerprint, step number and revision. A genuinely
unrenderable stage pauses safely at the assessed transition boundary with
an explicit failure message, without committing mastery or grading invisible
notes. Successful third-pass transitions remain immediate when preparation
finishes on time. Backend source recovery remains intact; the production
Godot visual staff no longer moves backward, including during retries.
Lookahead stage +2 now uses its correct future revision, preserving warmed
assets across consecutive promotions.

**Acceptance limitation:** no captured keyboard/GPU session yet proves
glitch-free transitions on the target computer. Temporary preparation
delays may produce a longer empty reading runway, although the visual
clock remains continuous. Permanently invalid source notation is a
blocking, explicit user-facing error; silent recovery from truly invalid
engraving would falsify the score. Real long/complex pieces and automatic
adaptive replanning remain mandatory Phase 6 acceptance cases. This
feature does not close physical performance or teaching-effectiveness gates.

## Phase 6 — perpetual practice staff and calmer UI (2026-11-05)

**Product behavior, implemented in `main`:** The production Godot stage
uses one `ContinuousScoreFlow` that advances its world position each rendered
frame, independently of the backend's source position and whether a physical
MIDI keyboard is connected. READY, Pause and between-step waiting continue to
show a moving blank staff. Starting a take, restarting and resuming admit
authentic pre-engraved source notes as separate clipped passes on that same
world axis. Already admitted notes leave the screen naturally, even after Pause;
none are reset or rewound. Note timing, assessment, count-in, synthetic Listen
and saved mastery remain owned by the backend and use its authoritative
source tempo map. Forward camera velocity follows authored tempo changes;
tempo control never seeks the camera. All stage transitions reuse the
revision-bound prepared renderer and preserve departing ink.

**Rendering:** Local GPU additive CanvasItem bloom remains compatible with
Godot's Compatibility renderer. The play/pause bloom now uses a rounded SDF
and feathered alpha at the quad edges, with dark-blue button halos. No
global HDR/Forward+ switch, per-frame CPU-generated blurred textures or
scene-tree mutations inside a draw callback. Native source contours remain
retained CanvasItem commands; only their transforms and clipping move.

**UI:** Settings prioritizes MIDI and practice tempo, followed by library
and listening. Calibration, exercise strategy, and history maintenance are
disclosures; all underlying actions remain available. The lesson path
summarizes position, mastery goal and the current passage, with a bounded
neighboring-passage preview and full step selection via the picker.
The Accuracy ring contains the percentage alone and labels it outside.

**Verification, not yet final release acceptance:** The fast Python tests and
Godot 4.7.2 syntax/UI/flow fixtures passed on the updated head. One matching
embedded runtime previously passed a real two-hand score, Moonlight Sonata
Play/Pause/Retry/Listen/stage/tempo/reopen, Peace Piece and Chopin UI flows;
its final packaging audit timed out because it copied the entire developer
Python prefix. A smaller self-contained CPython staging operation with an
explicit staged-import check is now used; its matching runtime CI must pass.
The separate independent framebuffer/source-notation checks still report
failures for sampled Peace Piece rests and Chopin/Moonlight note contours.
Those are not waived by a successful UI runtime, and target-GPU/real-MIDI
acceptance remains open.

### 2026-11-05 — Continuous repetition, saved-song overlap and tempo controls

- The fixed playhead is a forward-only Godot presentation world. READY,
  Pause, Retry, transport recovery, score loading and next-stage preparation
  never intentionally stop or reverse its motion. Pausing prevents admission
  of *new* retained note clips; existing visible clips keep drifting out.
  Retry and automatic restarts admit new clips after the engine's meter-aware
  preparation gap. The backend's source timing remains independent for
  grading, audio, and evidence.
- No MIDI device: a preview repeats after one empty measure and cannot earn
  mastery. A connected but silent keyboard: the authoritative grader records
  missing notes, applies source-bound recovery and replays after the rest.
  Incorrect attacks use the same registered response policy. Evidence-guided
  practice stops introducing new automatic interventions after twelve actions
  but keeps repeating; it no longer automatically diverts rhythmic practice
  into a note-finding state that could wait indefinitely. An explicit learner
  Pause still suppresses new score admissions. Irrecoverable score errors
  prevent fresh *graded notes* from being admitted but not visual world time.
- Source fingerprints isolate persisted piece/course positions, learned
  tempos and mastery. On opening a saved piece past its first lesson step,
  including the startup's last-opened piece, Practice offers three paths:
  restore the exact step, review two earlier exercise steps, or select a
  source measure (when opened from the full Library). Earlier mastery remains
  stored. Review uses ordinary lesson steps and assessment, not an invented
  mastery credit; returning to the previous saved step is via normal course
  progression or manual selection.
- The tempo popover is a compact 190×98 panel with an Italian tempo name
  and symmetric five-BPM controls. Manually increasing beyond the imported
  song's original BPM is supported up to the configured application maximum,
  without rewriting its musical target or discarding stage-specific saved BPM.
- Coda and Fukuda contribute actual source-safe musical transformations and
  can incorporate graded source-note feedback. The separate registered
  mistake-response policy determines repeat, isolate, slow and reintegrate;
  `LearningPlan` sets tempo ladder and accepted-take mastery; `PracticeEngine`
  schedules transitions. They do **not** presently own retry policy, the entire
  tempo ladder or all transport decisions. Full authority would require a
  separate, explicit contract/architecture revision; do not claim it now.
- Bounded software verification is distinct from the independent real-score
  framebuffer oracle, physical MIDI/target GPU tests, full package audit and
  long-session failure handling. Only checks actually run for the matching
  revision can certify their specific gates.

## Immediate order of work

**Learning measurement and adaptive teaching continuation (2026-11-04):**
The local ledger retains sessions, attempts, original note assessments,
repetitions, actual BPM, durations, interventions and linked subsequent outcomes.
Mastery still requires three accepted full-target takes; strictly clean takes
are a separate metric, and the practice labels now say accepted passes.
`learning.statistics` on the in-process API reports these measurements,
timing residuals, comparable retry outcomes and unknown/pruned coverage.

The selectable `evidence-adaptive` policy uses actual source error clusters,
source attack density and compatible prior outcomes to repeat, isolate, slow,
guide and reintegrate. Repairs expand across held-note boundaries and return to
unsupported full-passage grading. All six existing policies retain their
behavior. Twelve automatic actions bound an episode; manual overrides cancel
stale decisions. MIDI replay covers the complete repair route, write-failure
retry and source preservation. Physical-instrument behavior, delayed retention
and comparative teaching effectiveness remain unverified. No UI redesign,
architecture replacement or long CI run is part of this continuation.
Verification: 254 targeted Python tests passed in 6.65 seconds, covering grading,
ledger/capture rollback, statistics/API, the full adaptive MIDI route, fixed
policies, Coda/Fukuda generation and seamless stage transitions.

### Approved P0 learning measurement implementation plan — 2026-11-04

**Goal:** Preserve all practice exposure and authoritative grading evidence in
one local ledger, with working privacy controls and unchanged accepted-take mastery.
**Architecture:** The existing SQLite connection and engine lock own settlement;
grading captures its original assignments and an application evidence owner seals
attempts before recorder disposal. Existing Settings exposes local controls.
**Tech stack:** Python, SQLite, Godot 4.7.2 and the current in-process bridge.
**Spec:** [Approved contract](docs/learning-measurement.md).

Global constraints: main only; no service, alternate history backend or visual
redesign; three accepted full-target takes, `accepted-full-target-v1`; detail
defaults 365 days/256 MiB, bounds 7–3650 days/16–4096 MiB; local redacted export;
unknown crash suffix and legacy fields remain unknown; all six policies retained.

Review focus: repeated/chord wrong-pitch assignment; failed write with a pending
third take; stop/navigation/device replacement before settlement; migrated unknown
timing and pruned coverage; deletion during an active session without inherited credit.

1. **Authoritative grading detail** (`practice.py`, `timed_assessment.py`, new
   grading evidence tests). Add frozen observation values to the actual matching
   pass: press index, expected/actual seconds, local tempo/tolerances, signed
   residuals and independent flags. Preserve status/passed behavior. Write failing
   repeated/chord/wrong/mapped/unreleased tests, implement, run grading contracts.
2. **One durable ledger** (new `learning_ledger.py`, `progress_repository.py`,
   `practice_history.py`, new ledger tests). Define `start_session`, `store_rules`,
   `start_attempt`, `checkpoint`, `settle_attempt`, `record_event`, `add_decision`,
   `record_outcome`, `close_session`, `recent`, `prune`, `export`, `delete_piece`,
   `delete_learner`. All share the repository connection/savepoint. IDs and sealed
   payload hashes enforce identical replay/no-op and conflicting replay/error.
   Migrate bounded old rows atomically, remove their writer/table, read advisory
   history from the ledger. First test migration/restart/rollback/retention/export/
   deletion, then implement and run those tests against reopened databases.
3. **Lifecycle integration** (`server.py`, new application evidence owner,
   in-process shutdown, new replay tests). Freeze source/rule/map/device context at
   each timed/guided/preview/Perform start; checkpoint existing musical boundaries;
   seal completed/partial/rolling/guided/aborted exposures before recorder disposal.
   Commit assessment and progress together; preserve pending payload on write error.
   Record decisions, next-exposure outcomes, episode verification/censoring, manual
   events and distinct measured phase intervals. Tests drive real MIDI callbacks,
   repeated settlement, failed writes, acknowledgment, overrides and restart.
4. **Functional local controls** (`library.py`, typed command contracts/bridge,
   `godot/settings_screen.gd` and its coordinator, new control tests). Add validated
   retention preferences and working local JSON export with detail opt-in; current
   piece and all-learner deletion use explicit UI confirmation. Reset preserves
   ledger evidence. Intent/applied records surround file-backed setting changes.
   Test invalid settings, cancellation, redaction and complete deletion/reset.
5. **Acceptance and canonical documentation** (bounded scripts, ROADMAP, current
   audit and verification receipts). Run each task's targeted tests after its
   RED→GREEN cycle, then bounded fast/hybrid/Godot/native/launch gates; review the
   complete change independently, correct confirmed findings and commit verified
   changes directly to main. Record actual counts, runtime/resource coverage and
   remaining physical/packaging gates. P1 analytics and adaptive rollout remain
   separate later phases, never inferred from ledger completion.

Status: tasks 1–4 implemented, with bounded software acceptance and review
corrections recorded in the [P0 verification receipt](docs/verification/learning-measurement-2026-11-04.md).
All 74 variables have a source audit and explicit implementation delta. Task 5
does not close full architecture, independent notation, physical MIDI or release
acceptance. Resumed independent storage/lifecycle and controls reviews found
additional episode/maintenance issues; their fixes have regressions and the
scoped reviews report no remaining confirmed Critical/Important findings.

Ruling: a valid manual retry-policy or calibration change ends the old exposure
and requires Play for the next. This preserves one frozen policy/correction per
attempt; it changes manual override continuity. Invalid changes preserve the
active take. Fixed-policy decision rules and accepted-take mastery remain intact.

Next software phase is the contract's P1 read-only analytical queries/report,
with retained/pruned/legacy coverage and comparable fixed-policy denominators.
No dashboard, difficulty-adjusted learner model or learned retry selector is
claimed by P0. Complete the outstanding current-head notation gates
before adaptive rollout; retain the physical and clean-machine gates below.

**2026-11-04 development audit and adaptive retry proposal.** The current
[architecture map](docs/architecture/system.md) inventories subsystem owners,
dependencies and invariants. The
[dated verification/findings ledger](docs/verification/development-audit-2026-11-04.md)
distinguishes reproduced defects, corrected obsolete fixtures, passing checks
and remaining verification debt. Historical Phase 5 acceptance above is not a
claim that every current local test or physical gate passes.

Confirmed fixes in this audit preserve performed BPM in completed-take evidence
when a policy slows the retry, validate stage commands before stopping a valid
take, normalize invalid saved folder/calibration values, align READY lesson
labels with the native preview camera, preserve sustained notes at standalone
Fukuda excerpt entry, and remove the unused two-pass `Curriculum`. The notation
verifier no longer imports its coordinator through its causal-difference helper.
Legacy HTTP/PNG test seams in the exercised gates are migrated to typed/native
contracts; no compatibility runtime has been restored.

Whole-suite collection was restored in the first audit; the P0 delivery now
collects 4,839 tests with zero collection errors (704 fast tests pass).
Outstanding fingering-clearance and small-staff attachment failures and remaining
broad assertions retain their own verification gates; collection success is not
whole-suite acceptance. The selectable recovery implementation does not close
those notation or physical gates.

The [adaptive retry specification](docs/mistake-response-policies.md) reviews
primary studies, defines structured error evidence, graduated interventions,
offline replay and a small controlled physical comparison. It recommends an
explainable deterministic selector before online learning. The owner's subsequent
development request authorizes the implemented `evidence-adaptive` selector.
Its thresholds are engineering defaults, not proven optimal pedagogy. The six
fixed strategies retain their identifiers and behavior.

Proposed implementation sequence within P6/P7, requiring review before product
behavior changes:

| Step | Complete implementation scope | Exit gate |
| --- | --- | --- |
| P0 retry evidence | Implemented through the approved local measurement contract above; one ledger replaces the status-only writer. | Bounded software and scoped independent review evidence is recorded; broader notation and physical/release gates remain open. Manual policy/calibration changes now seal the current exposure. |
| P6 adaptive selector | Implemented as a separately registered/versioned deterministic policy using the existing transport and ledger; complete repeat/isolate/slow/guided/reintegration path, source-safe ranges, reasons and learner overrides. | Focused real MIDI replay and rollback checks pass; baseline policies retained. Full physical sessions and teaching-effectiveness evidence remain open. |
| P7 comparison | Preregistered matched-passage feasibility study, followed by power/precision-planned retention comparison. | Unsupported full-original tests at common tempo after 24 hours; burden/frustration, missingness and uncertainty reported; no superiority claim from pilot/replay. |
| P7 optional online learning | Local interpretable contextual bandit only after randomized eligible-action logs and comparable unsupported outcomes exist. | Action support/propensities, effective sample size, held-out learners and prespecified delayed learning/safety outcomes. Otherwise retain deterministic policy. |

The numerical thresholds in the proposed selector are calibration hypotheses.
The existing `adaptive` response is parameterized recovery, not a learned
personalized policy. `Assessment.passed` permits a minority of timing/hold
warnings, whereas `Assessment.clean` requires all notes precise; retention and
clean-pass reports must state which criterion they measure.

**P6 — Prove real user behavior.** The
[embedded real-MIDI workflow](https://github.com/tpepels/piano_teacher/actions/runs/41660803843)
passed at `213cc255`: library catalog, opening an actual two-hand MIDI,
Verovio note anchors, source-semantic score, score-ready acknowledgement,
Play/Pause/Resume and the staged package asset audit. Native CI is now pinned
to the exact build revision and reruns on changes to the score pipeline.
This establishes embedded software integration, not Godot framebuffer
correctness or physical MIDI keyboard behavior.

**P6 — Production UI gate.** The real-scene
[acceptance run](https://github.com/tpepels/piano_teacher/actions/runs/41663899894)
passed at `aecbb09`. `main.tscn` starts the embedded Python worker, reopens
the saved MIDI, compiles retained notation, dismisses the loading overlay
and starts, pauses and resumes the same transport. Commit `4feb8ac`
adds stronger checks for actual viewport-visible noteheads, stationary
pause positions and scroll displacement at the displayed BPM. The
stronger frame-level checks passed in the later
[real-score native runtime gate](https://github.com/tpepels/piano_teacher/actions/runs/41678370190)
at `d92d9e6`. Neither check substitutes for an independent pixel proof or
physical MIDI test.

**P6 — Real-source written rest.** The
[bounded real-MIDI regression](https://github.com/tpepels/piano_teacher/actions/runs/41665774242)
passed at `cc7efe9`, including the composed-generator contracts and the
17-piece MIDI corpus. Its newly generated three-measure, two-hand source
contains a full silent measure, and the unchanged original performance
continues along the same visual and grading beat axis across the silence.
This establishes software clock continuity, not the target-device frame
cadence or MIDI input response.

**P6 — Actual repertoire and session.** A bounded native integration
journey uses the repository's genuine `Moonlight_Sonata_I.midi` and drives
the production scene through ready notation, Play/Pause/Resume, a full
backward/retry preparation measure, Listen/return, selection of step 2,
manual -5 BPM and closing/reopening the saved lesson. Both score revisions
and visible native noteheads are checked at every publication boundary.
The native workflow
[passed at `d92d9e6`](https://github.com/tpepels/piano_teacher/actions/runs/41678370190),
including decoded Listen WAV playback and the staged runtime audit. Sound-card
output and physical MIDI grading still require real hardware.

**P6 — Real-score viewport coverage.** Two further production-scene
cases now select the real `Peace_Piece_-_Bill_Evans_(Piano_Solo).midi` and
`Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi` through the persisted
library. The full file SHA-256 must match the loaded backend fingerprint.
Each case verifies retained visible noteheads at READY, at least two beats
of lookahead, a stationary Pause and source-clock-aligned motion on Resume.
Both
[passed at `d92d9e6`](https://github.com/tpepels/piano_teacher/actions/runs/41678370190),
including SHA-256 source identity, actual retained notehead presence, Pause and
BPM-consistent Resume. Independent framebuffer pixel verification remains
separate from these headless compositing checks.

**P6 — Graded software-input callback.** The
[bounded Coda + Fukuda test and 17-score corpus](https://github.com/tpepels/piano_teacher/actions/runs/41676220356)
passed at `23ca2ca`. This additional real MIDI fixture delivers original
note-on/off messages through `PracticeEngine._receive`, including a whole
silent bar; one clean whole-piece performance and a second take with a
deliberate wrong RH pitch produce correctly source-bound performance reviews
without modifying the source MIDI. The
[backend-calibrated click and display-clock regression](https://github.com/tpepels/piano_teacher/actions/runs/41676891067)
passed at `c2a7ab7`, including state-response delay injection. Neither is
a measurement of physical USB/Bluetooth input latency.

**P6 — Independent real-score pixel proof.** The targeted
`phase6-real-score-framebuffer.yml` gate runs on matching Godot 4.7.2,
generates source-registered production PNGs for Peace Piece measures 1–2,
Chopin Nocturne measures 5–6 and Moonlight Sonata measures 1–2, verifies
real written rest/notehead ink, and demands that deliberate framebuffer
damage is rejected by the same pixel oracle. Missing/mismatched source
symbols or output frames fail the build; captured evidence is uploaded with
the exact source SHA. This is a bounded sample, **not** full-score coverage.
The
[Godot 4.7.2 pixel gate](https://github.com/tpepels/piano_teacher/actions/runs/41682551172)
passed all three samples, including the otherwise missing causal eighth-rest
control. The fixture assembler uses the canonical native layout path without
`native_notes`, and the controlled experiment now recompiles the retained
CanvasItem before its ablated PNG. The expanded, source-derived
[slur/three-voice framebuffer job](https://github.com/tpepels/piano_teacher/actions/runs/41683609789)
also passed on Godot 4.7.2. The sampled proofs remain distinct from complete
pixel-level validation of every source event on every page.

**P6 — CPU and memory instrumentation.** The
`phase6-score-performance.yml` source-bound gate profiles actual Moonlight
and Hanon imports, first Verovio/native asset compilation, same-revision
cached response, next-lesson score generation and 160 real backend state
polls under a practice transport. It exports wall times, p95/max polling,
actual note counts, source hashes and peak process RSS. These are bounded
Linux CI software budgets, not USB/Bluetooth/display latency targets. The
real-score
[performance CI](https://github.com/tpepels/piano_teacher/actions/runs/41685438881)
passed: Moonlight (1,164 source notes) cold load ~0.45 s, first native
score ~2.85 s, state P95 ~0.9 ms; Hanon (18,058 source notes) cold load
~5.78 s, curriculum ~4.56 s, state P95 ~3.61 ms, peak RSS ~194 MB.
This replaces an observed ~27.8 s Hanon load and ~22.1 ms state P95
at the first benchmark. Full-piece beam inference is explicitly declared
only by source-heuristic generators; the adaptive MIDI-domain author
contributors avoid unused global MusicXML. Source attacks are indexed once
for each composed curriculum, and the HUD freezes only the current
exercise's hand rows while retaining an accurate complete lesson count.
An immutable stage-key index keeps step-number and mastery lookups fast.
The CI budgets now require Hanon cold load below 15 s and state P95 below
12 ms, Moonlight below 8 s and 8 ms respectively, with stricter
native-ink and memory bounds. CI-host timings cannot establish local
frame pacing, Bluetooth or USB input latency.

**P6 — Score preparation.** Score loading now supersedes obsolete
layout/model requests without waiting for old deadlines, bounds semantic
retries, and surfaces actionable failure if retained notation never completes.
The Godot `score_asset_lifecycle` regression runs as part of the bounded
syntax/behavior CI gate.
The original five native score-session contracts now enforce the same
bounded retry, revision supersession, failure and publication semantics. Loading phase, Browse and delayed Retry now come
directly from this session into the practice UI. Retry can also supersede a
still-pending layout request. Physical screen/instrument evidence remains open.

On the real Beethoven Pathétique II MIDI,
record READY ink, Step 1 provenance, effective tempo, Play/Listen/Retry,
post-rest handoff and stage changes. Run the
[physical keyboard acceptance checklist](docs/verification/coda-fukuda-physical-midi-checklist.md)
with both USB and Bluetooth where available. Fix source-specific failures
in the single clock/score pipeline, not by adding alternative paths.

**Release package hygiene.** Standalone staging now explicitly excludes
Godot test fixtures, smoke scripts, editor-only .uid files and MCP plugins.
The package audit rejects these sources if a future change includes them;
clean-machine installed execution remains a Phase 7 gate.

**P7 — Validate pedagogy and ship.** Preregister a human within-piece or
counterbalanced study comparing meaningful learning outcomes across Coda,
Fukuda, combined and original-note practice. Keep generated sequences and
evidence reproducible; separately test clean-machine installation and offline
functioning.

## Outstanding critiques and resolution directions

| Critique | Required resolution or research |
|---|---|
| Later production commits require fresh acceptance evidence | Re-run the affected fast/focused, corpus and native gates against the changed revision; do not claim hardware or release validation from source checks |
| Sparse opening and dense note spacing may still be visually wrong | Native framebuffer captures before/after Play at fixed BPM; measure first attack x-position and pixels/beat against timing |
| Score preparation and large-piece transitions may stall | Score projection is now reused per selected revision across geometry + semantic commands; profile cold/warm import, engraving, atlas and command queues per stage; require bounded P95 |
| Stage choice might be repetitive or musically ineffective | Expose actual removed/retimed/source-preserved notes; inspect stages on a varied corpus, then run P7 study |
| Audio, visual scroll and MIDI grading could drift under load | Record common source-ID/beat traces, audio position and note-on timestamps; compare under pause/retry/rest/tempo changes |
| Calibration pulse drift under delayed score/device snapshots | Calibration beat now uses the same backend monotonic epoch as MIDI events; a Godot regression injects stale snapshots and verifies the visible downbeat/click. This is a software correction only; hardware audio/USB/Bluetooth offsets still require measurement |
| Physical latency/handshake and reconnect remain unproven | Measure timestamp and calibration error with USB and Bluetooth on target device; fault-inject disconnect and recovery |
| Full packaging, migration and runtime fault handling not accepted | Isolated clean-home install, simulated corrupted cache/old course, crash/reopen, offline start and asset-bundle checks |
| Residual application orchestration | Maintain the established transaction and request boundaries; use failing end-to-end tests before extracting more responsibilities. No transport forwarding remains |
| Removed strategies can survive in historical test fixtures or saved preferences | Prevent runtime registration, reject obsolete selection, migrate unknown saved choice to the default hybrid; retain historical fixtures only as test data |
| Original Fukuda numeric/figure parity is not independently established | Paper-to-code threshold/figure audit; explicitly report MIDI-domain substitutions instead of claiming audio-domain replication |

## Current blockers

| Blocker | Unblock |
|---|---|
| **Real Beethoven and physical instrument behavior unobserved** | Reopen Beethoven in combined strategy; capture diagnostic log, framebuffer and keyboard assessment trace |
| **Research comparison and release evidence missing** | P7 pilot and clean-machine packaging gate, after P6 |

## Commands and completion rules

```bash
git pull --ff-only
# Re-run on any new production change:
bash scripts/ci-smoke.sh
bash scripts/check-godot-syntax.sh
bash scripts/verify-hybrid-workflow.sh --focused
bash scripts/verify-hybrid-workflow.sh --corpus
# Daily developer start: only stale native inputs rebuild; changed runtime
# inputs are preflighted against the actual Godot + embedded Python process:
./run.sh
# To diagnose build/preflight failures independently:
bash scripts/build-inprocess.sh
bash scripts/verify-native-bridge.sh
# Staged standalone audit is performed by the native runtime smoke CI.
```

Do not run or wait for long CI during interactive development. A focused
test suite proves only its named contracts; software source inspection
cannot certify audio/visual correctness or a physical MIDI device.
**A phase closes only after every stated gate has evidence.** Archive
outdated planning notes; update **this file** when statuses change.


### 2026-11-05 — Future-only score admission and overlap verification

- The Practice presentation clock `ContinuousScoreFlow` is forward-only regardless of Pause, Ready, Retry, state polling and step transitions. Its immutable retained ink copies now reserve globally disjoint future source intervals via `score_stream_admission.gd`. A pause stops *admission*, not movement; each repeated take can enter only beyond the tail of older committed ink. Resume records its former source position and does not silently restart earlier source measures.
- Godot computes a source-aware presentation lead from the visible retained queue and sends it as `presentation_lead_seconds` through the existing typed embedded `practice.command`. `PracticeEngine` alone extends the graded deadline/count-in; embedded worker calls without that explicit visual request retain the established transport semantics. Manual retry continues to use the backend's semantic preparation rest and the same single graded source timeline. There is no parallel score clock or additional backend.
- CI checks: [projected notehead and future-only tests](https://github.com/tpepels/piano_teacher/actions/runs/42084931074) verify rapid pause/resume/retry on the production admission and retained-note projection code, including cross-take collisions, backward jumps and timing at insertion; [latest fast Python checks](https://github.com/tpepels/piano_teacher/actions/runs/42085160302) report 754 passed, 2 skipped, including an embedded-command/graded-deadline regression.
- **Open acceptance (not waived):** actual MIDI hardware capture and signed real-score screenshots across rapid pause/resume, metrical rests, tempo map changes and adjacent score-stage handoffs. The separate Phase 6 source framebuffer sample has three failing visual assertions on its last run; the extended instructional recovery suite also reports failed old expectations after the fixture's missing source fingerprint was corrected. Neither suite is counted as a pass for this revision.
- Pedagogy: the existing registered `evidence-adaptive` mistake policy is a deterministic source-bound selector, not a learned Gaussian Process model. Its decisions and deferred-retention outcomes require comparison against the fixed registered baselines. Relevant independent frameworks: [Moringen et al. (2024)](https://proceedings.mlr.press/v257/moringen24a.html), [Guadagnoli & Lee (2004)](https://pubmed.ncbi.nlm.nih.gov/15130871/), and [Carter & Grahn (2016)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4989027/). No paper establishes that the present 5-error threshold, 10% slowdown or 3 target-speed performances are individually optimal.

- **2026-11-05 photographed Beethoven opening regression:** SourcePassPainter correctly engraved the initial Verovio clef, key and meter to the *left* of source beat zero, but `StreamPassWindow` clipped every copy at `source_floor * density`, removing the full initial header and bisecting its first notehead. The admitted copy also had an arbitrary 3.5-beat right crop which could bisect an upcoming note or beam on screen. The fix keeps the original pre-engraved source, extends the first clip by fifteen staff spaces into the real header, reserves notehead clearance at later left boundaries, fills the visible right-side staff, and snaps the admitted right boundary to a complete source measure. Intermediate right crops do not expose the next measure's first notehead; the terminal barline gets its authored trailing clearance. Ambient staff lines no longer draw through the preserved header interval.
- **Saved progress UX:** `ResumePracticeChoice` is now a compact, non-modal inline banner just below the Practice header. The saved step and optional review/measure actions remain available without blocking keyboard/transport. Ordinary Play, later playback, the measure picker or explicit dismissal hides it without modifying existing saved progression. These behaviors are covered by the headless Practice-screen test.
- **Bounded software evidence:** [Godot parse, UI review and score-stream admission/projection](https://github.com/tpepels/piano_teacher/actions/runs/42093260267) passed for commit `f0b041ea`. The screenshot scenario itself still requires a new *actual* Beethoven framebuffer/physical input acceptance run. Existing full real-score framebuffer cases (Peace Piece, Chopin, Moonlight) still fail their separate pixel obligations and are not asserted green.
