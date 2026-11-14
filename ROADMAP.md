# Piano Teacher — single development roadmap

**Authoritative plan • updated 2026-11-14 • MIDI input only**

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

The desktop lesson strategy is adaptive **Coda + Fukuda**
(`coda-fukuda-midi`); saved selections of removed strategies migrate to this
default. Lessons are meaningfully transformed from
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

**P1 software report completed (2026-11-13):** The existing Settings → Learning
history → Practice statistics disclosure now provides All history/Current piece,
Refresh and bounded page controls with loading/error/empty states. Query version
1/report schema 2 validates source/session/date/stage/hand/performed-BPM/scope/
policy filters and stable 250-default/1,000-maximum attempt cursors. Shared detail
bytes, observations, related rows and metric tables have explicit caps and
missingness. Original pitch assignments, signed quantiles/local tempo context,
note-location exposure denominators, tempo history, recorded phase intersections,
censored recorded mastery and six descriptive fixed-policy arms use the single
ledger. Read-only worker/WAL snapshots keep report work outside the musical
engine lock. This does not close physical latency/instrument, clean-machine
release or human learning-effect gates. See the
[Task 5 software receipt](docs/verification/learning-statistics-p1-2026-11-13.md).

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


### 2026-11-05 — Single moving-bar architecture replacement

The previously reported Play pop-in was reproduced in source: `present_flow` admitted
a new source copy only after the backend published `running`, using the current
frame as `world_origin`. The native view also retained a source-local READY
camera, an ambient barline camera, source-loop/recovery variants, and a fallback
placement routine. These paths were removed, not retained as fallbacks.

Current contract (one production score projection):
- `ContinuousScoreFlow` is the single monotonic forward presentation axis,
  independent of graded MIDI time; `_project_stream` is the only native frame
  score-placement routine. Play does not change the visual origin.
- READY prepositions the original fully engraved source beyond the right
  viewport, including its authentic clef/key/meter header. Play only *arms*
  an existing reservation. The backend uses its future onset for MIDI
  assessment; a late stage handoff fails closed rather than seeking.
- Retained source and semantic-rest windows start hidden and are revealed
  only after the world transform and crop have been installed. A new clip
  cannot appear for a single frame at (0,0).
- Automatic same-score successors are pre-engraved and queued during the
  preceding take, with an explicit score reading horizon. The existing
  backend `next_at` rest is preserved, and only missing lead time is added
  to the graded deadline. Automatic successors are accepted only when their
  world onset agrees with the new backend clock; a mismatched repeat is not
  redrawn at the playhead.
- The next-stage preloader sends source-header plus view-width/IPC lead to
  the authoritative backend. After course progression it promotes only an
  already cached native score, bound to the exact future graded onset;
  the old renderer's retained clips continue to scroll left. There is no
  stage-specific source-local camera or duplicate scrolling animation.
- Obsolete idle-preview, measure-light and source-copy visibility modules and
  their tests were deleted. The canonical source painter no longer selects
  repeat/recovery variants or masks content based on an old loop history.
- Architectural regression guards assert the legacy pathways stay absent;
  Godot acceptance exercises READY→Play, pause/resume, future placement,
  clipping and real retained-note projection.

**Open and not certified:** physical MIDI timing and a signed production
Beethoven screenshot after this change; full real-score framebuffer/pixel
tests and extended instructional-recovery checks still have independent
failures. Auto-remediation that changes passage/hand/tempo must still be
verified end-to-end; its visual queue intentionally does not fabricate a
new on-screen copy if the engine's revised deadline does not match the
prepared source.


## 2026-11-09 — post-Task-3 native audit and acceptance gates

