# Production practice transition and ownership ledger

This ledger is a **source-level dependency and transition audit** for the
default practice-flow contract in [practice-flow.md](practice-flow.md).
It documents the actual Python/Godot production path, with separate
acceptance gates. Its date is 2026-11-21; do not treat a source-owner
mapping as hardware verification.

## Non-overlapping responsibilities

| Invariant or decision | Sole production owner | Native reader/adapter | Prohibited alternative |
| --- | --- | --- | --- |
| Selected piece, revision, measure window and hand | `SourceIdentity` / `LessonExecution` and generator-approved `TeachingDecisions` | `PracticeScreen` and `ScoreAssetSession` | Godot selecting a neighboring practice measure |
| Listen → Free → Tempo, next window/hand and Coda/Fukuda eligibility | `practice_flow`, `TeachingDecisions`, `LessonExecution` | `PracticePresentationSession` and `PracticeChrome` | UI phase-string transition choices |
| Accepted screen/MIDI shortcut action and navigation effects | `control_projection`, locked `PracticeControls` | `ApplicationInputSession`, `PracticeCommandCoordinator`, `CommandSuccessPolicy` | Godot turning a stale button label into Start or Retry |
| Graded and audible musical origin, count-in, exact retry/fixed deadline | `PlaybackCoordinator`, `MusicalScheduler`, `TransportActions` | `ScoreAdmissionGateway` and `MetronomeFrameCoordinator` | Native musical scheduling or alternate countdown clock |
| Sampled immutable source/clip, queue positions, notes strictly in future, suffix retraction | `ScoreStreamQueue`, `ScoreStreamController`, `StreamTakeBinding`, `StreamAdmissionExecutor` | `ScoreAdmissionGateway`, `ScoreRunway` | Python mutating pixels or UI holding an alternate stream |
| Presentation world and authored tempo-map projection | `PresentationTimeline` / `ContinuousScoreFlow` | Native score view/frame adapters | Separate presentation clocks for count-in or Free |
| Semantic Free target, Pause, unready idle, and pending successor motion directive | `ScoreStatePublisher` | `GuidedPresentationSession` only maps target beats to world | Native teaching-phase/expected-note progression |
| MIDI on/off grading, marks, hold and timing policy | `MidiIngress`, `AttemptSettlement` and authoritative assessment | GDExtension input port, `PracticeFeedbackSession` and view effects | Local Godot verdicts, mastery or strike counts |
| Durable attempts, review progress and saved reopen | `LearningLedger` and `LearnerProgress` | Library/lesson screens present accepted results | Godot persistence or implied mastery |
| Full immutable state projection and schema | `SessionReadModels`, `state_projection`, `state_contract.VERSION=5` | `ApplicationStateInbox` | Side-effecting reads, unversioned fallback fields |

The native bridge is `PianoNative` → `inprocess_bus.gd` →
`EngineCommands`, not an HTTP endpoint. Every playback admission
operation is executed on the embedded worker under the application lock.

## Ordered transition/acknowledgement matrix

| Event / prerequisite | Authoritative transition | Cross-boundary receipt / observable state | Failure or non-progress |
| --- | --- | --- | --- |
| Library opens a selected MIDI | `library.open` → `SourceIdentity`, `LessonExecution` | source fingerprint, revision, window, complete sounding tail and one Listen exposure | missing/repaired metadata reported; prior source invalidated |
| Real source fully engraved | `score_ready` acknowledgement → `TransportActions.control_acknowledgement` | same revision; selected score/tempo map, `playback_intent` when timed | stale asset revision rejected; no grading before source |
| Listen / start gesture | `PracticeControls` resolves UI intent → `TransportActions` → `PlaybackCoordinator.request` | `intent_id`, attempt, source and earliest deadline | unavailable controls have non-executed outcome; no clock without authorization |
| Native physical admission | `ScoreTransportReservation` previews, `StreamAdmissionExecutor` arms immutable source; `PlaybackCoordinator.reserve` authenticates physical witness | source/queue generations, exact world and one reservation receipt | wrong source, impossible clearance, stale witness, fixed-deadline overlap rejected |
| Audible/graded playback begins | `playback.present` → `PlaybackCoordinator` commits the one transport | authorized segment, transport ID, downbeat, meter, count-in and audio epoch | expired count-in, mismatched segment/renderer or partial failed commit stops/fails |
| Lost reserve ACK | `playback.status` returns original physical witness | native confirms same intent, take, attempt, queue generation and timestamp; only then binds it | conflict retracts provisional ink; prior active take remains |
| Lost present ACK | `playback.status` / authorized state poll identifies active segment and take | native physically attests still-present source, promotes staged renderer once | absent source reports `playback.failure`; never guesses an authorized take |
| Count-in / Pause / Resume | `TransportActions` requests Pause or Resume; `PlaybackCoordinator` authorizes the resumed take | backend `presentation_directive` frozen/retain/run, source-bound metronome, MIDI grading window | pending Resume cannot unfreeze painted ink; pause retains source |
| Listen completes | `PracticeTimeline`, `LessonExecution` apply accepted practice-flow transition | complete window Free target, backend guided plan source identity | score not ready/paused/incorrect MIDI cannot grant credit |
| Free expected note | `GuidedSession` records actual MIDI; `ScoreStatePublisher` publishes next target | guided plan and `presentation_directive=target`, authentic note feedback | wrong, absent or partial chord retains target; no timed grading |
| Free completes → Tempo | `LessonExecution` selects original notes at starting rung | new timed intent at selected window and hand, native physical source ACK | no notes outside selected measure window admitted |
| Tempo take completes | `AttemptSettlement` evaluates all attacks/extras/releases according to configured policy | accepted clean/fail verdict, persisted evidence | missing/wrong/early/late or optional hold failure blocks clean credit |
| Clean below target | `AttemptProgression` chooses next tempo from target-rung ladder | fixed repeat at full outgoing-time rest, incoming tempo only at new downbeat | physically impossible exact repeat retired, not shifted |
| Failed attempt, repeated floor failure | `TeachingDecisions` chooses same/slower Tempo or return to Free | attempts/streak counters, next source and backend message | messages never alter musical deadline; source/window identity preserved |
| Second floor return | `TeachingDecisions` applies source-safe simplification only if eligible | named changed exercise and durable per-window/hand evidence | no eligible aid: original Free remains; no fabricated original mastery |
| Window/hand mastery | `LessonExecution` selects next original window/hand | one measure alone, then trailing windows up to four; completed hand evidence | empty hand skipped; window progression cannot display neighbors |
| Whole-piece final | `practice_flow` chooses full authentic source, both hands | final-stage identity, two clean target passes and durable record | never infers mastery from simplified or ungraded input |
| Reopen progress | `LearningLedger` / `LessonExecution` restore same window at Free | valid source revision and saved staged progress | partial chord/held key cannot become completed learning |
| Source change during admission | `PlaybackCoordinator.invalidate` / `cancel_pending` | old intent/receipt invalid; native verifies latest fingerprint/revision | no old async callback may present or promote new ink |
| Physical source disappears during active take | native watchdog reports take/segment; `PlaybackCoordinator.fail` decides transport stop | recorded source failure and recoverable visible reason | no unscored/audio-only take; four-frame native grace currently used |

