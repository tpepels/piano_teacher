# Application architecture

[Practice flow](practice-flow.md) defines learner-visible behaviour.
[ROADMAP](../ROADMAP.md) records product decisions, phases and dated verification.
This document is the current technical overview; [development](development.md)
covers operation and acceptance, and [reference](reference.md) covers fingering,
learning evidence, privacy and research limitations.

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
the exact interval if safe; otherwise it appends behind the irreversible
prefix. It never protects obsolete unseen measures merely because an earlier
strip shared their take. Every incoming renderer checks all still-live outgoing
layers. Different densities cannot overlap printed music.

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

Architecture review and software execution are distinct from physical acceptance.
See [development](development.md#verification-and-acceptance) and the dated
[roadmap](../ROADMAP.md) for what was actually checked on each revision.