The complete 24-shard Godot 4.7.2 audit initially ran on `5b3a11f`.
It did **not** establish full notation acceptance: many source cases, especially
original Hanon, Chopin and Debussy, failed the independent five-rail detector
with `Image staff rule has no consistent thin horizontal core`. The
35-minute matrix jobs also exceeded their runtime budgets before reaching the
declared source/case denominators. Partial case counts, timeout exits and
unverified symbols cannot be promoted to passes; keep the original artifacts
and [run 42639148266](https://github.com/tpepels/piano_teacher/actions/runs/42639148266)
as negative evidence.

### Implemented verification repairs

- At `ce984aec`, `verify_all_notehead_pixels` can now intersect multiple
  **real** current Godot photographs to recover fixed gray staff rules from
  beneath transient moving noteheads and beams. The exact original five-line
  detector, notehead thresholds, source ID denominators and ink matching remain
  unchanged. The currently tested frame is always an input to the intersection:
  a line deleted from even one frame still fails. No native score telemetry
  supplies a rail or pitch position.
- The existing real-score framebuffer sample passed on that change:
  [run 42654227334](https://github.com/tpepels/piano_teacher/actions/runs/42654227334).
- The new authentic Hanon (bars 37–40), Chopin (bars 13–16), and Debussy
  (bars 33–36) notehead pixel/erased-rail regressions passed **3/3**:
  [run 42654644865](https://github.com/tpepels/piano_teacher/actions/runs/42654644865).
  These are *selected* notehead witnesses, not every symbol or a full-corpus
  waiver. The same workflow now includes separate all-symbol case acceptance.
- Modern repeat-visual tests photograph the live native queue with original
  passage, complete metered rest, and a fresh replay including source header.
  A deliberately deleted replay header fails the same image predicate;
  [run 42655813267](https://github.com/tpepels/piano_teacher/actions/runs/42655813267)
  passed **1/1**. This supersedes the retired looping/rewind tests without
  restoring their obsolete render path or relaxing pixel limits.
- The embedded production Moonlight journey, Pause/Resume/Retry, Listen,
  tempo change, reopen, Peace Piece/Chopin, native bridge, and assembled
  package verification passed on `7d486c2`:
  [run 42639112951](https://github.com/tpepels/piano_teacher/actions/runs/42639112951).

### Still mandatory, not certified

1. Run every original/lesson/hand symbol in the 24-shard audit on the
   **new** implementation revision, resolve any remaining genuine pixel
   failures and bounded-execution issues, and require all denominators.
   Existing partial/timeout evidence proves neither correctness nor completion.
2. Perform the Phase 6 full practice/recovery workflow on a connected physical
   USB and Bluetooth MIDI keyboard, measuring the actual latency/calibration,
   audio/visual note synchronization, device loss/reconnect and long practice.
   Headless/software OpenGL has no physical keyboard or listening measurement.
3. Reproduce the non-bundled Beethoven Pathétique and any user-imported MIDI
   that previously showed slow loading/Retry Score, with actual score files
   and production screenshots/logs. Issues #45 and #46 remain open until the
   affected copies pass cold/warm opening, readable passage and final
   whole-piece playback.
4. The current generator/policy ownership still separates Coda/Fukuda
   transformed exercises from mistake-response selection and the tempo/mastery
   ladder. Full Coda/Fukuda decision authority remains an explicit unsatisfied
   product requirement until a single coherent decision contract replaces the
   divided policy and tests show all control decisions originate there.
5. Phase 4 original-paper figure/threshold comparisons, Phase 7 learner
   efficacy evaluation and target-machine release acceptance are not
   established by source or synthetic tests.


### 2026-11-09 — Complete-symbol rejection and newest bounded CI evidence

The expanded source-pixel gate remains **RED** on
[run 42658927695](https://github.com/tpepels/piano_teacher/actions/runs/42658927695).
Its strict positive and corrupted-rail controls passed **32 + 3 tests**, and
its two all-symbol cases failed with **98 Hanon** and **256 Chopin** error
entries. Against the previous all-symbol attempt on
[run 42656223093](https://github.com/tpepels/piano_teacher/actions/runs/42656223093)
(175 Hanon, 356 Chopin), the full-scope error inventory shrank without
relaxing a tolerance, deleting an obligation or claiming a mismatch passed.
The exact source screenshots, original Verovio pages, per-family observations
and cause counts are in each run's uploaded `dense-rails-*` artifact.

Shared `PhotographedStaffRails` now supplies strict current-frame-intersected
rail evidence to the independent captured-frame, note-feature, structure, rest,
and unexpected-symbol owners. The finite photo-cache, mutation and pixel
contracts passed 32/32 on the matching CI run. Their selected real-source
checks passed another 3/3. The original source noteheads verified 32/32 on
Hanon and 77/77 on Chopin; all 4 Hanon and 7 Chopin ledger obligations,
and all 4 Chopin rest obligations, are independently verified.

Remaining failures are substantive and must stay RED: Hanon 7 of 8 beams
mismatch original profile; Chopin 5 of 9 beams mismatch and 3 have no complete
common witness; dense stem/flag attachment and contour checks remain incomplete;
one Chopin graphical tuplet numeral mismatches, while 14 hidden source markers
cannot count as graphical proof; unowned/ambiguous ink and the explicit
family-candidate resource budget prevent whole-frame absence certification.
These exact categories must be addressed by causal production-drawing and
proof-algorithm fixes, with mutated-image controls preserved. Neither the
current three-frame rail witnesses nor a new tolerance can authorize missing
beam/flag/tuplet/absence evidence.

Issue #45's bounded *same-real-source* reopen path is now part of
`tests/test_phase6_score_performance.py`: Moonlight and Hanon reimport,
native engraving, semantic source-vs-written ID binding, retained progress
selection, and P95/cold/warm time limits passed
[run 42658481719](https://github.com/tpepels/piano_teacher/actions/runs/42658481719).
The user's specific originally failing imported MIDI is not bundled here,
so #45 must not be closed solely from these two source samples.

The full 24-shard corpus has **not** passed at the repaired revision.
Software native acceptance, physical MIDI and genuine learner effectiveness
are independent unfulfilled exit conditions.


### 2026-11-09 — continuous-rest photographic ownership / CI execution blocker

The latest **executed** original-case full-symbol run is
[42668217876](https://github.com/tpepels/piano_teacher/actions/runs/42668217876)
at `97ff7531`: independent contracts **81 passed**, real Hanon/Chopin/
Debussy rails and damaged-rail controls **3 passed**. The complete Hanon/
Chopin proof remained **RED** with respectively **34 and 231** error entries.
The Hanon change from 5 to 34 was introduced by the exact dense-candidate
search retaining additional real whole-rest detections, not by the source
drawing becoming less accurate. The original fixture's PNG and independent
unexpected-symbol report show **34 frames** with precisely two identical,
meter-correct whole rests beyond the original last source bar (tracks 4856
and 4857, stable Y 170.5 / 342.5 and about 242 px per beat). Neither rest
is an extra *source* note or an invented barline. Unrelated residual ink
must remain unverified.

On `main`, `procedural_rest_ownership.py` now distinguishes such printed
practice silence from source MusicXML events. It derives the source-end beat
and first complete meter from the independent XML reader, checks absolute
photographic staff position, measured camera position and frame-to-frame
travel, requires the same complete left/right rest pair across at least
three distinct actual frames, and rechecks both on every current PNG.
It never exempts unmatched rests or other residual ink. Source-independent
negative controls cover missing/duplicate/wrong-height/wrong-time/low-Dice/
unstable-track rests, invalid meter and impossible photo translation.
The finite current-frame ownership mask claims only the authentic whole-rest
template's actual pixels.

**Not yet accepted:** After `2d3c3a9`, GitHub Actions began returning
`conclusion=failure` with **zero created jobs and no runnable logs** for
both normal and dense CI, including runs
[42671494209](https://github.com/tpepels/piano_teacher/actions/runs/42671494209)
and [42671662913](https://github.com/tpepels/piano_teacher/actions/runs/42671662913).
This is a runner/workflow-start gate, not a Python assertion or a validated
new source failure. The changes made after the last executed CI run therefore
remain **unverified**. Restore runnable CI and rerun both fast and dense
checks before using their outcome as proof.

**Still open:** 231 Chopin error entries at the last executable revision,
principally beam-attachment/common-witness, tuplet bracket, stem/flag and
full-frame symbol-ownership obligations. The original 24-shard complete
corpus, affected Beethoven/imported score, USB/Bluetooth/audio physical
measurement, Coda/Fukuda complete policy decision ownership and human
instructional-efficacy acceptance are all **open**. Neither Phase 2 nor
Phase 6 is certified complete.


### 2026-11-09 — post-onset connector witnesses (not accepted)

The independent full-connector verifier originally tried source onsets and
four nearest-to-mean supplementary clocks. For Chopin bars 13–16, the six-note
beam beginning at beat 7.5 ends at 8.875; its current screenshot captures
9.0/9.15/9.3/9.45 are genuine saved PNGs, but the verifier never inspected
them. All earlier candidates were either obstructed by the fixed playhead or
had ambiguous optical translation, leaving the source beam unverified even
though a clean later photograph may exist. The same onset-only limitation
applied to other multi-note beam groups and to singleton tuplet brackets.

`CapturedFrames.post_group_clocks` now selects at most four actually captured
times strictly AFTER the final source attack and within one half-beat.
`connector_pixels._verify` includes those images in the mandatory source-
anchored contour and independent motion checks, without accepting offscreen
endpoints, missing raster ink, invented clocks or weakened pixel thresholds.
`tests/test_post_group_connector_photos.py` covers actual retained Chopin
clock positions, boundedness, exhaustion and preservation of old neighbor
scheduling. **The runtime full-symbol result remains unverified** at this
revision; these tests have been committed but the subsequent GitHub Actions
runs have not supplied an executable all-symbol success. Do not claim the
three previously unverified Chopin beam groups or the bracket are fixed until
the actual new captured PNG reports establish it.

All physical-device and learner-study gates remain open.


### 2026-11-10 — continuous moving-bar P0/P1/P2 implementation audit

The moving bar keeps **one forward-only visual world clock**. Score edits are
not allowed to reposition admitted notation: it can only enter strictly in
the future, be withdrawn as the maximal unseen suffix, and expire from the
front. These changes implement the P0/P1/P2 findings from the November
moving-bar architecture audit:

**P0:**
- Pause withdraws still-unseen later measures of the active attempt, rather
  than protecting an entire graded take merely by owner ID. In-flight Play
  acknowledgments remain protected until their authoritative result arrives.
- Automatic Retry checks the engine's exact placement before withdrawing any
  music, restores only **actually missing** original strips after a partial
  journal failure, cleans incomplete newly allocated strips before restoration,
  and verifies cached plan IDs against the live FIFO. Repeated requests cannot
  claim a non-existent passage.
- Backend-scheduled automatic passages use the single authored tempo map and
  accept at most .025 source beat of visual/onset jitter, not .75 beat.
- Native retained source segments draw only their source windows, not the
  entire piece per measure. Barline context seeks by binary search. The
  immutable source-span index selects source Verovio beams, tuplets, ties,
  slurs, hairpins and voltas by time interval, preserving original paint
  order even for nested long spans. The draw frame stops projecting the
  chronological queue once its next strip is beyond the right viewport edge.

**P1:**
- A notehead's authentic horizontal ink must belong to exactly one
  retractable strip. Boundary seams move only within observed/source-derived
  blank space, with *no* source beat adjustment. Cross-measure ties/beams,
  slurs, tufted tuplets, hairpins and voltas that cannot be safely cut are
  coalesced into a single indivisible visual unit; Pause can remove only
  safe independent suffixes.
- Listen, Perform and untimed Learn publish their source-bound schedules to
  the same engine-authored future admission route. Learn repeats an unfinished
  idea only at distinct engine-scheduled epochs; Pause prevents new admission.
- After a late Python callback, a fully prepared next lesson is scheduled
  with its complete reading lead **from the actual backend clock**, never
  with an already expired downbeat. Already visible preceding source continues
  scrolling on the original world axis until it has left.

**P2:**
- Startup, unloaded and score-error screens retain the empty moving two-staff
  notation and playhead; their global visual clock is updated every frame.
- Empty measures use the actual source time-signature boundaries with pickup
  and final-meter continuation, and a bounded logarithmic viewport seek.
- On-score lesson-step markers use the same queued source origin; the prior
  unconditional per-frame suppression was removed.

**Verification:**
- [Godot 4.7.2 startup/behavior tests — run 42740196454](https://github.com/tpepels/piano_teacher/actions/runs/42740196454):
  **passed** after adding real FIFO seam/Pause, late-stage, exact recovery
  rollback, continuous tempo-map, meter, source-span and projection tests.
- [Python fast contracts — run 42740196541](https://github.com/tpepels/piano_teacher/actions/runs/42740196541):
  **passed**, including engine-owned Listen/Learn stage scheduling and
  minute-late preloaded handoff deadlines.
- [Real-score framebuffer — run 42740090984](https://github.com/tpepels/piano_teacher/actions/runs/42740090984)
  and [repeat/rest/header pixel capture — run 42740090826](https://github.com/tpepels/piano_teacher/actions/runs/42740090826):
  **passed** at the latest production-code revision (the subsequent commit
  modified only Godot regression tests).

This is a **focused software integration acceptance**, not full scientific
or physical acceptance. It does not waive the independent 24-shard original
notation audit (including unresolved Chopin symbols), USB/Bluetooth MIDI/audio
latency and disconnect/reconnect trials, the affected real Beethoven/imported
source-file reproductions, or genuine learner effectiveness. Phase 2 and
Phase 6 remain open against those independent exit conditions.


### 2026-11-10 — exact original-model import and measure-context safety

The earlier moving-bar audit is now supported by additional **original production
source** evidence and explicit deterministic Retry diagnostics, without claiming
the unavailable developer's affected Pathétique file or USB piano tests.

1. The Lumikey 0.3.0 original LH/RH ONNX providers retain their source
   ordering, hard manual/authored finger constraints, and authentic
   logits. Indexed overlap searches replace the previous repeated whole-piece
   `fixed.some/filter` scans, including recursive chord-completion rules.
   Independent left/right sessions run concurrently with one CPU thread each;
   output ordering remains left then right. Exhaustive overlapping/fixed-finger
   parity and all genuine provider tests run in
   [real-model CI](https://github.com/tpepels/piano_teacher/actions/runs/42792150649):
   **22 passed**, including both published model weight checks.
2. A full **1,164-note Moonlight Sonata I** `library.open` ->
   `score.native_layout` -> `score.semantic` -> repeated `library.open`
   test with those REAL providers is green in
   [run 42793022223](https://github.com/tpepels/piano_teacher/actions/runs/42793022223):
   869 ms cold import, 3,872 ms authentic native ink plus model, 282 ms
   cached import. The later run
   [42793776301](https://github.com/tpepels/piano_teacher/actions/runs/42793776301)
   additionally verifies that the original desktop `coda-midi` preference
   starts with a bounded learning stage (no whole-piece first lesson) at
   manual 20 BPM and retains the complete original piece as the final
   performance stage. Its measured cold import was 569 ms, native geometry
   2,887 ms and cached reopen 203 ms on the CI runner. No fingering algorithm
   or lesson source is silently disabled.
3. The immutable measure-strip seam index now protects the **leftward extent
   of actual clef/key/meter context at a later measure boundary**, as well as
   notehead, beam, slur, tie, hairpin, volta and finite barline ink. If the
   new header cannot be assigned wholly to its own future strip, that
   connected visual unit is merged. Godot's integration test catches the
   previously failing split; the updated
   [Godot run 42793455356](https://github.com/tpepels/piano_teacher/actions/runs/42793455356)
   and [real-score framebuffer run 42793455304](https://github.com/tpepels/piano_teacher/actions/runs/42793455304)
   pass.
4. Native `ScoreAssetSession` tracks exact errors across explicit Retry:
   an identical second failure is reported as repeated (while Browse
   remains available), successful retries clear the warning, and a new
   source revision resets its identity. The new regression is included in
   the [Godot run 42794260890](https://github.com/tpepels/piano_teacher/actions/runs/42794260890),
   **passed**.

**Status constraints:** issue #45's exact failing original MIDI was not
supplied, so its physical reproduction and remediation remain unverified.
Issue #46's specific Beethoven Pathétique input/screen/readability also
remains unverified; the long Moonlight representative covers real Coda
passage boundaries and backend tempo, not physical display speed. Full
24-shard scientific notation proof, original Chopin drawing failures,
long-run input/reconnection/audio latency and learner trials remain open.
**Phase 2 and Phase 6 are not certified complete.**


### 2026-11-13 — mastered-stage retention and bounded software verification

This continuation was verified locally on the working tree based on
`92d03a63`, including the pre-existing uncommitted changes. The results below
describe that local tree, not a new committed or remote CI revision.

- **G2-6, mastered stages:** feedback-driven Coda/Fukuda reselection now keeps
  the exact mastered scaffold definitions, source/version/content identities,
  earned tempos and visible progress. Unmastered stages continue adapting;
  the original remains last. Reopening recovers exact mastered candidates
  from the immutable catalog before filtering saved credit. Unknown historical
  or mismatched content keys remain uncredited. Real Bach MIDI regressions
  cover both original and scaffold cursors, repeated feedback and reopening.
- **G2-9, real-generator decisions:** new tests exercise actual accepted-warning,
  failed and correct original takes at passage and whole-piece scope. They
  check decision-time state preservation, safe continuation announcements,
  actual settlement/rerouting and retained mastery. Mastery still requires
  three accepted full-target performances. Independent review also checked
  rollback after a real-generator replan with mastered left-hand stages.
- **Notation audit execution:** post-group photograph selection now seeks into
  the sorted capture inventory instead of scanning every preceding frame for
  each connector. A 100,000-clock regression requires fewer than 32 indexed
  reads for three late witnesses. Existing clocks, strict onset exclusion,
  half-beat window, pixel criteria and negative controls are preserved.
- **Runnable focused acceptance:** the hybrid workflow uses current continuous
  score-flow/admission fixtures, absolute fixture paths and the existing Godot
  error-detecting wrapper. It honors `GODOT_BIN`, `godot` and `godot4` and
  includes the new mastery regressions. The newly reachable picker fixture
  now checks readable labels, exact provenance tooltips and selected indexes
  against the current UI. Fifteen executable script regressions cover errors,
  failure markers, path handling, binary selection and the documented modes.

| Local gate | Observed result |
| --- | --- |
| `scripts/ci-smoke.sh` with `.venv/bin/python` | **751 passed**, 14.30 s |
| `scripts/verify-hybrid-workflow.sh --all`, focused portion | **172 passed**, 15.35 s; all four Godot fixture failure counts zero |
| Same command, real MIDI generator corpus | **17 passed**, 7.17 s |
| Workflow and post-group photographic regression modules | **21 passed**, 1.58 s |
| `scripts/check-godot-syntax.sh` | `GODOT_STARTUP_SYNTAX_OK`; all 37 behavior/UI fixture failure counts zero |

Task-scoped checks additionally passed 87 adaptive/progress/settlement tests,
36 connector tests and 58 related notation contracts; these suites overlap
and their counts must not be added. All three implementation tasks passed
independent spec and code-quality review. The Godot gate retains existing
deliberate failure-injection diagnostics and teardown warnings; its successful
exit does not certify leak-free long sessions. The README/product contract
now reflects the sole desktop strategy and saved-selection migration already
implemented before this continuation.

**Remaining gates:** the full 24-shard source-symbol photographic audit and
unresolved genuine notation mismatches, the affected non-bundled Beethoven/
imported MIDI reproductions, USB/Bluetooth/audio/GPU practice acceptance,
original-paper parity, comparative learner outcomes and clean-machine release
acceptance remain open. The 25–45 minute full suite and long CI were not run
in this bounded continuation. Full Coda/Fukuda policy/tempo/transport decision
ownership still needs its explicit contract; per-note Fukuda contributor
regeneration remains a report-only option. **No phase is closed by these
software checks.**

### 2026-11-13 — full remaining-work continuation (in progress)

The owner requested all remaining and deferred work, then specified that
software testing should continue and physical hardware acceptance will follow.
The complete work inventory and evidence live in the current completion plan;
the following items have fresh local evidence:

- **Peace Piece source-onset blocker repaired and reviewed.** Beams crossed
  explicit tuplet boundaries, causing Verovio to apply a tuplet ratio to an
  ordinary following note. The beam-scope correction preserves original
  generated XML exactly except for beam elements, including IDs, onsets,
  durations, pitches, voices and ties. All four failing passages (31, 37, 53,
  67) pass. The old expected-failure allowance was removed: the complete
  17-piece chord/phrase corpus passes all 1,240 phrases, 3,687 chords and
  39,301 note glyphs; 216 focused regressions pass.
- **Polyphonic rest collisions and printed-rest ownership repaired and
  reviewed.** Repeated layout now measures the original baseline instead of
  accumulating prior trial offsets. Independent photographic ownership
  recognises stable fragments of the same source-end practice-rest pair,
  retaining strict current-frame/source-boundary and foreign-ink controls.
  Both original quarantined failures pass unmasked and their entries were
  removed. The final 81 controls and 240 related tests pass.
- **The Pathétique MIDI is available locally.** Its SHA-256 is
  `95723184515859acd321be57e8b4d1dcae3e18ebc57e0eab6895f33619c509a2`.
  Native first/middle/last-measure diagnostics pass on it, Fairytale of New
  York, the additional Prelude I file and Where Is My Mind. Earlier blanket
  missing-file statements are historical; actual full production Listen/
  retry/reopen and hardware acceptance remain their own obligations.
- **Current control/harness migrations are being verified.** The real
  embedded control journey passes 15 assertions. Ordered-signal regression
  checks also pass under controlled CPU load. These changes are awaiting
  their task review and complete current-head acceptance.

The original-paper [threshold/figure audit](docs/verification/fukuda-paper-audit-2026-11-13.md)
now records the inspected primary PDF and MIDI-domain substitutions. It does
not award numerical/figure parity or human effectiveness. Bounded P1 analytics
and its usable report, full teaching-decision ownership, deferred orchestration,
complete scientific notation proof, package/realtime acceptance and final
full-suite evidence remain active work. No phase has been closed.


### 2026-11-13 — interrupted Codex tree recovered and independently verified

The user's committed interrupted tree at `9b337e7` was repaired **directly on
`main`**, without a new strategy, presentation timeline, worktree, or parallel
generator. GitHub CI evidence for the four originally red workflows:

| Gate | Current verified software evidence |
| --- | --- |
| Python fast contract | [Green at `72b1df1`](https://github.com/tpepels/piano_teacher/actions/runs/43486658577) |
| Godot 4.7.2 startup syntax, score queue and coordinators | [Green at `7b6431c`](https://github.com/tpepels/piano_teacher/actions/runs/43482142798) |
| Embedded CPython native production UI, Moonlight journey and bridge | [Full runtime smoke green at `7b6431c`](https://github.com/tpepels/piano_teacher/actions/runs/43483147421) |
| Full imported-MIDI engraving and assessment recovery | [Green at `623dcce`](https://github.com/tpepels/piano_teacher/actions/runs/43481051758) |
| Independent dense real-score framebuffer | [Green at `72b1df1`](https://github.com/tpepels/piano_teacher/actions/runs/43486658564): 168 focused pixel checks passed, 1 skipped; full-source Hanon passed, Chopin remains **XFAIL**, not certified |

Corrections include extracting production smoke/test assumptions from deleted
`main.command_state` and obsolete standalone Fukuda fixture; preserving
untimed Learn versus explicit graded Practice during stage promotion; valid
assessment fixtures and command/atomic-settlement architecture checks; keeping
the P1 statistics receipt in tracked documentation; honoring the renderer's
actual 29-pixel left clipping boundary when the independent image verifier
claims visible noteheads; verifying real subdued two-sided ledger ink without
allowing corrupted Liszt fixtures to pass; and treating a photographed,
source-declared, partly clipped F-clef's *paired ornamental dots* as unresolved
clef context rather than invented augmentation dots. None of these accepts an
unobserved source note or waives the actual negative pixel controls.

**Independent full-symbol audit detail:** Hanon measures 37–40 now has **zero
full-symbol audit errors**. Chopin Nocturne Op. 9 No. 2, measures 13–16, still
has **208 independent symbol-verification errors** in the matching
[full-source artifacts](https://github.com/tpepels/piano_teacher/actions/runs/43486658564/artifacts/14069180172).
All 77 sampled written active pitch noteheads and all 7 ledger obligations
verify; six of ten beam groups remain mismatched or unverified (four verify);
four rest placement obligations mismatch despite all four rest glyphs being
recognized. Numerous stem/flag/rhythm/tuplet bindings remain unverified or
unsupported. The Chopin test is explicitly expected to fail and **must not
be represented as passing or silently retired**. Its original xfail wording
refers to historical beam discrepancies and is not evidence for the current
208-error breakdown.

The full 24-shard scientific source-symbol proof, remaining genuine Chopin
pixel/source mismatches, non-bundled imported-score reproduction, unified
Coda/Fukuda control-decision ownership, original-paper numeric/figure
parity, complete package/realtime recovery and the original physical
instrument/learner study gates remain open. Hardware, external learner outcomes
and clean-machine release acceptance cannot be inferred from CI. **Phase 2,
Phase 4, Phase 6 and Phase 7 exit gates have not been closed.**


### 2026-11-13 — complete-source audit coverage and Chopin rest-ink correction

- **Commit `b07d292`:** every original/learning/focused graphical case and
  one whole-source semantic case per source receives a stable repository-relative
  identity before capture. Every partition publishes an immutable case manifest,
  SHA-256 and exact original source/runtime identifiers. New global
  `complete-source-acceptance` refuses absent or duplicate cases, missing
  shards, foreign revisions, inconsistent inputs/runtime, partial runs and
  corrupted totals. The **24 source-shard workflow was triggered** as
  [run 43491850070](https://github.com/tpepels/piano_teacher/actions/runs/43491850070).
  Its complete source/pixel certification is not implied by the fast gate.
- **Commit `13f492f`:** the independent rest-placement measurement previously
  treated pale mint fixed playhead columns as bright neighboring notation.
  It now removes only the photographed mint transport overlay from the
  **clearance** mask. The unmodified raw bright-mask still governs suppression
  integrity, including foreign added ink. A negative test ensures neutral
  detached note ink still causes a collision. The matching
  [fast gate](https://github.com/tpepels/piano_teacher/actions/runs/43492443134)
  and [Phase 6 real-score framebuffer](https://github.com/tpepels/piano_teacher/actions/runs/43492443302)
  passed. The independent full Chopin pixel audit remains a separate
  acceptance gate; do not mark its four rest obligations fixed until that
  audit publishes fresh source-specific evidence.
- **Commit `60f3244`:** original-paper MusicXML/MIDI semantics now require
  *each* ledger row to be `verified`, not merely the absence of a mismatch.
  `unsupported`, `ambiguous`, `unverified`, malformed and empty ledgers
  cannot certify the complete source audit. The matching
  [fast contract gate](https://github.com/tpepels/piano_teacher/actions/runs/43492886601)
  passed.

**Open:** all 24 source-shard outcomes and their final joint receipt;
unresolved independent Chopin beams, rhythm symbols and connectors (existing
`xfail` remains unwaived); Coda/Fukuda decision-ownership and original-paper
numerical/figure parity; unbundled real-source reproductions, MIDI hardware/
audio-latency and long-session checks; clean-machine release and comparative
learner evidence. **Do not close the product or research acceptance phases.**


### 2026-11-13 — strict Chopin and adaptive-continuation recovery (current software receipt)

**Native pixel audit:** [real-source framebuffer run 43496832338](https://github.com/tpepels/piano_teacher/actions/runs/43496832338) on `7dbac6a` passed 228 focused tests, skipped one, and completed the full Hanon+Chopin source harness. Hanon remains zero-error. Chopin, Nocturne Op. 9 No. 2, bars 13–16 remains an **expected failure with 167 recorded independent source/ink errors**, reduced from 204. Its 10 source beam groups now contain seven independently verified groups, two recorded mismatches, and one unresolved group with no complete common photographed witness. The complete Chopin test remains quarantined; the workflow success is **not** Chopin acceptance. Corrections to source beam verification now (a) sample the entire actual multi-level beam stack, (b) avoid calling gutter-clipped endpoints missing stems, (c) inspect genuinely captured pre-onset photos when no onset/post-onset picture contains both ends. All changes preserve source-group and physical-pixel negative tests.

**Teaching and retry logic:** `b88e388`/`18dc3be` and `b6c2a10` correct an automatic recovery crash when a bounded retry began at an off-grid musical time inside a held note: the recovery interval uses the actual surrounding bar boundaries and validates repair actions, not only isolate actions. `4ea4d22`/`14615f1` fixes selected untimed Learn recovery being shadowed by an automatic timed whole-take response; ordinary guided steps, a source-selected remedial assignment, and an explicitly guided policy reply retain the correct respective owner and persisted attempt context. The targeted regressions run in both fast and source-recovery CI and passed at [fast gate 43498417304](https://github.com/tpepels/piano_teacher/actions/runs/43498417304) and [real-score recovery 43498417120](https://github.com/tpepels/piano_teacher/actions/runs/43498417120).

**Full 24-shard audit remains blocked, rather than certified:** [run 43491850070](https://github.com/tpepels/piano_teacher/actions/runs/43491850070) enumerated roughly 600 original/focused/learning cases **per shard**. The first four shards exhausted their real 1,680-second process limit after only a fraction of those cases (exit code 124). Their retained case logs contain actual failures across Chopin, Debussy, Satie, Bach, Danny Boy and Hanon. The global exact-shard aggregator already refuses absent, incomplete, mismatched and unverified source evidence, but the current corpus job architecture cannot finish full acceptance within its configured per-shard deadline. This needs a resource-bounded complete-corpus execution redesign, not relaxed assertions or reduced source coverage. Its failing cases are not overridden by the narrow green Hanon or fast tests.

**Exit conditions still open:** full original-score graphical and semantic source audit, remaining genuine/unverified notation mismatches, original Coda/Fukuda research parity and single-authority pedagogical integration, physical MIDI/Bluetooth/count-in/latency/reconnection testing, clean-machine release validation, and measured learner outcomes. The corresponding phases are **not complete**.


### 2026-11-13 — latest independent-source, combined-teacher, and clean-machine status

**Complete native Chopin source audit, not CI gate color:** The complete
independent original-symbol and framebuffer run
[43500813359](https://github.com/tpepels/piano_teacher/actions/runs/43500813359)
at `5624d49` reduced the Nocturne Op. 9 No. 2 measures 13–16 right-hand
**167 errors to 134** by correcting shared-chord flag obligations in the
source inventory and photographed feature verifier. The full run
[43502966732](https://github.com/tpepels/piano_teacher/actions/runs/43502966732)
at `c2ece10` retained 134 errors: seven of ten source beams independently
verified, two mismatches, one no-usable-common-photo beam. Exporting exact
Verovio stem abscissae (`c2ece10`) removed a layout approximation but did
**not** earn any extra independent source proof. The next full run
[43504145272](https://github.com/tpepels/piano_teacher/actions/runs/43504145272)
at `588c2f2` also retained **134** errors despite separating the
photographed independent tuplet bracket from physical beam ink: the next
remaining evidence failure is actual head-to-beam stem continuity. In the
real `native-10.95000.png` screenshot, the second stem's photographed
RGB 144/159/155 continuous anti-aliased column was below the old bright
pixel cutoff. Commits `c5168a2` and `05c416f` now admit exactly that
physical mid-tone ink when separately bound pale head/beam endpoints exist;
missing multi-pixel stems and broad polygons remain negative controls.
**Their full source audit was not yet completed when this entry was written.**
Chopin remains XFAIL, never accepted on the strength of a green CI job.
A different first group still lacks its authentic third-level backward hook;
a third long group lacks a uniquely registered complete screenshot. The
remaining meter, ledger-independent note features, note stems, flags,
tuplets and source-clock ownership claims also remain open.

**Selected Coda/Fukuda decision authority:** Commit `e400f4e` removes the
older error-family `RepeatedErrorPolicy`/`RemediationPlanner` fallback
from the only selectable hybrid course. Its original MIDI feedback now
selects transformed candidate lessons through the original combined
algorithm catalogue; the shared immutable teaching/transport coordinator
still owns persistence, note timing and mastery. The adversarial regression
monkeypatches the old planner to raise and passes in
[fast CI 43501077851](https://github.com/tpepels/piano_teacher/actions/runs/43501077851)
and [real-score recovery 43501078067](https://github.com/tpepels/piano_teacher/actions/runs/43501078067).
This is stronger algorithm ownership, **not** proof of numerical reproduction
of every original paper figure or external learner effectiveness.

**Release candidate and fresh-install software validation:** Commits
`137c5c5`/`4f4a45f` introduced a real stand-alone Linux x86_64 tarball
from the embedded CPython 3.14 and native Godot bridge; a separate fresh
Ubuntu container checks archive SHA-256, dynamic library resolution,
relocated imports and actual executable startup without development tools.
[Run 43502802706](https://github.com/tpepels/piano_teacher/actions/runs/43502802706)
proved the native/full-score build and tarball, but exposed missing host
`libcairo.so.2` in the clean container. Commit `4ea4bdc` supplies the
required Cairo/Pango OS runtime dependencies and strict `ldd` evidence.
[Run 43504715461](https://github.com/tpepels/piano_teacher/actions/runs/43504715461)
then proved bundled imports and all native links in that clean container,
but **the packaged Godot executable still exited 1**. Its redirected log
was not printed due to shell fail-fast; commit `51f8bb1` records the real
Godot error log even when startup fails. The subsequent clean-machine run
was pending; **packaged clean-machine acceptance is not certified**.
All of this is headless software evidence only, not keyboard/acoustic
acceptance.

**Outstanding blocking gates:** the full 24-shard audit is incomplete and
already has retained genuine symbol failures and hard resource timeouts;
Chopin source/ink is not complete; real physical USB/Bluetooth keyboard
timing and sustained-play/count-in/reconnect recordings are not supplied;
external-controlled learner outcomes, full original-paper figure parity,
and clean-machine publish acceptance are unproven. Do not close Phase 2,
Phase 4, Phase 6 or Phase 7 on the basis of these commits.

### 2026-11-14 — local regression triage after `fb7d04c` (matching Godot rerun pending)

A fresh user-side local run exposed **two independent test migration failures**
after the command lifecycle was extracted from Main, without demonstrating a
new production-level transport or grading error:

- `tests/test_measurement_controls.py::test_settings_controls_drive_typed_commands_and_present_results`:
  **743 passed, 1 failed** in the reported segment. Its Godot fixture still
  constructed `CommandSuccessEffects` with seven positional arguments
  although the class now accepts one presenter and signal connections.
  Commit `93ec567` uses the production effect signals and explicitly
  configures the existing `PracticeCommandCoordinator`, preserving the
  typed Settings/history requests and their outcome assertions.
- `tests/test_practice_screen.py::test_independent_practice_screen[app_busy_ack]`:
  **159 passed, 1 failed** in its segment, with Godot reporting invalid
  `App.command_state` followed by a 20-second Python subprocess timeout.
  Commits `a9432d0` and `0d43017` drive the current
  `command_coordinator.state` through the application's real response
  handler and independently assert clearing of busy state on both successful
  and failed acknowledgements, including count-in cleanup. The unrelated
  intermediate segment reported **304 passed**.

These commits change **test fixtures only**: no production safety checks,
original-source graphical obligations, physical MIDI acceptance, or independent
scientific audit assertions have been disabled. Source and commit inspection
confirms the modifications on `main`; **the matching Godot executable is not
available in this verification environment and no matching post-fix CI run
has been observed here**. Keep the two regression gates **unverified** until
they run against commit `0d43017` or a descendant. Rerun the affected Godot
cases, `scripts/ci-smoke.sh` and `scripts/ci-extended.sh`; a source edit alone
does not count as green CI.

**Unchanged open exits:** full original-symbol 24-shard execution including
Chopin physical beam/stem/flag/ledger evidence and resource-bound completion;
complete Coda/Fukuda original-paper/parity and teacher-decision proof;
real Pathétique/import/retry/reopen; physical USB/Bluetooth latency, count-in
and sustained input tests; clean Ubuntu executable release; long-session and
comparative learner studies. Phases 2, 4, 6 and 7 stay open.

### 2026-11-14 — short-session GPU warmup lifetime regression (software rerun pending)

The user's latest local run at `c72640a` confirmed the two earlier
command-fixture migrations: targeted tests **2 passed**, smoke **744 passed**,
and the extended run passed successive segments of **304, 160, 41, 1, 12,
and 1 tests**, before a later segment reported **12 passed, 1 failed**.
The failure was
`tests/test_note_reactions.py::test_engine_feedback_events_reach_the_production_ledger_once`:
authentic event/ledger checks completed (`NOTE_REACTIONS_FAILURES:0`), but
Godot emitted `Resumed function '_free_after_frames()' after await, but
class instance is gone` at `res://main.gd`, so the run correctly failed
despite correct musical feedback.

**Production correction:** `godot/main.gd` no longer awaits
`SceneTree.process_frame` in a Main-owned cleanup coroutine. The three-frame
GPU status-ink warmup now lives in `godot/status_ink_warmup.gd`, a temporary
renderer-owned `Node2D` with bounded `_process` lifetime. A parent or Main
teardown destroys it without any suspended Main method. Its head masks,
shader materials and normal rendering preparation have not been removed.
`tests/test_status_ink_warmup.py` additionally tests early owner teardown
and normal frame-bounded expiry; the original production-ledger test retains
its strict Godot error detection. Changes are in `a7e872c`, `5563a03`
and `20067ec` on `main`.

**Acceptance remains open** until the affected production-ledger regression,
new lifecycle test, smoke and extended suites pass on the same committed
revision with Godot 4.7.2. No independent notational, original-source,
physical MIDI or standalone-release acceptance is inferred from this fix.

### 2026-11-14 — local rerun after status-ink lifetime repair (all listed gates green)

Developer local checkout fast-forwarded from `c72640ab` to `20f61468`
and ran Godot 4.7.2 on Arch Linux.

- `tests/test_note_reactions.py` plus
  `tests/test_status_ink_warmup.py`: **2 passed in 4.54 s**.
  This verifies the previously failing production-feedback callback and the
  new renderer-owned GPU warmup lifetime regression together, with no
  reported `SCRIPT ERROR` or `ERROR:`.
- `scripts/ci-smoke.sh`: **744 passed in 13.05 s**, with
  `TRANSPORT_ALIAS_CALLERS: 0` and `TRANSPORT_OWNER_ONLY_OK`.
  The two earlier command fixture failures are also covered by the
  previous explicitly reported targeted 2/2 and smoke 744/744 passes.
- `scripts/ci-extended.sh`: all seven reported pytest sections passed
  **304 + 160 + 41 + 1 + 12 + 1 + 13 = 532 tests**.
  Its final `scripts/check_godot_parse.py --godot "$GODOT" --timeout 25`
  printed the normal Godot 4.7.2 banner; the developer then confirmed
  `echo $?` returned **0** immediately after the script. Therefore the
  **entire extended script passed on the local checkout at `20f61468`**.
  This is user-provided local exit-status evidence, not a GitHub Actions run.

This retires the specific observed command fixture and Main-teardown
regressions for this local tested commit. It does not constitute full CI,
24-shard original-symbol acceptance, physical MIDI/GPU/audio verification,
original Coda/Fukuda research parity, clean-machine release acceptance
or learner-study evidence. Those phase exit gates remain open.

### 2026-11-14 — full-suite Arch Linux acceptance: 4,895 passing, 144 nonpassing (not certified)

The developer ran the real `scripts/ci-full.sh` on Arch Linux / Godot
4.7.2 (approximately 31 min 20 s). Final pytest verdict:
**4,895 passed, 96 failed, 48 errors, 9 skipped, 1 xfailed**.
Unlike the earlier 744-pass smoke and 532-pass extended results, **the
full release gate is red and must stay open**.

The complete supplied terminal traceback was classified by test outcome,
without treating a secondary symptom as an independent production defect:
- **58** rows ended in `[Errno 122] Disk quota exceeded` or SQLite
  `disk I/O error`. The job retained results in
  `/tmp/pytest-of-tom/pytest-399/`. These need adequate disk/quota and a
  clean rerun before inferring an engraving/cache/SQLite regression.
  `PreprocessingCache._write` deliberately tolerates failed filesystem
  writes, which can also produce later cache-miss assertions. No evidence
  assertion is to be relaxed.
- **21** rows involve deleted `source-progression`/`coda-midi` desktop
  preference selection. The sole user-selectable strategy remains
  `coda-fukuda-midi`; direct MusicXML raster probes now explicitly set
  the **registered internal** `WARMUP_STRATEGY` only on an isolated
  fixture library instance. No deprecated preference has been restored.
- **30** rows are Godot/startup/integration failures with mixed potential
  causes; **35** other Python/pedagogical/notation failures remain
  independently actionable. These category counts sum to 144 and are
  diagnostic classifications, not counts of distinct root causes.
- A concrete old-owner regression occurs in
  `tests/godot/learning_statistics_native.gd`,
  `pending_navigation.gd`, `practice_interactions.gd`,
  `art_direction.gd` and `library_resume.gd`: old
  `App.command_state` references or the seven-argument
  `CommandSuccessEffects.new` fixture. These fixtures have been
  migrated to the already-authoritative `command_coordinator.state`,
  signal-based effects and explicit request adapter configuration.
  The ownership-source test now asserts reservation inside the
  extracted coordinator rather than Main.
- Genuine failed assertions additionally concern continuous-queue
  deadlines, pedagogical remediation and stage transitions, Perform
  weak-passage routing, source-bar seek, independent fingering pixel
  placement, source beam/stem audit, long-running native launch and
  potentially real disk-cache persistence. They remain open, not
  waived; retired internal remediation members must not be restored
  merely to make old tests pass.

**Code/test corrections on main, not yet locally rerun:** 2026-11-14
full-suite fixture commits `90494da`, `c24e6e3`, `a1975f9`,
`ac5928c`, `45c2e2b`, `1626192`,
`bd1c667`, `4517d83`, `b4d5f4b`.
These were reviewed against the current production constructor,
signals, registered strategy and coordinator API. No matching Godot
or pytest run has yet been observed after these commits.

**Immediate validation order:** examine `df -h /tmp`,
`quota -s` where supported, and `du -sh /tmp/pytest-of-tom`;
preserve relevant failed-run evidence before cleaning obsolete pytest
temporary runs. Then run the affected targeted migration/strategy
tests and full suite in a writable environment. Keep original
24-shard independent notation, physical MIDI, clean-machine release,
Coda/Fukuda parity and real learner-study exits separately open.

### 2026-11-14 — source-grid seek and weak-section retry repairs; fast full-suite ownership gate

The full-suite triage yielded two additional production-command defects:

- `PracticeEngine._practice_weak()` selected the weak source interval
  but, after `_prepare_practice()` cleared the previous review state,
  did not publish `retry_range`. It now republishes the chosen
  `start_beat`/`end_beat` pair from the same source-bound exposure.
  The original `tests/test_listen_perform.py` assertion for a later
  two-bar weak section remains strict (commit `fe0c972`).
- `PracticeEngine._seek()` could accept a manual source-bar seek
  even when `_seek_grid()` had no authoritative imported measure
  boundaries. It now rejects the request before applying a teaching
  command or mutating the paused transport. The original
  `tests/test_paused_seek.py` rejection test is retained
  (commit `43b258c`).

The original-source MusicXML pixel/camera fixtures are verified *by source
inspection* to require the registered internal `WARMUP_STRATEGY`.
The desktop setting validator still exposes only
`coda-fukuda-midi`. Their isolated fixtures set the internal baseline
for their direct importer probes (commits `bd1c667`, `4517d83`).

A new `tests/test_full_suite_fixture_owner_contract.py` checks that
the five full-only Godot fixture files cannot reintroduce Main-owned
`command_state`, that the mock action request is configured on the
actual coordinator, that the saved-library fixture uses signals, and
that source-only MusicXML tests use the internal strategy. It was added
to the existing fast push gate `scripts/ci-smoke.sh` (commits
`3f355e9`, `ce42197`).

**Verification status:** commits were written directly to `main`,
but **no matching post-fix local pytest/Godot runs are available**.
The reported 4,895-pass/96-fail/48-error full run remains the most
recent full-suite evidence. Do not promote this repair set to
accepted status without reruns; the other pedagogical, original
notation, resource, native-start and 24-shard gates remain open.

### 2026-11-14 — focused full-suite rerun: native camera, queued library and Perform Seek

The developer supplied a **post-`2b09537` focused rerun** of ten
previously failing/full-only test modules under Godot 4.7.2 on Arch Linux:
**91 passed, 15 failed, 6 fixture errors in 77.88 seconds**. This is a
targeted rerun, *not* a new `ci-full.sh` result.

- **6 camera setup errors:** `tests/godot/native_camera.gd:95` still read
  the deleted `App.command_state` after a genuine source model loaded.
  The same fixture replaced Main's request adapter without replacing the
  extracted coordinator's request port. Commit `b8356c3` uses
  `command_coordinator.state` and synchronizes the offline adapter with
  `command_coordinator.action_request`, preserving real reservation and
  acknowledgement semantics.
- **4 saved-library failures:** `library_resume.gd` configured the
  coordinator but omitted Main's `library_requested` signal binding.
  Therefore a queued **Continue** selection never opened after an accepted
  Pause. Commit `17a65fa` restores its actual deferred open. The shared
  native fixture had the same omission; `765b6b6` fixes the 11-case
  pending-navigation harness.
- **9 pending-navigation failures:** the fixture compared command bodies
  against only `action`, but today's valid transport requests also carry
  `presentation_deadline_ms`, `continuation_clear_beats`, and
  `continuation_header_beats`. The updated recording adapter explicitly
  validates these fields (finite positive deadline and nonnegative finite
  geometry), then compares the original ordered user commands. Commits
  `f84413c` and `2a05969` keep the tests strict and parser-safe.
  The shared fixture's queued-open signal fixes the separate selection case.
- **2 Perform→Seek grading failures:** `teaching_manual.choose_manual`
  retained `mode="perform"` in the *prepared exposure* for a paused source-bar
  Seek. The immediate `_seek()` display was Practice, but
  `score_ready` consumed the retained exposure and switched the actual
  graded take back to Perform, producing `performance_complete` for an
  incomplete section. Commit `cf7f79a` makes a non-Learn source-bar Seek
  select Practice at the authoritative decision layer.
  `tests/test_paused_seek.py` now requires Practice still be active *after*
  the score acknowledgement (`e6f3a9a`). A small pure decision test
  guards both Perform and Practice entrances (`aea447c`).
- **Early failure detection:** `tests/test_full_suite_fixture_owner_contract.py`
  now covers the native camera adapter and queued library signal wiring,
  while `scripts/ci-smoke.sh` includes the cheap Seek-mode decision test
  (commits `64819f6` and `7bcc798`).

**Acceptance:** these repairs have been committed to `main` but **no matching
post-fix local Godot run is yet reported**. Keep all 21 observed failed/error
cases open until the ten-module targeted suite passes, and keep full CI
and independent 24-shard original-source audit unaccepted until each is run
to completion. No legacy owner or compatibility code was restored, no
assertion was deleted, and original notation, physical MIDI, release and
pedagogical proof gates remain unchanged.