## Native physical admission invariants

A provisional score arm cannot grade MIDI. The backend receipt is
source/attempt/queue-bound, and the native controller must prove that
the same arm still exists before `playback.present` can authorize it.
After authorization the queue may only discard expired head ink or
retract an unexposed maximal future suffix. Future source placements
are immutable. Automatic exact repeats can neither move the deadline
nor print a second rest. The complete sounding tail and closing
barline belong to the selected authored window; additional neighboring
bars may inform internal engraving, not the printed exercise.

**Open architectural contract:** the renderer currently proposes its
physical slot and measured travel time, while Python verifies musical
feasibility and binds that exact proposed deadline. The V3 target is
a true backend-owned *proposal → physical commit → authorization*
transaction, with the backend determining the one deadline from the
physical feasibility envelope before ink is armed. Treat current
verification-plus-binding as incomplete V3 ownership.

## Reproduction witnesses and acceptance gaps

| Witness | Actual observation | Corrective owner / status |
| --- | --- | --- |
| Missing Pause/Free visual hold, pending Resume deadlock | State changed but painting release/forecast was confused | backend directive, independent held-paint and hypothetical-geometry projection; core checks exist, native acceptance pending |
| Wrong/silent Free moved apparent target | Initial authorized Free ink had not finished reaching the playhead when wrong-note check began | production synthetic-MIDI journey now waits for actually stable printed Free target before injecting wrong MIDI, then measures wrong/silent hold; native outcome pending |
| Extra bars visible | Native pre-engraved neighboring context could leak beyond selected window | renderer clips only the current authenticated window; full-scene physical queue bound assertion added |
| Reservation reply dropped | Godot previously withdrew a physically armed source without checking Python ledger | read-only backend `playback.status.reservation` witness and exact native recovery |
| Original 40→48 BPM retry | Incoming tempo incorrectly shortened the *outgoing* printed rest; native queue reported overlap | `AttemptProgression` now clocks full authored rest at outgoing tempo; full native retest pending |
| Old direct command reply | Native-bridge smoke assumed flat response after `practice.command` introduced `{state,outcome}` | smoke now verifies command outcome before inspecting state; native retest pending |
| Active playback without native renderer | Watchdog checked wrong binding but omitted renderer absence | source-bound physical `playback.failure` reporting includes null/invalid renderers |
| Reopening saved work, final, simplifications | Backend unit/integration paths exist; full physical sequence not witnessed here | actual instrument and separate platform/installation gate open |

**Core evidence:** GitHub Actions 44956785207 passed on the
MIDI-shortcut source-ownership revision. Full native-production
includes real Godot 4.7.2, embedded CPython, a synthetic hardware
MIDI port, production score view, original Moonlight/Peace Piece/Chopin
sources and a relocated package boot. It is **not** a substitute
for a physical Kawai CA49, audio/speaker test, clean second machine
or a full source-specific Pathétique acceptance.

Any change to this matrix should be paired with a real-path scenario
and an actual CI/physical observation, not a test that duplicates
the lesson/transport policy.
