# Architecture cleanup: phased, behavior-preserving

## Audit (first-party production code, 2026-10-27)

The largest responsibilities are concentrated in three files:
- `godot/main.gd` (~3,500 lines): screen construction, navigation, backend
  polling/state interpretation, interaction effects, and layout. In particular,
  `_build_interface` and `_on_state` are oversized.
- `godot/notation/native/view.gd` (~2,950 lines): renderer, collision density,
  symbol geometry, annotation positioning, and continuous loop display.
- `piano_teacher/server.py` (~2,420 lines): MIDI lifetime, application commands,
  practice and recovery state machines, cached engraving and HTTP state payloads.
  `control`, `_update`, and `state` are especially long.

Audit/infrastructure code (`visual_coverage.py`, `feature_pixels.py`,
`check_native_verovio_overlay.py`) is also large; it must stay independent of
production engraving and should not be made to share its recognition algorithms.

## Stable boundaries

1. **Learning/domain** owns source notes, lesson stages, grading and recovery
   decisions. No UI or networking dependencies.
2. **Backend application** orchestrates the above under its existing lock;
   separate MIDI device management, practice transport, commands and read-only
   HTTP state projections. Preserve the existing `PracticeEngine` API.
3. **Notation** owns immutable source timing and semantic positions. The native
   view owns drawing; pure collaborators handle collision spacing, layout
   calculations and independent annotation policy. Preserve one beat-to-pixel
   projection and note identity.
4. **Godot UI** splits screens and UI-only presentation into separate components,
   while `main.gd` owns navigation and API coordination. Avoid circular
   screen-to-service references.
5. **Verification** remains independent of renderer internals. Keep actual
   framebuffer tests and negative controls; do not weaken evidence thresholds.

Dependency direction: domain <- application <- adapters/UI; native engraving
may use pure geometry/layout helpers but never import verifier internals.

## Incremental refactor sequence

- [x] Extract native ink-collision density into a stateless layout collaborator.
  Its inputs are actual ink rectangles; its only outputs are density and a
  diagnostic witness. Preserve exact existing spacing semantics.
- [x] Separate hand-stage and guided-learning state projections from the
  engine using captured facts and pure functions; preserve API field names.
- [ ] Continue isolating remaining state/HTTP fields from engine transitions,
  with an explicit immutable snapshot boundary.
- [x] Extract source-bar to course-section selection from the backend command
  handler into a pure, separately tested learning-navigation helper.
- [x] Extract read-only continuous beat/velocity projection into a pure
  transport module with explicit phase snapshot and deterministic tests.
- [x] Extract immutable recovery/HUD metadata from `_update` to a pure
  source-bar projection; keep decision detection, tempo adaptation, saving
  and scheduling under the application lock.
- [x] Separate the command dispatch path from focused engine-owned handlers
  for source navigation, restart, pause/resume and stage selection. The public
  control method still owns the re-entrant lock and its prior error semantics.
- [x] Split the backend update loop into focused methods for MIDI health,
  pending feedback settlement and rolling-error recovery transitions, without
  moving clock/tempo ownership outside the locked engine.
- [x] Give SQLite schema initialization, versioned progress restoration,
  durable mastery/tempo persistence, and scoped path deletion to
  `ProgressRepository`, independent of the engine. Keep a documented legacy
  `db` alias for existing tests. The repository initializes LearnerStateStore
  and its schema as part of owning the local progress database.
- [x] Create an independent AssessmentService that owns bounded source-note
  grading, per-source-bar performance reviews and live feedback mapping.
  The engine retains recorder, renderer, tempo and mastery transitions.
- [x] Give mutable visual transport state and preparation scheduling to
  `VisualTransport`. Engine command/clock callers retain compatibility aliases
  with no duplicated storage; the transport component owns reset, take
  continuation, rewind clocks and absolute visual beat projection.
- [x] Isolate the post-settlement completion path from the polling/rolling
  recovery loop. CompletionRoute gives precedence to performance, explicit
  bounded section review, partial recovery and full-passage practice; no
  state updates before settlement and no curriculum advancement for partials.
