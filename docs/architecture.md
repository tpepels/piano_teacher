# Application architecture

[Practice flow](practice-flow.md) defines learner-visible behaviour.
[ROADMAP](../ROADMAP.md) records product decisions, phases and dated verification.
This document is the current technical overview; [development](development.md)
covers operation and acceptance, and [reference](reference.md) covers fingering,
learning evidence, privacy and research limitations.
The ownership descriptions are the required contracts. The
[2026-11-20 source audit](#remaining-work--source-audit-2026-11-20)
retains the original six findings as historical evidence. The corresponding
correction commits and software verification are recorded below; physical
MIDI, audio and visual acceptance remain separate.

### Composition closure audit — 2026-11-21

The pre-audit composition file retained many direct imports from the
former 2,783-line facade despite constructing no objects from those
imports. It now imports the concrete current application owners only,
and the four unused constructor ports discovered in the extracted
services have been removed at both ends. `PracticeEngine` remains a
343-line public facade and constructs its services through
`application/composition.py`, without injecting a facade or
global service locator into the application services. Full dependency
closure and packaged/native acceptance remain separate requirements.

## One desktop runtime

The product is one Godot 4.7 desktop process with embedded CPython, authentic
Verovio notation, one immutable score stream and one MIDI/transport timeline.
The product imports MIDI. Generated MusicXML is an internal engraving format;
missing expression or editorial information is never invented from MIDI.

[Main](../godot/main.gd) composes scenes and services and connects their signals.
[PracticeEngine](../piano_teacher/server.py) is the locked application/API
boundary. Neither is another lesson policy, score ledger or clock owner.
There is no separate Python server, HTTP/UDP bridge or compatibility renderer.

| Responsibility | Authoritative owner |
| --- | --- |
| Course windows, hands, tempo and mastery | [PracticeFlowLessonGenerator](../piano_teacher/practice_flow_course.py) and [teaching decisions](../piano_teacher/teaching_decisions.py) choose one immutable result. Other registered generators retain their own explicit strategies. |
| Selected curriculum and saved progress | [LearningPlan](../piano_teacher/learning.py), validated [SessionCommands](../piano_teacher/application/session_commands.py) and [ProgressRepository](../piano_teacher/progress_repository.py). |
| Listen / Free / Tempo preparation | [Exposure preparation](../piano_teacher/application/exposure_preparation.py) materializes the chosen source; [PracticeFlowCourseSession](../piano_teacher/application/flow_course_session.py) presents its step and messages. |
| Guided targets | [GuidedSession](../piano_teacher/application/guided_session.py) owns the selected fragment, derived beat range, controller, hints and recovery return. |
| Timed authorization | [PlaybackCoordinator](../piano_teacher/application/playback_coordinator.py) owns source-bound intent/reserve/present/cancel transactions. |
| Playback lifetime | [PlaybackSession](../piano_teacher/application/playback_session.py) owns running/mode/automatic flags, take epoch, readiness, count-in and pause/resume effects. |
| Musical time | [VisualTransport](../piano_teacher/visual_transport.py) stores epochs; the pure [MusicalScheduler](../piano_teacher/application/musical_scheduler.py) calculates deadlines; [TempoMapCache](../piano_teacher/application/tempo_map_cache.py) retains the selected immutable map. |
| Physical input | [MidiIngress](../piano_teacher/application/midi_ingress.py) preserves calibrated arrival timestamps and the source-bound grading gate. |
| Listen sound | [ListenSession](../piano_teacher/application/listen_session.py) owns asynchronous audio preparation and score/audio readiness. |
| Assessment and settlement | [AssessmentService](../piano_teacher/assessment_service.py), [assessment policies](../piano_teacher/application/practice_assessment.py), [AttemptRuntime](../piano_teacher/application/attempt_runtime.py) and [AttemptSettlement](../piano_teacher/application/attempt_settlement.py) retain one verdict, take and durable result. |
| Source installation and correction | [SourcePreparationSession](../piano_teacher/application/source_preparation_session.py) owns mutation serialization, source generation and fingering correction identity. |
| Current/future engraving | [ScoreArtifacts](../piano_teacher/application/score_artifacts.py) compiles a frozen selection; [TeachingContinuation](../piano_teacher/application/teaching_continuation.py) retains exact future source/asset identities without selecting another outcome. |
| Commands and accepted state | [PracticeCommandCoordinator](../godot/practice_command_coordinator.gd), [ApplicationStateInbox](../godot/application_state_inbox.gd) and [ApplicationPollSession](../godot/application_poll_session.gd) own request sequencing, accepted snapshots and polling. |
| Presentation reconciliation | [PracticePresentationSession](../godot/practice_presentation_session.gd) reconciles state and score readiness; [PresentationTimeline](../godot/presentation_timeline.gd) owns forward visual projection. |
| Physical admission and promotion | [ScoreAdmissionGateway](../godot/score_admission_gateway.gd) negotiates exact receipts; [ScoreSceneController](../godot/score_scene_controller.gd) promotes exact-revision renderers; [ScoreRunway](../godot/score_runway.gd) prepares assets and retains outgoing layers. |
| Immutable ink | [ScoreStreamController](../godot/notation/native/score_stream_controller.gd) owns the single source/rest ledger. [RetainedNotationPool](../godot/notation/native/retained_notation_pool.gd) owns compiled CanvasItems. |
| Engraving and drawing | [ScoreEngraving](../godot/notation/native/score_engraving.gd), [ScorePainter](../godot/notation/native/score_painter.gd) and [NativeScoreView](../godot/notation/native/view.gd) own preparation, canvas composition and the canvas/lifecycle boundary. |
| Artwork and derived masks | [GlyphAssets](../godot/notation/native/glyph_assets.gd) owns authentic artwork; [GlyphHeadMasks](../godot/notation/native/glyph_head_masks.gd) owns derived head masks; [Glyphs](../godot/notation/native/glyphs.gd) composes them on the canvas. |
| Controls and feedback | [PracticeChrome](../godot/practice_chrome.gd) builds widgets; [PracticeScreen](../godot/practice_screen.gd) presents state and emits intents; [PracticeFeedbackSession](../godot/practice_feedback_session.gd) consumes acknowledged note events. |

Navigation, settings, device selection, input shortcuts and audio each have
dedicated sessions. They use explicit facts and semantic ports; helpers do not
receive an Engine/Main reference or access another owner's mutable internals.

## One selected lesson decision

A generator consumes immutable source/progress/evidence facts and chooses the
next exact exposure. Its decision includes source, hand, scope, BPM, reset
counters and mastery. Announcement, settlement, preparation and save retry
consume that same selection. Display text is never parsed into a decision.

Practice Flow commits Free → Tempo at 50% of target in both its new progress
and next exposure. Listen and Free use target BPM. The display flow and engine
do not select another BPM downstream. Each trailing window has independent
progress, and the full original examination is separate. The complete rules
live only in [Practice flow](practice-flow.md).

The [course state](../piano_teacher/teaching_course.py) exposes the active
policy's required clean-run count, using Practice Flow's existing two-take
constant or the other courses' configured rule. Lesson snapshots, validation
and captured evidence consume that fact. New rule snapshots retain
`clean_runs_required`; statistics use the captured value, falling back to the
recorded lesson settings for older evidence rather than reinterpreting history
with today's course defaults.

The registered `LessonGenerator` interface receives a canonical `Piece` and
returns a `LessonPlanDefinition` with source-safe stages and an unchanged
whole-piece finale. Variants retain source-note IDs and explicit timing/tempo
policies. Composition uses contributor `passage_stages` and `with_feedback`
ports, rather than decoding generator names. Unknown registrations fail
explicitly. Genuinely different source/timing/tempo performances have separate
stage identities; renamed or duplicate performances do not create new credit.

Simplified stages may not silently replace original music. Exact authored
attacks and complete releases survive source selection, including notes held
beyond the selected last barline. A silent bar creates no fictitious attack.
Changed source/stage/hand/rules cannot inherit incompatible mastery.

The `flow_returns` progress table persists floor-failure returns for the exact
window/stage key and hand. The second return can select a real announced aid;
aid completion returns to the original full-window Free exposure. Aid success
cannot award original-note mastery or advance its target-tempo streak.

## Performance source and display envelope

`authored_duration_beats` is the selected measure-grid duration;
`sounding_duration_beats` also covers complete releases beyond its barline.
The first attack chooses the playable opening after leading silence without
retiming original source attacks or changing their IDs. Grading, Listen and
the take's end use the selected source and complete sounding tail.

[DisplayEnvelope](../piano_teacher/notation/display_envelope.py) extends authentic
ink around that selection. `active_note_ids` identify only the performance hand's
required attacks; `display_notes` and `display_measures` may also contain the
other hand, neighbouring bars and sustained carry-ins. Their signed
`display_extent` can begin before active beat zero. The active authored grid and
performance IDs remain unchanged: context is never hidden graded work.

One compiled native renderer draws active and dimmed ink from that envelope;
there is no second context renderer. Announced transformed exercises display
their own source-safe notes rather than silently acquiring original notes as
context. A direct repeat may trim decorative neighbours to preserve its one-bar
deadline, while retaining the required active notes and full sounding releases.

## Practice state and timing

Source beats are quarter-note positions on the authored measure grid. Source
tempo maps convert them to musical seconds. Deadlines are absolute monotonic
seconds. World beats are forward visual positions, projected at frame rate;
they cannot change a MIDI grade or move already exposed notation backwards.

For constant tempo, `seconds = beats × 60 / BPM`; shaped tempo uses the exact
selected map. Scheduler decisions combine independent lower bounds: authentic
count-in, measured glyph/header clearance, predecessor ink, readiness, latency
and any existing reservation. Rest and count-in may overlap and are not counted
twice. Geometry constrains admission; it does not choose a lesson or tempo.

### Authorized graphical playback

Every timed Listen, Practice, Perform, preview, repeat, retry, stage handoff and
resume uses one transaction:

1. Python publishes an immutable `playback_intent`: intent/take/generation,
   source revision, exact exposure, starting BPM, count-in meter and earliest
   musical deadline. Grading and sound have not started.
2. Godot requires compiled authentic assets for that revision and preflights
   the source against the viewport and all live predecessor layers.
3. Godot physically reserves immutable strips and sends `playback.reserve`
   with the same identity, world origin, queue generation and exact deadline.
4. Godot binds the returned segment and calls `playback.present`. Python
   validates the remaining count-in and authorizes that exact deadline.
5. Notation, MIDI input, metronome, voice and Listen sound consume the same
   authorized take/segment. A preloaded renderer is promoted after authorization.

The musical worker advances deadlines independently of snapshot polling.
Untimed Free has a separate guided segment on the same renderer and holds its
target at the playhead; it has no timed grading deadline. The explicit
Python/headless adapter is not rendered-notation evidence and is never selected
as desktop admission. Its `score_queue_next` projection is not a graphical
playback route.

For an automatic same-source Practice Flow repeat, `fixed_deadline_ms` is the
outgoing sounding end plus **one upcoming authored bar at the next attempt's
BPM**. The already selected count-in origin remains fixed; admission consumes
the lead that remains instead of restarting a full bar. The gateway reserves
that exact world/deadline pair and rejects collision with irreversible active
ink. It cannot add fresh snapshot latency or an offscreen runway to move the
deadline. This exact-repeat route may trim only display context; generic fresh
source reservations still require a complete authored count-in bar.

### Pause and failure

An ordinary timed take receives a complete authored count-in bar. Pausing in
count-in may reuse its remaining part only if the exact admitted opening is
still safely ahead; otherwise another full bar is required. Pausing a played
take preserves its recorder and frozen musical elapsed time. Key releases
during pause/lead remain paired and do not count the paused interval as a hold.
The resumed partial take cannot grade until its admitted opening arrives.

An initial first attack may use the canonical onset allowance before its
deadline. MidiIngress alone admits that input; Recorder preserves its signed
musical timestamp. Resume reading lead still suppresses new grading. A second
Pause during that lead keeps the existing frozen source position.

Stale, expired or infeasible receipts never start grading or audio. A worker
timeout can lose a reply after commit: query `playback.status` before retrying
or withdrawing. Presentation is idempotent by segment identity. Missing bound
ink raises `TAKE_WITHOUT_SCORE` through `playback.failure` and stops the take.
Stop, navigation and source-generation changes invalidate pending work.

Settlement retains the original performed BPM, assessment, selected successor
and source identity. Evidence, progress and generator feedback commit together
under the existing lock/savepoint. A failure restores in-memory state; retry
reuses the same sealed evidence and receipt without regrading or awarding twice.
Incomplete capture is interrupted/censored, never manufactured into mastery.

## Immutable score stream

Retained command-buffer generations identify both geometry changes and
admission-time source crops. ScoreAssetSession publishes the completed
generation together with its readiness status; a ready getter cannot outrun
the corresponding overlay update.

Each logical take is a sequence of adjoining source strips at authored measure
boundaries, with one take identity. Printed cut points are source beats;
header/terminal margins use staff-space units. Once admitted, source range,
world origin and geometry are immutable. Retained layers share those facts;
they are not another source ledger.

There are two removal directions:

- Retire completely departed strips from the front, oldest first.
- Withdraw only the maximal safe, never-exposed suffix from the back. A visible
  strip is irreversible even if later strips belong to the same take.

Replacement is preflighted before mutation. A failed reservation compensates
its own provisional suffix without repainting earlier ink. Resume may reuse
the exact interval if safe; otherwise it retains the first paused source strip
and appends behind that irreversible prefix. Later unseen measures remain
eligible for withdrawal. The new copy explicitly binds its paused predecessor
to the same transport without changing either copy's geometry or identity.
Every incoming renderer checks all still-live outgoing
layers. Different densities cannot overlap printed music.

When Retry needs a complete leading preparation rest, that prefix is admitted
in the same immutable batch and take owner as its source. Stable
before/source/after slot identities distinguish the leading rest, music and
following rest through FIFO retirement, archive reuse and rollback. A
provisional prefix stays hidden until authorization; it cannot become a
separately inserted rest or move the exact automatic-repeat deadline.

The offline FIFO contains available reusable source plans. Its separate
append-only JSONL journal records checksummed enqueue, withdrawal, completion
and reset events under `user://score-stream-journal`, keyed by musical content.
The event is flushed before destructive removal. A failed append blocks that
operation and preserves live bindings and CanvasItems. Reuse materializes a
matching archived plan in a new future owner; it never restores obsolete world
coordinates or consumes an archive entry after a failed enqueue.

## Authentic notation and feedback

Every authentic atlas is extracted from the same complete parsed notation
document. Active performance and bounded display projections cannot remove
context or carry-in chord/tuplet inventory before asset extraction.

Verovio supplies authentic glyphs and composite note/chord artwork. Native
layout maps source identities to retained ink; there is no page-image fallback
or alternate score painter. When internal source notation carries expression,
the compiler preserves the original XML and projects surviving articulations,
ornaments, technical marks and lyrics onto the first generated source attack.
Staff-specific directions keep their hand and offsets without advancing the
timing cursor. Slurs require surviving endpoints in the same hand; ambiguous
unstaffed directions and missing endpoints are not invented. Ties/tuplets are
respelled from the variant's actual durations rather than blindly copied.
Unsupported expression cannot be claimed as natively drawn merely because
internal XML preserved it. Tied continuations do not invent new attacks or
repeat fingering.

Note feedback has one acknowledged channel, `feedback.events`, carrying
sequence, fingerprint, revision, transport, mode and graded facts. The backend
retains unacknowledged events; Godot processes each event before acknowledging.
Gaps/overflow are errors. New-revision events may wait for their exact renderer;
an unrelated current snapshot cannot relabel them. Preview and Listen never
award grades or mastery.

Provisional attack/release observations may appear before authoritative
assessment. `Recorder` alone pairs physical presses/releases, including
overlapping same-pitch keys. `LiveInputView` retains held/recent keyboard facts;
it has no matcher, used-note set or release ledger. Live and final scoring use
the same canonical assignment and shared observations. Live observation
construction is bounded to a two-bar display scope while matching retains full
canonical assignment; strict source projection is O(N + M), with direct source
head lookup rather than per-mark phrase/glyph scans. Elapsed live grading uses
the frozen musical clock during Pause and the resumed reading lead.

Every current canonical assessment snapshot replaces the provisional dimensions
for its source head. `final: true` locks the completed result. A revised local
assignment emits a `pending` withdrawal for its old provisional head; bounded
scope changes preserve older exposed ink rather than erase it. The
ledger preserves independent pitch/onset/release dimensions even when the
product shows only green/red. Records belong to physical take + engraved-note
instances; tied heads inherit the original attack's result. Status masks use
the same authentic head artwork inside its retained strip clip, repainting on
ledger changes rather than on every scrolling frame. Wrong-note ghosts and
Listen lighting are presentation facts, not extra graded source notes. Future
tied heads inherit the attack colour only when the canonical source beat reaches
their continuation. Free feedback uses the same canonical physical take key;
it cannot colour an unrelated future copy of the passage.

The backend carries the persisted `grade_note_holds` choice through the
fixed and tempo-mapped assessment policies into live grading and final settlement.
Feedback events use `release_advisory` as its inverse. With the default off,
correct pitch and onset earn green ink and clean passes regardless of the
physical key release; measurements are still retained. With the setting on,
short, long or unreleased keys are errors and prevent clean Practice Flow passes.
Captured rule identity includes the preference, and switching it cancels the
active attempt rather than reinterpreting existing evidence. Signed wrong-key ghosts use their real musical beat and
the same physical strip/header clip; they cannot enlarge exposed score bounds.

## Native protocol and workers

[PianoNative](../native/) exposes typed operation + JSON requests and raw PCM
audio through an in-memory queue. Internal statuses are success/invalid/unknown/
failed; no URL, socket or network adapter is involved.
[EngineCommands](../piano_teacher/inprocess.py) dispatches the operations.

One native command/tick worker owns command execution and bounded monotonic
wakeups. A separate asset/read-only worker handles cold engraving and statistics
so they cannot block musical ticks. `ScoreArtifacts` serializes engraving then
model publication outside the engine lock. The Python GIL is held while invoking
Python; native condition variables wait without spinning. Godot receives
callbacks on its main thread. Statistics capture bounded read-only WAL snapshots
and never acquire the musical lock or write another history.

Detached snapshots carry explicit facts/read ports; they cannot mutate the live
plan, recorder, renderer or clock. Source/fingering installation similarly uses
an immutable generation/fingerprint/original-notes identity and a validated
install effect; a late correction cannot replace another source.

## Planned PracticeEngine decomposition — 2026-11-21

The active [S0–S7 plan](../ROADMAP.md#active-plan--practiceengine-architecture-replacement-2026-11-21)
supersedes treating the oversized `server.py` facade as mere deferred
file cleanup. At the `f8bd9cd` baseline it contains 2,783 lines, 168
methods and 151,578 bytes. This section describes an **intended**
architecture, not an implementation already present in `main`.

**New architectural layers and boundaries are allowed and may replace
existing ones.** The only architectural constraints are those needed for
correct product behaviour and clear dependency ownership: one actual
lesson/tempo selection, source identity, musical grading clock, admitted
playback authority, canonical notation stream and durable assessment result.
These constraints do not prohibit a new application-service layer, explicit
workflow engines, interface/port layers, an effect-dispatch boundary,
transaction coordinator or immutable snapshot types. Determine their value
from the responsibility inventory and dependency direction, not from the
current class inventory.

The target dependency direction is:

```text
Godot / EngineCommands / native workers
                |
       PracticeEngine entry boundary
                |
        application use cases
    / source  lesson  playback  outcome  read /
                |
    domain state, decisions and policies
                |
       explicit ports / infrastructure
```

The illustration is provisional. Phase S0 must confirm all method and state
ownership and decide the concrete type/module graph. A command coordinator
may orchestrate multiple owners under a documented transaction; it may not
acquire its own competing score queue, MIDI grader, transport clock or
lesson-decision policy. Pure domain modules must not import the facade;
services must not hold a universal mutable `PracticeEngine` reference.
New interfaces should correspond to real dependency seams, not merely
increase layer count.

Initial production migration moves source identity/revision into
`application/source_identity.py`, selected opening/course flag into
`application/lesson_cursor.py`, learner-facing messages into
`application/session_notices.py`, and active remedial assignment into
`AttemptRuntime`. The selected plan lives with its source identity,
the visual transport owns scheduling/rest metadata, and SessionCommands
owns its command reason. The full workflow and transaction decomposition is
still open; these new owners do not establish phase completion.

Native future-stage preload selection and exact-revision acknowledgment
now live in `application/score_preload_workflow.py`. A feedback release
uses only the preloaded source selected by TeachingContinuation, and a
failing next asset stays source-bound.

Source-bound live note observations and acknowledgement identity now use
`application/live_feedback_workflows.py`. It invokes the sole configured
assessment policy and the existing live publisher; it contains no
second used-note matcher or independent musical clock.

Score-state snapshots and exact graphical or explicit headless fixture
projection now use `application/session_read_models.py`. It owns only
the read side; command/worker transitions cannot be induced by polling.

Score selection, current artifact geometry, cached completed-take layouts,
guided marks and overview now use `application/score_read_services.py`,
which resolves the promoted artifact owner through the registry. Cold
native engraving continues outside the application lock.

History-management transactions now reside in
`application/history_management.py`: scoped evidence reset, learner deletion,
lesson reset, history reads and export. It consumes the installed
source/plan identity and `SessionLifecycle` rather than holding a
`PracticeEngine` reference. The external public methods remain locked
entry points. Source installation and fingering correction now live in
`application/source_workflows.py`. Preparation is outside the short
application lock, installation is inside it, and course-entry effects
remain in the facade transaction until S3. Settings and current-policy selection now live in
`application/settings_workflows.py` and
`application/policy_registry.py`. A saved preference change updates the
one current grading/diagnosis instance, while source/transport and read
consumers resolve that same instance; no stale policy reference is
captured at service construction. Device connection lifecycle and calibration now live in
`application/device_workflows.py`, which emits explicit setting changes
rather than calling the engine or mutating configured policies itself.
The short facade entry preserves source interruption ordering and locking.

Native MIDI callback handling, corrected source/transport facts,
device hot-plug and keyboard shortcut dispatch now reside in
`application/midi_application_input.py`. The existing MidiIngress
continues to own physical observation admission and Recorder remains
the one note pairing authority.

Public native/user commands, course-stage controls, state acknowledgement
and committed playback receipts now use `application/practice_controls.py`.
The facade retains the public `control` operation; the command router
uses source-bound services and keeps the existing application lock.
It does not acquire an independent take-admission policy.

Authorized timed take execution, continuation, Pause/Resume and Listen
readiness now use `application/timed_playback.py`. Its return from
Resume carries deferred score readiness to the command boundary, so
the playback service never re-enters the entire engine.

Source-bound count-in, musical-rate projection, rest geometry,
forward visual motion and playback admission facts now live in
`application/transport_timing.py`, which holds no extra clock
epoch and makes no curriculum decision.

The selected musical worker's tick, evidence finalization, take completion
and non-grading course handoffs now execute through
`application/practice_timeline.py`. It calls the existing playback,
graded assessment and source owners rather than implementing a competing
clock, selection or scorer. Bounded re-entry remains to be audited.

Exact post-settlement feedback and typed continuation dispatch now
belong to `application/completion_continuations.py`. The selected
next source and admission deadline come from existing authoritative
course and playback owners, not a second continuation policy.

Recovery materialization, recorded boundary checks and automatic
remedial effects now use `application/recovery_workflows.py`, which
executes the existing configured assessment/recovery decisions and
uses the canonical source clock.

Committed full-passage assessment effects and bounded review return
operations now reside in `application/post_assessment_effects.py`.
It consumes the one sealed `AttemptSettlement` receipt, updates the
selected source/score registry, and never regrades a take or independently
chooses its successor.

The decision-building part of lesson orchestration now lives in
`application/teaching_workflows.py`. It gathers bound evidence and route
facts and applies exactly the generator's validated decision. It does not
create another stage-selection policy or hold an engine backreference.
Exposure selection and materialization use
`application/exposure_workflows.py`; selected-effect installation uses
`application/exposure_installer.py`. Exact guided evidence facts are
assembled by `application/session_evidence_context.py`, and the installer
does not re-decide the lesson. Course entry, guided completion, navigation and original measure
selection now execute inside `application/lesson_execution.py`.
It uses the registered teaching decision and persisted source state
rather than introducing another curriculum selection policy.

The final shutdown path shares `SessionLifecycle` and retains the
evidence-close, MIDI-select-close and database-close ordering exactly.
No shutdown workflow calls back into the engine.

The active-take stop transaction now resides in
`application/session_lifecycle.py`. The stop workflow owns ordered
authorization invalidation, evidence interruption, cancellation and
per-owner resets, with explicit dependencies rather than a facade
backreference. The remaining command and source workflows are still
coordinated by `PracticeEngine`.

Identified high-risk state: `feedback`, `next_action`, selected source
window, `course_guided`, `score_revision`, scheduled starts, paused
source time, recovery and `_stop` lifecycle sequencing. Their concrete
writers, authoritative owners, derivations and explicit effects are S0/S1
deliverables. Later phases move complete source/history, lesson/exposure,
command/transport, settlement/recovery, read-model and score-presentation
workflows; each phase deletes the old implementation and migrates all callers.

The facade's approximate 300–450-line target is a **diagnostic goal, not
an architectural invariant**. Larger well-separated services or additional
layers are acceptable when coherent, whereas a 300-line facade that simply
forwards into another 2,000-line god object fails the goal. The present
ownership table above is an inventory of the *current* architecture and
can change as the S0–S7 plan is implemented. Existing graphical-admission,
read-only snapshot and musical-tick asset requirements remain binding.

### S0 responsibility inventory — implementation baseline 2026-11-21

Method-level audit on `75965fc6` identifies **180 methods
including public properties** after the initial state migration. The original
baseline contained 168 methods, before the explicit owner observation
properties were introduced. The following is a **complete migration map**,
not proof that the listed methods have already moved; final destinations may
become new classes or layers when the group dependencies are resolved.

| Intended responsibility | Current methods (name and source line) |
| --- | --- |
| S2: source/device/history | `_midi_lost` (383), `_present_midi_notice` (396), `ports` (405), `connect` (419), `hardware_diagnostics` (432), `hardware_diagnostics_action` (436) |
| ↳ | `library_listing` (440), `library_health_status` (444), `start_library_health` (447), `midi_calibration_action` (450), `preferences` (472), `_learning_context` (476) |
| ↳ | `learning_history_status` (489), `learning_statistics` (494), `_retry_context` (498), `export_learning_history` (530), `delete_piece_history` (536), `delete_learner_history` (559) |
| ↳ | `close` (586), `set_preferences` (596), `_active_tempo_map` (641), `_elapsed_beat` (652), `_elapsed_seconds` (657), `exercise_diagnostics` (661) |
| ↳ | `load_library` (672), `performance_diagnostics` (691), `load` (746), `fingering_status` (783), `correct_fingering` (788), `_restore` (814) |
| ↳ | `_save` (817), `_reset_current_path` (820), `_poll_midi_connection` (1938) |
| S3: lesson/exposure | `_learner_saved` (864), `_guided_unit` (868), `_save_guided_preparation` (872), `_learner_snapshot` (902), `_enter_selected_exposure` (907), `_flow_active` (920) |
| ↳ | `flow` (924), `_flow_stage_entry` (927), `_flow_execute` (930), `_flow_open` (944), `_flow_say` (953), `_flow_state` (956) |
| ↳ | `_begin_course_stage` (959), `_skip_stage` (966), `_place_original` (976), `_valid_trouble_spots` (990), `_revisit_trouble` (994), `_reset_trouble` (1009) |
| ↳ | `display_phrase` (1012), `_begin_learn` (1019), `_exposure_source` (1035), `_apply_exposure_preparation` (1042), `_prepare_practice` (1100), `_apply_listen_failure` (1117) |
| ↳ | `_prepare_listen` (1124), `demo_audio` (1132), `_start_listen_if_ready` (1136), `_prepare_perform` (1146), `_review_retry` (1164), `_practice_weak` (1176) |
| ↳ | `_seek_grid` (1186), `_seek` (1195), `_teaching_binding` (1214), `_prepare_teaching` (1220), `_manual_effect` (1265), `_install_command` (1269) |
| ↳ | `_control_listening` (1583), `_control_learning` (1601), `_change_stage` (1899), `_open_take` (2448) |
| S4: command/playback | `require_presentation` (321), `playback_status` (325), `reserve_playback` (329), `present_playback` (333), `withdraw_playback` (339), `report_playback_failure` (343) |
| ↳ | `_playback_facts` (348), `_request_playback` (370), `_abort_playback` (374), `_on_playback_failure` (377), `_receive` (694), `_midi_transport_facts` (702) |
| ↳ | `_apply_midi_shortcut` (718), `_receive_message` (726), `_stop` (858), `_presentation_bpm` (1279), `start` (1325), `_commit_playback_intent` (1378) |
| ↳ | `_next_count_in` (1406), `_next_count_in_beats` (1418), `_next_count_in_meter` (1421), `_continue_at` (1424), `_collect_continuation_measurement` (1449), `_start_rate_bpm` (1464) |
| ↳ | `_schedule_preparation` (1471), `_visual_motion` (1481), `control` (1490), `_dispatch_control` (1519), `_control_acknowledgement` (1550), `_update_short_rest` (1642) |
| ↳ | `_collect_rest_measurement` (1660), `_update_continuous_horizon` (1688), `_presentation_lead` (1696), `_control_transport` (1709), `_open_selected_measure` (1780), `_start_or_restart` (1795) |
| ↳ | `_musical_seconds` (1851), `_pause_current_session` (1863), `_resume_current_session` (1871), `_update` (2340), `_update_transition` (2361), `advance_clock` (2501) |
| S5: outcome | `_apply_policy_response` (504), `_performance_review` (1154), `_commit_pending` (1285), `_decided_stage_selection` (1948), `_advance_pending_feedback` (1954), `_publish_feedback_fault` (1986) |
| ↳ | `_dispatch_continuation_effect` (1990), `_start_remedial_assignment` (2012), `_apply_rolling_recovery` (2042), `_complete_attempt` (2106), `_finish_performance_review` (2188), `_finish_section_review` (2194) |
| ↳ | `_finish_partial_recovery` (2206), `_finish_full_passage` (2219), `_assess_rolling_boundary` (2255), `_run_pre_assessment_transition` (2282) |
| S6: projection/read | `_guided_marks` (1091), `_phase` (2417), `_layout_for_completed_take` (2436), `_feedback_take` (2452), `_publish_live_assessment` (2461), `_live_marks_for_snapshot` (2481) |
| ↳ | `_live_feedback` (2485), `_score_projection_facts` (2548), `_prepare_score_presentation` (2579), `_state_snapshot` (2588), `_capture_session_snapshot` (2647), `_next_stage_selection` (2720) |
| ↳ | `next_stage_score` (2728), `report_preload_failure` (2733), `acknowledge_preloaded_stage` (2740), `_score_selection` (2756), `_source_model` (2768), `_selected_artifacts` (2772) |
| ↳ | `semantic_score` (2783), `engraving` (2787), `geometry` (2791), `lesson_overview` (2796) |
| S7: facade/public projection | `plan` (117), `source` (121), `is_builtin_warmup` (125), `fingerprint` (129), `score_revision` (133), `open_from_beat` (137) |
| ↳ | `course_guided` (141), `feedback` (145), `feedback` (149), `next_action` (153), `next_action` (157), `_remediation_active` (161) |
| ↳ | `teaching` (166), `persistent_hints` (170), `running` (175), `mode` (179), `auto` (183), `preview_only` (187) |
| ↳ | `transport_id` (191), `count_in_beats` (195), `count_in_bar_beats` (199), `count_in_meter` (203), `awaiting_score_revision` (207), `pause_context` (211) |
| ↳ | `__init__` (214), `state` (2530), `poll_state` (2541) |

The proposed domain/state dependency ownership is:

| Fact or operation | Single authoritative owner / planned boundary |
| --- | --- |
| Loaded source, `LearningPlan`, source fingerprint and published revision | `SourceIdentity` (now), prepared/install effects in S2 |
| Selected opening and course-guided designation | `LessonCursor` (now); S3 manages semantic transitions |
| Learner-facing feedback and suggested action | `SessionNotices` (now); policy produces facts, presentation consumes them |
| Active remedial assignment, recording, review and recovery flags | `AttemptRuntime` and teaching decisions |
| Current audio/MIDI transport lifetime, count-in and mode | `PlaybackSession`; physical admission in `PlaybackCoordinator` |
| Forward view epoch, continuation rest and rendering runway | `VisualTransport`; native score admission owns physical ink |
| Command reason, selected manual effects and application provenance | `SessionCommands` |
| Assessment and lasting result | `AssessmentService`, `AttemptSettlement`, `LearningCapture` |
| Asynchronous source and asset work | `SourcePreparationSession`, `ScoreArtifacts`, native asset worker |
| Graded command/tick transaction | New/updated S4 application executor; not snapshot reads |
| Cross-workflow completion/return effects | New/updated S5 effect/settlement orchestrator; no shadow selector |
| Read models and score projections | S6 projection boundary using immutable `SnapshotValues` and named read ports |

**Cycle and ordering evidence.** The major method-call strongly connected
groups in the current facade are: `control` /
`_dispatch_control` / `_control_transport` /
`_resume_current_session` (command re-entry);
`_update` / `_update_transition` / `_complete_attempt` /
`_run_pre_assessment_transition` / `_finish_full_passage`
(automatic completion); and `_flow_execute` / `_begin_learn`
(course re-entry). S3–S5 must explicitly resolve those cycles by accepted
commands and ordered effects rather than moving them into mutually
referencing coordinator classes. The planned dependency graph in the
preceding section is the design baseline; the concrete port contracts and
transaction implementations are S1–S5 deliverables.

**Migration rule:** All 180 inventoried names must be
accounted for after S7 as moved code, intentional public wrappers, or
demonstrably unused/deleted methods. Public in-process operations must
retain their contract. User-state migrations and the headless fixture adapter
remain only where needed for supported behaviour.

## Remaining work — source audit 2026-11-20

Historical discovery findings and original source evidence follow. A1–A6 now
have production-code corrections; the table is not a list of unimplemented work.

Implementation ledger (main, starting at `82bf06bb`):

- A1 implemented: admission compares the prepared model with both canonical
  `practice_timeline` bounds, then compares the intent with its sounding bound.
  No second duration field, truncated release or changed authored API.
  Existing desktop/timeline Python checks and all native checks pass
  (`architecture-a1-ci.log`); a direct Godot gateway diagnostic accepts the
  4-authored/6-sounding range and rejects mismatched prepared assets.
  Physical rendering remains unverified. Commit: `96c895e7`.
- A2 implemented: pool reseeding is allowed only before stream binding;
  growth initializes new capacity without rewriting admitted crops. Once ink
  is committed, engraving preserves its gap and safe horizontal boundaries
  through resize while rebuilding vertical placement. Existing native checks
  and 14 desktop/timeline tests pass (`architecture-a2-ci.log`); the actual
  controller/Resume/pool diagnostic preserves each bound source crop during
  pool growth. Physical resize appearance remains unverified.
- A2 commit: `0d959470`.
- A3 implemented: exposure/review/retry, settlement publication, guided return,
  recording suspension and preparation transitions use their existing owners.
  Manual command scopes use SessionCommands' context manager; obsolete Engine
  teaching/hint setters and redundant stop resets are removed. Calibration
  reset and assistance capture also mutate inside their owners. All existing
  Python behaviour checks pass: 107 passed, one optional system-SF2 skip
  (`architecture-a3-ci.log`).
- A3 commit: `e7b10962`.
- A4 implemented: snapshots sample one instant without executing transitions.
  Teaching and calibration reads are passive; their worker/command operations
  advance them. Guided presentation scheduling also moved out of serialization
  into the accepted command/tick boundary. Three existing behaviour cases now
  explicitly tick the worker instead of relying on obsolete poll advancement.
  Full CI script passes: 107 Python tests, one optional system-SF2 skip,
  parser and four native groups (`architecture-a4-ci-final.log`).
- A4 commit: `1507b427`.
- A5 implemented: immutable lesson contracts and the shared source-attack
  index sit below curriculum policies. Composers receive explicit contributors;
  Practice Flow uses their feedback contracts without importing the registry.
  Statistics share pure evidence/numerical operations, and tuplet recovery
  receives the authentic extractor as an explicit operation. No algorithms
  or supported strategies were removed. All 107 Python checks pass (one
  optional system-SF2 skip; `architecture-a5-ci.log`). The one-off runtime
  import scan, including deferred imports and excluding TYPE_CHECKING-only
  edges, reports zero cycles (`architecture-a5-imports.log`). This diagnostic
  is not a new architecture CI test.
- A5 commit: `f8daff77`.
- A6 implemented: admission/preloading query InProcessRequest's pending
  operation semantics. The private numeric ID stays inside its request owner.
  Repository-wide caller inspection removed unused native withdrawal/restore,
  receipt, append, direct-arm and empty-strip facades, their dead helpers,
  unused continuation prediction and the unused flow-rate compatibility port.
  Production admission still uses the existing two-phase executor. Full CI
  passes: 107 Python checks, one optional system-SF2 skip; parser and four
  native groups pass; coverage is 69.6% lines / 49.4% branches
  (`architecture-final-ci.log`). The first full run on `982d3fee` exposed acceptance scripts that still read
  the removed renderer `stream_passes` property. Commit `ad1055ac` uses
  a deep diagnostic snapshot from the canonical stream owner instead.
  Remote core and full native-production CI then passed on `ad1055ac`,
  run 44796955201, including real-score journeys and relocated package
  boot. Physical output acceptance remains unverified.

### Ownership and dependency follow-up — 2026-11-20

The follow-up review inspected engine snapshot construction, PlaybackSession,
VisualTransport, AttemptRuntime, AttemptSettlement, Godot admission, the retained
notation pool and its single queue. The engine delegates take and transport
lifecycle mutations, and snapshot reads do not execute the worker transition
loop. The native diagnostic returns a deep copy of the sole stream ledger and
does not restore mutable queue access.

A further dependency cleanup makes shared lesson focus, hand selection and
hybrid passage segmentation explicit public module ports. It moves bounded
authentic vector rasterization from tuplet extraction to
`notation/assets/vector_art.py`, consumed independently by beam and tuplet
extractors. Runtime/font resource initialization is similarly exposed through
public functions, instead of other extractors importing private helpers.
These changes preserve the existing algorithms; no new architecture, pixel
or infrastructure tests were introduced.

The review covers the critical production owners and the known dependency
clusters. It cannot prove absence of every possible defect. The refactored
source requires a new full CI run and physical acceptance remains separate.

### Musical-tick asset boundary — 2026-11-21

Completed-take feedback consumes the selected `ScoreArtifacts.cached_layout`
without cold engraving. If that layout is missing, the existing
`assess_completed_take` error boundary retains its canonical grading result,
reports the absent visual projection and skips unmapped ink. No Verovio
compilation may run from the locked transport tick. Pre-engraving and publication
remain owned by `ScoreArtifacts` and the asset worker.

### Legacy-dependency review — 2026-11-20

The production paths were checked against the current ownership table above.
The runtime has one in-process Godot–Python command transport, one backend
playback authorization owner, one native score/immutable FIFO and one musical
grading clock. The forward-scrolling visual timeline projects those authorized
epochs but cannot grade or admit MIDI.

Source-level findings and changes:

1. The old `score_queue_next` plan remains an explicit headless fixture
   projection in Python, now isolated in
   `application/headless_score_projection.py` (2026-11-21). The product
   `ScoreStatePublisher` publishes only admitted desktop intents and guided
   plans. `PracticeEngine` calls the headless adapter only when presentation
   is disabled. Godot diagnostics use the actual backend segment identity;
   no graphical score stream reads the compatibility projection.
2. Assessment ink rejects layouts without `source-note-v1` bindings.
   The former pitch/onset-nearest fallback has been removed; only the
   canonical note-to-head mapping can colour music.
3. Fixed-BPM and tempo-mapped recovery now have one reducer over already
   assessed wrong/missed notes. Their time conversions remain separate and
   use the same source grid; no additional scorer, progression state, or
   second recovery clock was introduced. Warm-ups retain their own bounded
   source window as before.
4. The obsolete, invisible coaching card and its standalone GDScript were
   removed. The current native ink/feedback and gameplay rail remain.
5. The old `score_loop_enabled` state field carried no actual loop authority:
   the base renderer used it only to gate practice-timeline validation and
   an otherwise redundant redraw. The validation now derives from accepted
   `mode == "practice"` and `kind != "perform"`; the Python/Godot
   state contract advances together to v4.
6. Unsupported authored expression classes continue to be recorded under
   `unrendered_expressions`. No complete-page or alternate renderer is
   available or selected. Native source fidelity is not silently claimed
   where an authentic glyph cannot be drawn.

The retained migrations in the library, progress repository and learning
ledger safeguard pre-upgrade saved data; they do not govern new lesson
decisions. The explicit headless adapter is restricted to no-presentation
testing. The development MCP toolkit is not enabled by the project and is
excluded from standalone package assembly.

This source audit, including the production Python/GDScript keyword and
caller inspection, is evidence about known paths, not a formal proof against
all dynamic interactions. The main `PracticeEngine` facade is still 2,783
lines and declares 168 methods; it is the largest remaining maintainability
risk. CI and instrument-level acceptance are reported independently in the
roadmap. No new tests or parallel services were added.

Audited implementation: `640a77f5`. Read-only implementation review, a Python
import-graph inspection and an existing real-MIDI/public-command diagnostic
found the following remaining work. No production code or tests were changed
by this audit. Priority reflects demonstrated software consequences versus
structural debt; physical rendering and instrument acceptance remain separate.

| ID / priority | Remaining work and evidence | Required ownership outcome |
| --- | --- | --- |
| A1 / high | **Unify authored and sounding range contracts at admission.** [Python playback facts](../piano_teacher/server.py#L329) use the complete sounding endpoint; [lesson snapshots](../piano_teacher/application/lesson_snapshot.py#L29) publish authored duration. The [Godot admission guard](../godot/score_admission_gateway.gd#L111) incorrectly requires equality. An existing one-bar MIDI fixture with a held ending publishes 4 and 6 respectively, so that guard refuses admission. Accepted state reaches the gateway unchanged. | Carry both meanings explicitly from the selected source and validate prepared coverage against the correct endpoint. Keep the full release and the authored four-bar window limit. Never fix the disagreement by truncating the music. |
| A2 / high | **Preserve admitted source crops on resize.** [View resize](../godot/notation/native/view.gd#L213) calls [pool resize](../godot/notation/native/retained_notation_pool.gd#L65), which rewrites source windows by pool-array position. [Admission](../godot/notation/native/stream_lifecycle.gd#L122) assigns those same nodes the ledger's context/Resume-specific clips. Resizing can therefore recompile a different source interval under an unchanged admitted ledger record. This is a source-level mutation path, not a claimed visual reproduction. | Stream binding remains authoritative for each allocated node's crop. Pool growth/reflow must preserve bound windows and exposed geometry, and only prepare unbound capacity. |
| A3 / medium | **Finish lifecycle ownership transfers from the Python facade.** [Exposure installation](../piano_teacher/server.py#L1064) writes transport opening/rewind and attempt review fields directly. [Settlement publication](../piano_teacher/server.py#L1299) clears PlaybackSession's score wait; [transition execution](../piano_teacher/server.py#L2294) mutates the transport preparation dictionary and visual offset. [PlaybackSession](../piano_teacher/application/playback_session.py#L287) also clears AttemptRuntime fields directly. | Give VisualTransport, PlaybackSession, AttemptRuntime and GuidedSession semantic operations for their own lifecycle mutations. Keep the facade's lock/composition role without creating another state holder or moving the same field bag elsewhere. |
| A4 / medium | **Remove transition execution from snapshot reads.** [State serialization](../piano_teacher/server.py#L2545) calls the same mutating update as [the clock worker](../piano_teacher/server.py#L2507). This is one serialized clock, but two entry paths for grading, settlement, device polling and continuation side effects; the source explicitly retains a compatibility poll route. | The existing worker/command execution boundary advances transitions. Snapshot construction reads a frozen accepted state and cannot settle a take or start its successor. |
| A5 / medium | **Break deferred dependency cycles and private helper coupling.** [Statistics](../piano_teacher/learning_statistics.py#L285) imports its [metrics module](../piano_teacher/learning_statistics_metrics.py#L8), which imports private helpers back. [Tuplet extraction](../piano_teacher/notation/assets/tuplets.py#L460) calls [recovery](../piano_teacher/notation/assets/tuplet_recovery.py#L109), which imports the extractor back. Course/generator modules also form a deferred cycle; [PracticeWindow](../piano_teacher/practice_windows.py#L16) imports the alternate curriculum's private source index. Type-checking-only edges were excluded from these findings. There is no immediate top-level import failure. | Put shared source indexes/contracts below curriculum policies, and give statistics/tuplet recovery one-way dependencies. Preserve existing algorithms and avoid a duplicate matcher, planner or source index. |
| A6 / lower | **Close remaining private request-state access.** [Admission](../godot/score_admission_gateway.gd#L275) and [preloading](../godot/score_runway.gd#L303) repeatedly inspect [InProcessRequest's](../godot/inprocess_request.gd#L8) private pending ID to decide timeout/reconciliation/cancellation behaviour. | The request owner exposes pending/completion/cancellation semantics; callers do not depend on its storage representation. No current learner-visible failure was established for this item. |

Lower-priority cleanup: repository-wide caller inspection found unused native
mutation facades such as [append_source_take](../godot/notation/native/view.gd#L389)
and [arm_stream_take](../godot/notation/native/view.gd#L457). Review these against
the supported API, then remove obsolete internal admission/compensation paths
while keeping the existing executor as the sole production entry.

The earlier extraction is substantive: Main composes application sessions,
PracticeScreen separates chrome from interaction, glyph assets/masks are
separate, and ScoreStreamController delegates binding/recovery and retained
resource lifetime. This audit found no second production score ledger or
independent progression clock in those paths. File size alone does not justify
another extraction. Durable assessment/progress transactions already live in
AttemptSettlement; A3 concerns remaining lifecycle writers and publication.

Diagnostic evidence: `debug-sessions/practice-completion/architecture-range-probe.log`
records actual Python command values for A1. A2–A6 are source-review findings.
The prior passing CI/native/package record remains valid for its exercised
scenarios; it does not close these newly identified gaps. Address A1/A2 first,
then A3/A4, followed by A5/A6 and obsolete-port cleanup. Keep CI focused on
player behaviour rather than adding architecture-shape tests.

### MIDI-only source boundary — verified source review 2026-11-20

User source dispatch and persisted library selection both accept MIDI only.
The old MusicXML importer and direct source-annotation/fingering placement
parsers were deleted; two dangling imports and an obsolete authored-fingering
test were subsequently corrected. Internal generated MusicXML and the
authentic Verovio asset extraction pipeline remain part of the native view.

There is a single imported `Piece`, single immutable attack identity set and
one original MIDI measure grid. The preprocessing cache returns this `Piece`
directly, and `SourcePreparationSession` builds curriculum and fingering from
that same instance. It no longer carries a fictitious score alongside
`Piece` or installs an always-`None` `PracticeEngine.score`. The old alternate
music21-score branch in `render_layout` and its single-page SVG wrapper are
retired: the engraver accepts the native `LessonScore` exclusively. With
both external source import and music21 page conversion removed, the
`music21` package requirement and its verification checks are also retired.

Original MusicXML inventory parsing retained under `research/coda_*`
supports independent comparisons of Coda's symbolic notation ideas. Those
research tools are not the desktop input seam, own no playback or grading
clock, and cannot inject source pages into the active application. Do not
advertise this separate research capability as a user import format.

160 Python application modules were inspected for deleted-module imports
and stale `source_musicxml` uses; no remaining application reference was
found outside the isolated research adapters. The subsequent source-only
dependency and engraver cleanup passed combined core, native source journeys
and a relocated package boot on `23dd5649` (GitHub Actions run
44836313449). Physical MIDI/audio/visual acceptance is still separate.

Architecture review and software execution are distinct from physical acceptance.
See [development](development.md#verification-and-acceptance) and the dated
[roadmap](../ROADMAP.md) for what was actually checked on each revision.
