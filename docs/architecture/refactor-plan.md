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
- [ ] Move the remaining Home/Library/Practice screen construction into
  independently testable components with signals and explicit state inputs.
- [x] Extract simultaneous-voice stem selection, column-collision spacing
  and connected-component recentering into pure native voice_layout.gd.
  The native view supplies source note Y positions, beam directions and
  authentic glyph bounds. Rendering retains the original timing geometry.
- [ ] Continue separating native fingering/layout and visible drawing passes
  without coupling verification logic to production renderer internals.
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