- [x] Extract the post-performance side effects into distinct engine handlers
  for performance review, bounded review, partial recovery and full-passage
  progression; all remain under the existing engine lock. Add tests proving
  that partial paths cannot confer mastery or schedule unwanted auto-advance.
- [ ] Continue reducing the engine state/HTTP payload assembly through
  immutable projections, preserving source-note identities and poll clocks.
- [x] Split the giant _build_interface method into separate Home, Library and
  Practice builders, preserving construction order and event wiring.
- [x] Extract the modal source-measure picker into its own Godot Control,
  with independent source-bar input, resize and selection behavior; main.gd
  owns HTTP action dispatch and navigation via picker signals.
- [x] Extract Settings screen construction into a standalone signal-driven
  control. The application retains settings API operations and state updates;
  the view owns its widgets and visual structure.
- [x] Extract the settled-performance review strip as a signal-driven Godot
  component with isolated summary rendering and copy-on-present snapshot.
- [ ] Move the remaining Home/Library/Practice screen construction into
  independently testable components with signals and explicit state inputs.
- [x] Extract simultaneous-voice stem selection, column-collision spacing
  and connected-component recentering into pure native voice_layout.gd.
  The native view supplies source note Y positions, beam directions and
  authentic glyph bounds. Rendering retains the original timing geometry.
- [x] Move fingering's candidate ordering, spatial bin collision checks
  and placement packing into a pure layout collaborator, retaining real glyph
  obstacles and source-note Y coordinates in the native view.
- [x] Separate polyphonic rest-lane selection and rectangle collision scoring
  into a pure layout policy; native view still supplies authentic glyph ink.
- [ ] Continue separating native rendering passes and source ornament layout
  without sharing production logic with the independent notation audit.
- [ ] Modularize the audit coordinator separately from source-driven proofs;
  preserve its fail-closed behavior and resumability.

For each slice: measure duplication/coupling first, preserve public contracts,
add focused positive/negative tests, run quick CI, and commit separately.
Do not move code merely to make files shorter. No simultaneous architecture
rewrites or behavior changes while notation quality is being investigated.

## CI policy (2026-10-28)

Automatic push/PR checks run `scripts/ci-smoke.sh` only. It compiles Python,
checks the architecture's narrow contract tests, and parses the Godot main
scene. Test execution is bounded to 105 seconds and scene parsing to 25
seconds; the GitHub job has a seven-minute outer limit including dependency
setup. This is a **smoke gate, not a notation-quality certification**.

The older, much broader `bash scripts/verify-notation.sh --ci` remains
available explicitly for pre-release regression verification; the complete
`./scripts/verify-notation.sh` additionally runs the source-driven corpus
audit. Neither is scheduled on every commit. Do not silently weaken those
independent tests to make automatic CI faster.

Release verification uses the separately defined `native-release-regressions.yml`
reusable/manual workflow. It retains the original broad `--ci` suite and
exact-revision output; normal pushes do not trigger it. A passing automatic
smoke check is **not** grounds to publish a release or declare the full
notation corpus verified.

## Completion program (2026-10-28, baseline `a093c5c`)

The current checkout is newer than the original handoff. Baseline automatic
smoke: 50 tests passed and Godot main parse succeeded. The latest broad release
regression immediately before this program was 976 passed / six skipped. That
is baseline evidence, not final verification of the upcoming extractions.

### Target and decisions

Use composition with explicit owned data, rather than mixins, renderer/view
back-references, or moving engine methods into helpers that accept the whole
engine. Keeping the monoliths and adding forwarding wrappers would preserve
coupling; a rewrite of progression/engraving would risk behavior unnecessarily.
The chosen approach is incremental extraction of complete responsibilities.
The user's request authorizes design/implementation decisions and direct main
commits; no approval menu, worktree, feature branch or per-phase pause is needed.

- Backend: application session owns transitions under one lock. MIDI lifetime,
  score preparation, grading, persistence, transport and immutable read models
  have distinct owners. HTTP consumes snapshots and commands, never engine
  internals. Preserve existing public command/state payloads and device timing.
