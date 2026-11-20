# Application architecture

[Practice flow](practice-flow.md) defines learner-visible behaviour.
[ROADMAP](../ROADMAP.md) records product decisions, phases and dated verification.
This document is the current technical overview; [development](development.md)
covers operation and acceptance, and [reference](reference.md) covers fingering,
learning evidence, privacy and research limitations.
The ownership descriptions are the required contracts. The
[current source audit](#remaining-work--source-audit-2026-11-20) records
remaining deviations; the earlier Phase 5 completion claim is superseded.

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

The backend carries the selected `release_advisory` display policy on feedback
events. Normal Practice Flow keeps correctly pitched/on-time notes green for
short, long or unreleased keys while preserving those measurements in the
ledger and durable evidence. Other selected grading policies retain their
release judgments. Signed wrong-key ghosts use their real musical beat and
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

## Remaining work — source audit 2026-11-20

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

Architecture review and software execution are distinct from physical acceptance.
See [development](development.md#verification-and-acceptance) and the dated
[roadmap](../ROADMAP.md) for what was actually checked on each revision.
