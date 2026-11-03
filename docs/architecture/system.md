# Piano Teacher architecture

This is a technical contract. The sole active phase plan is [ROADMAP.md](../../ROADMAP.md).

The application is one Godot process with an embedded Python practice engine,
connected through a native in-memory command queue. Source notes,
written notation, teaching policy, playback time and photographed verification
are separate representations. A renderer never determines grading truth, and
reported renderer geometry never counts as independent pixel proof.

## Backend ownership

`PracticeEngine` is the application transaction boundary. Commands and MIDI
callbacks acquire its existing reentrant lock. Domain objects own curriculum,
teaching targets and recovery decisions. `ProgressRepository` owns the progress
database and durable restoration; `AssessmentService` performs bounded grading
and builds source-bound feedback. `VisualTransport` owns continuous visual time
and preparation scheduling. Pure transport/recovery/navigation projections take
captured facts and return values.

State responses cross an immutable boundary: the engine captures primitive
facts under its lock; frozen `SessionSnapshot` families recursively detach
nested collections; `project_session_state` returns a fresh JSON-shaped payload.
It cannot call the engine, sample clocks, mutate teaching or access a live plan.
The caller retains the established clock sampling order and stateful adapter
operations.

`ScoreArtifacts` receives a frozen `ScoreSelection` and owns selected notation
compilation, semantic projection, canonical Verovio source engraving and
native atlas/fragment preparation. There is no page-PNG renderer or
non-native score mode. It has no engine or plan reference. One compilation
feeds model and native rendering; durable keys bind source/stage/hand.
The engine owns source revisions and acknowledgements, rather than the cache.

`MidiConnection` owns ports, discovery/reconnect deadlines, physical input
activity and hardware-probe diagnostics. The engine supplies an event callback
and owns the musical consequence of losing or selecting a device. A detach /
cancel / close sequence preserves callback and cancellation ordering. Hardware
arrival timestamps are captured before acquiring the application lock.

Source importing, library health and preprocessing depend directly on the
canonical importer. The interactive application exposes only native
notation plus its semantic model. Offline page engraving and verification
utilities remain independent of the active session and are not selectable
presentation backends.

## Composable MIDI curricula

`LessonGenerator` instances own complete curricula; a registry selects the
whole-piece generator, not a conditional branch in `LearningPlan`. The
reusable `compose_lesson_definitions` merges compatible exercise stages
without changing source identities. `AdaptiveComposedLessonGenerator` selects
source-safe passage stages supplied by independent `passage_stages` contributors.
`with_feedback` forwards graded source-ID error families; source-ID-only
participants use `with_mistakes`. The practice engine does not branch on
Coda/Fukuda algorithm identifiers.
See [composed MIDI generators](composed-midi-generators.md) for contracts,
course identity, caching, verification and Coda + Fukuda behavior.

## Godot client

Screens own controls, responsive layout and their presentation/editing state.
They receive snapshots and emit intent signals with values. Screens never retain
`main.gd` or call its private methods. Home owns the captured Continue target;
Library owns catalog filtering/debounce and health presentation; Settings owns
tempo drafts, folder selection and the device menu. Stateless `UIFactory`
constructs common controls without an application dependency. Lesson owns its
path, hand/activity choices and captured reset confirmation; its overview session
owns request identity and retry, while the step selector owns numeric selection
intent. The source-measure
picker and performance review are independently usable controls.

Application coordination owns navigation, in-process command results and
resource readiness. Clock interpolation, source revision acknowledgement and continuous
score presentation must retain their established ordering. Remaining application/screen ownership critiques and acceptance gates are
tracked only in [ROADMAP.md](../../ROADMAP.md).

## Native notation

`native/view.gd` is the canvas composition boundary. It validates complete
source engraving, chooses one global density before playback, orchestrates
visible source copies and preparation rests, and publishes actual painted note
positions for UI feedback. It owns whole-frame output and retained preparation
history, rather than caches for every notation feature.

- The shared view/Timeline owns source beat projection and transport snapshots.
- `ScoreLayout` owns the source index, staff geometry, voice/chord offsets,
  rest lanes and vertical fitting caches. Viewport size is an explicit input.
- `InkGeometry` owns authentic texture alpha rows and collision-density evidence.
- `ViewportFit` chooses a score-wide staff gap/density without installing a
  second axis or altering source timing.
- `ConnectorGeometry` owns beam plans, tie endpoints and flag clearances.
- An ephemeral `RenderPass` owns one source copy's visibility/color context and
  painted positions. The view aggregates repeated instances for feedback.
- `SymbolPainter` draws authentic notes, rests, beams, ties, slurs and tuplets.
  `ContextPainter` draws clefs, keys, meters, barlines and preparation measures.
  They borrow source geometry and use an explicit transient canvas. Neither
  retains or calls back into the view.
- `FingeringAnnotations` owns placement, label metadata and editing. Its obstacle
  component owns reservations and sprite-envelope caches. Annotations cannot
  modify canonical source notes, hand assignment, timing or grading.

Changing geometry policy rebinds collaborators and synchronizes viewport size.
Clearing a score rebinds the new shared timeline before clearing owned indexes.
A new score/atlas invalidates only its dependent caches. Pixel corruption
fixtures inject the real geometry or painting policy that owns the behavior;
there are no old view overrides pretending to test moved algorithms.

## Independent verification

Expected symbols come from independently read source XML or a declared MIDI
quantization candidate. Pixel measurement uses retained actual framebuffers and
external Verovio/font references. Unsupported, ambiguous and missing evidence
stay in coverage denominators.

`pixel_ink`, `pixel_context`, `pixel_motion`, `head_registration` and
`captured_frames` are lower-level evidence owners. Feature status/source facts
and glyph evidence have single owners; stems, detached adornments, structure
and ledgers have separate proof families. `feature_pixels` coordinates source
requirements and physical-ink claims per call. The separate visual ledger owns
independent source obligations, occurrence binding and construct-specific
acceptance. Its policies import neither detectors nor image libraries, so a
producer's aggregate success flag cannot authorize an original obligation. Detectors do not call back into
coordinators, import the application or borrow native layout. Bounded image/font
caches retain the existing budgets. Generic SVG structure and isolation live in
`source_svg`, below both asset generation and independent reference readers;
it has no renderer, image-classifier or application dependency. Moving a proof preserves thresholds and
serialized reports; positive fixtures and deliberately corrupted controls
exercise the same acceptance rules.

## Audit execution

Capture, proof and orchestration have distinct lifetimes. `capture_store` owns
provenance and atomic publication/recovery; `capture_runner` owns Godot capture.
`StageRecorder` owns a case checkpoint, passed explicitly to execution.
`worker_protocol` serializes case execution/results; `worker_ownership` validates
process identity and session ownership; `job_executor` bounds resources, queues,
deadlines, recycling and cancellation. No process-global current-case variable
routes checkpoint updates. Source and dependency identities cover the extracted
modules, so changed code cannot silently reuse an old verdict. Successful
captures remain independently reusable when only proof code changes.

## Validation policy

`scripts/ci-smoke.sh` is the bounded automatic architecture/parse gate. The
explicit `scripts/verify-notation.sh --ci` runs broader real-frame, corruption,
progression and interruption regressions. The full 24-shard audit is a separate
operation; a refactor's green smoke gate does not certify the entire corpus.
The parse gate checks emitted diagnostics as well as Godot's exit code, with a
25-second bound; an emitted parse error cannot pass by exiting zero. Dated architecture inventories and superseded refactor plans are preserved
under `docs/archive/development/`; they are not active plans.