- Godot UI: main is the composition/navigation boundary. Screens own controls,
  responsive layout and presentation state; signals carry user intent. Backend
  requests/state polling and score transport are explicit services/presenters.
  No screen accepts the main node or reaches into its private widgets.
- Native notation: the shared view owns transport; a score layout owns the
  source index and geometry caches; connector geometry owns endpoint/flag
  clearance; engraving passes consume layout and an explicit canvas; fingering
  owns annotation layout/editing. Collaborators never call back into main/view.
  One beat axis and density, source identities and authentic glyphs are fixed.
- Verification: independent source expectations, photographed evidence,
  recognition/registration primitives, coverage accounting, batch execution and
  diagnostic publication have separate owners. Shared pixel primitives break
  lazy import cycles without borrowing production geometry or thresholds.
- Domain/importing/rendering adapters remain separated. Retain public import
  paths only where they are real API contracts; eliminate test-only aliases and
  duplicated mutable storage once callers are migrated.

### Execution checklist

- [x] Complete whole-repository inventory, dependency/cycle audit and ownership map.
- [ ] Extract backend session services/read models and reduce PracticeEngine to orchestration.
- [ ] Extract Home/Library/Practice screens and API/state coordination; reduce main.gd.
- [x] Give native score geometry/index/cache lifecycle an independent owner.
- [ ] Separate connector geometry, engraving passes and fingering annotation lifecycle.
- [ ] Separate verification source expectations, pixel registration and feature proofs; break cycles.
- [ ] Separate corpus case planning/execution/checkpoint/publication from audit CLI composition.
- [ ] Remove obsolete internal aliases/scaffolding; audit all remaining production files for cohesion.
- [ ] Add contract/behavior regressions for each component; preserve real pixel positives/corruptions.
- [ ] Keep automatic CI bounded; run focused tests at each extraction and broad final regression separately.
- [ ] Fresh independent reviews for significant changes, fix failures, coherent main commits.
- [ ] Final size/dependency inventory, architecture documentation, clean main checkout.

### Validation and review constraints

Each extraction first pins its independently callable contract and existing
behavior; then focused tests, Python compilation and/or Godot checks run before
its commit. Native layout changes additionally use real-framebuffer proof and
corruption controls. No threshold, source clock, onset, hand assignment, grading,
loop duration, recovery offset or UI interaction may change to simplify a split.
Automatic CI remains the bounded smoke gate; release/corpus checks run separately
when needed. Avoid a full 24-shard audit during architectural work.

The 1,000-line diagnostic is not a mechanical limit: the final inventory records
concrete reasons for cohesive exceptions. Giant context objects, component
cycles, view/engine callbacks and duplicated state fail the review even if files
are small. Third-party addons, generated assets, fixtures and lockfiles are not
first-party architectural monoliths.

### Progress ledger

- Baseline `a093c5c`: clean main; smoke 50 passed, Godot parse exit 0.
- Initial inventory: server.py 2165, main.gd 3258, native/view.gd 2904,
  visual_coverage.py 1632, feature_pixels.py 1482, audit CLI 1755 lines.
- Static Python scan: 93 modules; verification lazy cycles involve
  raster_matching/phase3_pixels/symbol_pixel_proof and connector_pixels/feature_pixels.
  music/fingering.types requires distinguishing typing-only from runtime coupling.

- Native geometry extraction: `ScoreLayout` owns source indices, note/chord/voice
  geometry, rest lanes and cached positions independently of a CanvasItem.
  Standalone headless contracts RED→GREEN; focused 3 + 12 + 31 tests passed.
  A custom-staff test fixture now injects its geometry policy rather than
  overriding canvas geometry; expected pixels and corruption checks unchanged.
  Independent review found no issues. Remaining forwarding accessors are
  transitional callers and will be removed during native pass separation.

- Native contour-spacing extraction: `InkGeometry` owns authentic alpha-row
  cache and global density/witness calculation. Shared barline geometry now
  belongs to score geometry and receives explicit source-offset parameters.
  New headless contract RED→GREEN; 13 independent/pixel tests passed;
  independent review found no math or ownership regressions.

