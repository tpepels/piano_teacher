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

## Active plan — PracticeEngine architecture replacement (2026-11-21)

**Status: source decomposition integrated and core verified; final software acceptance is still open.** Baseline: `f8bd9cd`; `piano_teacher/server.py`
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

**Source:** `55e31dd2` on `main`; [core CI 44906137747](https://github.com/tpepels/piano_teacher/actions/runs/44906137747)
passed **103 Python scenarios, 4 skips**, Python coverage **73.5% lines /
53.3% branches**, Godot syntax OK and all four native-source behaviour
groups with zero failures. Native embedded production/repertoire and strict
relocated package verification on this source are **not yet accepted**;
physical instrument/graphics/audio and an independent clean machine remain
unverified. The full embedded/native/repertoire and relocated-package verifier
**passed on `9fef7780`** ([run 44905418627](https://github.com/tpepels/piano_teacher/actions/runs/44905418627)):
native registration, real-score loading, two `PACKAGE_CONTENTS_OK`
checks and `PASS LOCAL EMBEDDED PRODUCTION CONTROL`. That source
predates the final command split and **does not certify `55e31dd2`**.

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
  frozen pause time, count-in and forward continuous scroll. No cold asset
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