- Native connector extraction: `ConnectorGeometry` owns authentic tie/flag
  clearance and beam/endpoint plans. Source visibility and clock offsets are
  explicit inputs, not view callbacks. Independent review caught stale viewport
  state on geometry-policy replacement; a new failing behavior case reproduced
  Y=40 instead of 220, then setter synchronization fixed it. Three headless
  contracts and fresh 43 real connector/beam/flag regressions pass. A fixture's
  obsolete `layout` field was renamed `beam_plan`; assertions unchanged.

- Native annotation integration: `FingeringAnnotations` owns layout, metrics,
  editing and label metadata; `FingeringObstacles` owns source reservations and
  sprite-envelope cache; `SourceVisibility` supplies one recovery clipping rule.
  No helper calls back into the view. Review caught viewport synchronization;
  application tests additionally exposed the shared view replacing its axis on
  clear. A new failing clear/rebind contract now passes after explicit rebinding
  and owner-driven cache clearing. Corrupted reservation fixtures inject the
  old obstacle policy rather than editing a moved view implementation.
  Fresh aggregate: 62 passed / four deliberately inapplicable fixture variants
  skipped, including real XML/Chopin/Hanon application popup corrections.

- Audit capture extraction: `scripts/audits/capture_store.py` owns provenance,
  atomic publication and interrupted publication recovery; `capture_runner.py`
  owns actual Godot capture independently of proof execution. Input identity
  includes every extracted audit module. New component contracts RED→GREEN;
  owner suites 61/35/41 passed and independent review ran 55 tests with three
  unrelated CI tests deselected, no blocking findings. No retained audit files
  or corpus were written. Worker stage ownership and CLI decomposition follow.

- Native fitting extraction: `ViewportFit` chooses the existing ordered staff
  candidates, two-pass rest lanes, global density and legible fallback without
  owning the beat axis. Vertical geometry fitting/cache moved to `ScoreLayout`;
  cache now records its explicit height/limit inputs. Independent review found
  unchanged equations and witness selection. Four headless contracts and 58
  real register, boundary, measure-width/velocity and layout tests passed.

- Whole-repository baseline inventory and cross-domain audit findings saved in `docs/architecture/inventory-before.json` (including static import edges with typing/lazy distinctions).

- Source-only dependency cleanup: library health and preprocessing import
  directly from the canonical importer, without initializing the page-rendering
  facade. Two fresh-process contracts failed before the change, then the
  import/cache/health/generator suite passed 17 tests. Generator documentation
  now reflects actual variant consumption. Baseline inventory includes all
  180 first-party Python/GDScript/shell/Node-bridge files.

- Backend immutable state slice: frozen value snapshots separate phase/payload
  projection from locked engine sampling and stateful teaching/input adapters.
  Fourteen baseline/current payload and clock-call sequences matched; owner
  42/116-test focuses and independent 33-test review passed with no regressions.
  Synthetic 1024-mark responses add ~4.2ms copying (ordinary polls <0.4ms),
  bounded and not an established CPU defect. Three expanded-suite baseline
  expectations predate exact overshoot/restart preparation and will be updated
  with exact deadline and lifecycle assertions in a separate test correction.

- Library UI slice: standalone screen owns widgets, search/debounce, catalog,
  recent-row deduplication, error/health presentation and responsive layout;
  signals carry open/resume/refresh/check intent. Main owns only request/route
  consequences. Shared construction primitives are stateless. Fresh owner
  focus 19 passed and independent review 14 passed with no findings.

- Verification foundation slice: photographed ink/context/motion, head
  registration and captured-frame lifetime have explicit independent owners.
  Both runtime cycles (including lazy imports) are removed. Existing algorithms,
  sign conventions, source/unison ownership and budgets are unchanged; 11 saved
  reports match byte-for-byte. Owner focuses 30/123/476/125 passed; independent
  review normalized 12 moved and 117 surviving bodies against baseline, checked
  40 catalogue glyphs, and ran 30 + 17 targeted tests without findings.
