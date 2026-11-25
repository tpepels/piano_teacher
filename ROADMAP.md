# Piano Teacher — roadmap

**Updated 2026-11-24 · MIDI input only · Timeline rebuild T1–T6 in software (`HEAD`); piano acceptance pending**

[Practice flow](docs/practice-flow.md) is the learner-visible contract.
[Architecture](docs/architecture.md), [development](docs/development.md) and
[reference](docs/reference.md) contain current technical documentation.
Superseded designs, detailed audit checkpoints and earlier phase logs remain in Git.

## Product

One Godot 4.7 desktop application, embedded CPython, native Verovio notation,
one immutable score stream and a single MIDI/transport timeline. MIDI
(`.mid`/`.midi`) and MusicXML (`.musicxml`/`.xml`/`.mxl`, converted to the same MIDI timeline) are the user imports. Generated MusicXML serves engraving.

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
| 2026-11-21 | Pause freezes the visible score even in Free/Listen/count-in; render only the selected practice measure window, retaining full sounding tails but no visible neighboring bars. |
| 2026-11-22 | Adopt A0–A7 architectural unification: one serialized PracticeSession; cohesive lesson, assessment, transport and score domains; one score preparation pipeline; physical Godot adapters; and complete migration/removal of redundant orchestration. Preserve supported features and real physical invariants; CI remains manual. |
| 2026-11-23 | Practice Flow is the only course. Remove the other courses and strategies, the warm-up course, lesson-screen extras, the no-piano timing preview, save-failure recovery and lost-reply recovery. |
| 2026-11-24 | Import MusicXML again (as the same MIDI timeline). Remove the Lesson path; add checkpoints every 4 measures. Game-style menus; 4.3 staff spaces per sixteenth; header glyphs never touch; status colour bleeds from the head. |
| 2026-11-24 | The course is a list of steps with a cursor; the aid is a phase; after a jump back, mastered windows are skipped. Tempo rises by 10% × (1 + timing quality) × length factor. MusicXML fingerings are kept. Calibration gets its own page and a tolerant measurement. Every control type gets its own visible look. |

## Musical timeline rebuild (T1–T6, adopted 2026-11-24)

Owner request: between-take placement must make musical sense (a repeat
after a note tied over the barline must not fail), Godot keeps the pace
and pulls what comes next, and tempo changes ease instead of jumping
(decided: half-cosine ease over the first half of the count-in bar).

**Problem.** Two clocks negotiate: Python pushes an absolute deadline,
Godot must "admit" it against what is on screen *now*. Every "cannot
admit / overlaps / expired" refusal is that race; a 2/4 bar (2 beats)
lost it (`f00a241e` relaxed the rule; the race remains).

**Design.** One declared musical timeline on the world-beat line, owned by
Python (MIDI arrives there, grading must not depend on frame timing) and
evaluated identically by both sides:

- Segments: take (source window, from_beat, authored tempo map), rest,
  count-in. Each has a world start in beats and tempo spans (constant or
  eased, `tempo_curve.py` / `tempo_curve.gd`), anchored to the shared
  monotonic clock. Time <-> world beat is a pure function of the timeline.
- Placement is bar arithmetic: next take = last sounding note (incl. ties)
  rounded up to the barline, then one count-in bar (ramp in its first
  half). New notation is placed the same way; if its score is not ready
  in time the rest grows by whole bars, never an error.
- Godot pulls: it reads the timeline at its own pace, draws world(t),
  places each segment's ink at its world start (refusing only what is
  already behind the playhead), and derives count-in, clicks and bar
  motion from the segments. Python appends the next segments when a take
  settles; a late decision adds a rest bar.
- Pause re-anchors the future segments; Free (untimed) stays a hold.

| Stage | Content | Status |
| --- | --- | --- |
| T1 | Exact constant/eased timing maths, Python + Godot | Done `c2a262b1` |
| T2 | Python `MusicalTimeline` model, built alongside today's transport and published in state; journeys log its agreement with today's deadlines | Done: today's admitted repeats start 1.4–14 s after bar arithmetic in the 4/4, 2/4 and Moonlight journeys |
| T3 | Godot scroll position from the published timeline (replaces presentation epochs); ramps visible | Done with T5: the world follows the published timeline during a run |
| T4 | Count-in bubbles and clicks from timeline segments | Done: count-in numbers and clicks read their beat from the timeline take, so the eased bar is counted as it moves |
| T5 | Continuations and Start/Resume append segments at bar positions; remove reserve/present admission for them; late decision = extra rest bar | Done with T3: every timed take is placed and started by Python; Godot draws it at its world start (pop-in allowed), no reserve/present; an unplayed abandoned take is withdrawn |
| T6 | Grading via the timeline inverse; remove fixed deadlines, reservation and clearance machinery; tests and journeys on the new contract | Done: live take position reads the timeline take; reserve/present/withdraw, physical admission evidence, fixed deadlines and the Godot reservation preflight removed. The outgoing-rest geometry, continuation deadline arithmetic, visual-motion projection and their state fields followed (`4535f58d`) |

Each stage keeps the 4/4 and 2/4 synthetic journeys, the test suite and the
full desktop check green before it is committed.

### Timeline rebuild in software — 2026-11-24

T1–T6 are complete in software. Follow-ups on the same day: legacy
deadline/geometry code removed; a take Godot could not draw (seen after
its first note, or notes lost while playing) is placed again once
automatically instead of stopping; a take requested at a Pause waits for
Resume without timing out; a failure to start a take no longer breaks the
MIDI key or tick that triggered it; cancelled exposures no longer publish a
failure reason. New MIDI journeys (`tests/test_midi_journeys.py`) cover
wrong, missing, extra and late notes, the Free return, slowing down,
mastery and seeded long journeys with Pause/Retry/Stop.

Second round (owner request, same day): the remaining take bookkeeping
(next-take deadline, announced continuation, preparation/rewind schedule,
next-step preloads and the runway's prepared renderer, scheduled start,
tempo epoch) is gone; the seek, section-review and partial-take routes were
proven unreachable and removed; grading times notes with the take's tempo
as placed on the timeline; Free runs on the timeline as holds, so Godot's
presentation epochs are deleted and so is the motion directive (state
contract 11). Owner decisions restored: Resume always gives a full
count-in bar; a too-early first note in the count-in is graded early;
repeats scroll in from the right (predicted repeat drawn early). Tests:
the failure matrix (`tests/test_failure_grading.py`) runs on right, left,
both hands, a two-bar window and MusicXML; a late decision adds a whole
rest bar; the native journey walks two failures back to Free and survives
a 14 s frame stall. Piano acceptance (sound, clicks, motion, the eased
count-in) is pending.

## Structural decoupling plan (R1–R8, adopted 2026-11-23)

**Why:** A0–A7 removed duplicate owners and parallel paths, but the
application layer is still tightly coupled. Measured on `7618737`: the
largest constructors take 32 (`PracticeTimeline`, `SessionReadModels`),
29 (`PracticeSession`) and 23 (`TransportActions`) collaborators;
`PlaybackSession` is used by 22 modules, `SourceIdentity` by 19,
`VisualTransport`, `AttemptRuntime` and `GuidedSession` by 16–17. Most
uses read one or two fields or repeat the same multi-call sequence, so a
small behavioural tweak ripples through many files. Goal: a change to one
behaviour touches one domain module and, at most, its call site.

**Target shape:** a few domains, each the *only* owner of its state, with a
narrow public interface: `facts()` returns a frozen read snapshot;
intention-named operations perform writes (one method per behaviour, never
a sequence of setter calls at the caller). Orchestration lives in small
event handlers that depend on domains, not on their internals.

| Domain | Owns (internal) | Replaces direct use of |
| --- | --- | --- |
| Transport | timeline (`VisualTransport`), session intent (`PlaybackSession`), physical admission (`PlaybackCoordinator`) | `visual_transport`, `playback_session`, `playback` |
| Lesson | source/plan identity, lesson cursor, teaching decisions, flow, guided selection | `source_identity`, `lesson_cursor`, `teaching_decisions`, `flow_session`, `guided_session` |
| Take | attempt runtime, recorder, settlement and completion receipts | `attempt`, `attempt_settlement` |
| Score | artifacts, bundle, successor preparation, read services | `score_artifact_registry`, `teaching_continuation` (assets), `score_read` |
| Session | event boundary, tick worker, notices, read model | `PracticeSession`, `PracticeTimeline`, `SessionReadModels` |

**Measurable exit (all on one HEAD, gates green):**
1. No application class takes more than 10 constructor collaborators.
2. Outside its domain module, no code references a domain's internal
   state holder; reads go through `facts()`, writes through named operations.
3. No multi-step state sequence is repeated at more than one call site.
4. The read model is built from domain `facts()` only.
5. Tests reach the engine only through its public operations
   (`EngineCommands` / the session harness), except pure-function tests.
6. `bash scripts/test.sh --coverage` and
   `bash scripts/verify-embedded-production-local.sh` pass on that HEAD;
   no learner-visible behaviour changes.

**Order (each step is committed green before the next):**
- **R1 Transport.** Introduce `TransportFacts`; route all external reads
  through it; add named operations for every external write sequence; then
  hide the three holders behind `Transport`.
- **R2 Lesson.** Same for source/plan identity, cursor, teaching decisions,
  flow and guided selection; merge `LearningActions`/`LessonExecution`/
  `ExposureWorkflows` behaviour into Lesson operations where it only
  manipulates lesson state.
- **R3 Take.** Same for attempt runtime and settlement; one completion API.
- **R4 Score.** Same for artifacts, bundle, preload and read services.
- **R5 Read model.** Build the snapshot from domain `facts()`.
- **R6 Handlers.** Reduce `PracticeSession`, `PracticeTimeline`,
  `TransportActions`, `CompletionContinuations`, `RecoveryWorkflows` and
  peers to handlers over domains (≤ 10 collaborators); delete layers that
  become pass-through.
- **R7 Tests and Godot.** Move tests onto public operations; apply the same
  review to Godot admission/stream orchestration.
- **R8 Verification and docs.** Same-HEAD gates, coupling measurements,
  docs/architecture.md.

### Course as a list, variable tempo, fingering, calibration — 2026-11-24 (`5ef…3ac7590e`)

- `teaching_course`: one ordered step list (window × hand) and a cursor;
  progress is the current tempo/failures/clean takes, mastered steps and
  Free returns. Variant dimension, tempo history/carry-over and guided-idea
  navigation removed (~900 lines). The aid is `practice_flow.Step.AID`,
  held by the flow session. Owner's saved session restores exactly (checked
  on a copy of the database).
- Tempo step = 10% of target × (1 + timing quality) × clamp(8/attacks, 1,
  2.5); ladder tests now assert behaviour, not step sizes.
- MusicXML fingerings are authored, fixed fingers (grace notes excluded).
- Calibration: 24 taps, median of consistent taps, accepted at ≤60 ms
  deviation, early tapping = no correction; its own page with a tap strip.
- Controls: menu choices (key notch), key-cap actions, pick-one key groups,
  card rows with a play badge, card tiles.
- Gates: 191 Python tests, Godot checks; full desktop check on `541a587a`
  (synthetic-MIDI journey fixed and re-passed on `3ac7590e`). Nothing here
  is tested at the piano.

### Thin practice screen and direct aid — 2026-11-24

- The practice screen's "More" popup (instruction, progress, feedback,
  streak, hand stages, fingering status, performance review, tempo popup)
  was unreachable whenever a piece was loaded, and problems that need the
  learner only reached those invisible labels. `screen_projection` now
  owns status, notice and keyboard; Godot displays them (notice on the
  score banner). Nine Godot scripts and ~1,300 lines removed.
- The Practice Flow aid enters Free directly; the timed remedial review
  and its flags never ran. pyflakes (per-file) cleaned 15 unused imports
  that vulture's package-wide name matching cannot see.
- Not tested at the piano: the banner text for no piano / failed
  admission / a refused command is new to the learner.

### Practice Flow only — 2026-11-23/24 (`aa0caace`…`50c8e46c`)

Owner decision 2026-11-23: remove what is not wired into Practice Flow.
Removed: alternate courses and exercise/diagnosis/mistake-response
strategies, the warm-up course, lesson-screen extras, rolling (mid-take)
recovery, the no-piano timing preview, save-failure replay (a failed save
now shows the fault and discards the take) and lost-reply recovery in
score admission (a failed reply cancels the provisional admission).
vulture was iterated until clean and the coverage report was checked for
uncovered code that nothing references; live but untested features (seek,
section review, Perform, fingering correction, device diagnostics) stay.

Structure: every "what happens next" rule is in one module,
`practice_flow_course` (`decide`, `graded_progress`), over the pure ladder
reducer `application/practice_flow.py`. The always-true `flow_active`
switch and its dead branches are gone; a finished take plans one of
stop / ready / announce. Without a piano, choosing Practice waits visibly
("Connect your MIDI piano to play in tempo.") instead of a stuck exposure.

LOC since `223fc503`: Python 34,235 → 29,078 (application 14,681 →
12,821); GDScript 25,674 → 25,369. Nothing here is tested at the piano.

### R1–R8 exit criteria met — 2026-11-23 (same-HEAD gates on `223fc503`)

1. **Fan-in ≤ 10:** met for every application class (was 12 classes
   above 10, max 17). Each split follows a real event family; see the
   ownership table in docs/architecture.md (completion → grading /
   immediate consequences / settlement; tick → observations /
   transitions / progression / publication; transport → authorization /
   commands / replay / routes; timed playback → start / continuation /
   pause-resume; MIDI → callback / delivery / device; read model →
   capture / presentation / extras / snapshot; recovery → selected /
   rolling; source → preparation / installation / library opening;
   history → reads / deletion; exposures → guided / timed installers;
   teaching → decisions + LearnerEvidence).
2. **No outside access to domain internals:** 0 (the audit now excludes a
   domain's own modules, which it had counted).
3. **No repeated multi-step sequences:** named the shared ones (Listen
   outcomes, plan adoption ×3, measured continuation ×3, Free-target
   arrival ×2, mistake policy ×4, terminal admission failure ×2, active
   segment reset ×2, course restart ×3); a 3-statement duplicate scan of
   application modules finds none.
4. **Read model from domain interfaces:** it reads only domain objects'
   public properties and read ports (wired once in composition), never
   internals; there is no single `facts()` object per domain.
5. **Tests use public operations:** Python as in R7; the native Godot
   journeys now use public app/gateway operations too.
6. **Gates on `223fc503`:** `bash scripts/test.sh --coverage` 235 passed,
   Godot syntax + 5 behaviour scenarios 0 failures, 76.6% lines / 56.1%
   branches; embedded verifier with Pathétique II 26 PASS.

**R2 merge:** pure lesson reads (`flow_active`, `display_phrase`) are
Lesson operations; LessonExecution's course flow and navigation are
separate owners; LearningActions only routes. **R7 Godot review:** no
cross-object private access in production Godot code, no duplicated
admission/stream blocks; `_admit`'s guards are named (a NaN timeline
duration now fails closed). No learner-visible behaviour changed in this
step. Physical piano acceptance pending.

### Owner piano report fixes — 2026-11-23 (`abe746d5`)

- **Free accepted keys before the notes were on screen.** The guided
  controller listened from the score-ready ACK while Godot was still
  moving the first target in (it arrives at the published guided
  deadline). Free attacks before that deadline now earn nothing and the
  prompt reads "Wait for <note> to reach the line" until it arrives.
- **Dimmed notes had darker overlaps.** Per-stroke 46% alpha stacked;
  dimmed ink is now one opaque colour pre-blended over the score fill.
- **Double flag after the practised Pathétique measure.** The clipped
  first quarter beat of the next (context) bar's sixteenth beam was
  painted; connectors with both ends in context bars are now hidden.
  Confirmed before/after in a windowed real-scene capture on an isolated
  HOME (not a pixel test).
- Not changed: a timed take still credits an attack up to one onset
  tolerance before the downbeat: the larger of 150 ms and a sixteenth
  (about 0.9 s at 16 BPM, i.e. inside the last count-in click).
- Observation: a hidden window is throttled to ~1 FPS by the compositor;
  admission then exceeds its 150 ms arm budget and Listen fails after
  three attempts. A visible window admits in milliseconds.

**Gates on `abe746d5`:** `bash scripts/test.sh` 235 passed, Godot syntax
+ behaviour 0 failures; embedded verifier with Pathétique II 26 PASS.
Physical piano acceptance pending.

### Event boundary split — 2026-11-23 (same-HEAD gates on `0b178399`)

`PracticeSession` only serializes events and publishes the committed
MIDI epoch; the one table of which workflow handles each event and
command family is `session_routes`. `CommandRouter` (UI intents, lesson
decision), `TickWorker` (bounded same-tick loop, deferred MIDI replay)
and `MidiEpoch` (stale-key gate) carry the former session internals
unchanged. PracticeTimeline no longer touches score or Listen:
TimedPlayback owns measured/preview continuations (shared with
recovery) and ExposureWorkflows ends a finished Listen. Fan-in:
PracticeSession 23 → 4, PracticeTimeline 19 → 17; max 17 (12 classes
> 10). The ≤ 10 target is still not met by the multi-domain workflows
(CompletionContinuations, PracticeTimeline 17; SourceWorkflows 16).

**Free stall follow-up:** the lost-present-ACK scenario ran 8 consecutive
times on `8c5e63c9` and 2 more in full verifier runs: all passed; not
reproduced. The fake-MIDI journey heartbeat now prints the Free-hold
facts (guided world, held target, projection, painted staff, targets) so
a recurrence identifies the stuck condition.

**Gates on `0b178399`:** `bash scripts/test.sh --coverage` 235 passed,
Godot syntax + 5 behaviour scenarios 0 failures, 76.3% lines / 56.0%
branches; `bash scripts/verify-embedded-production-local.sh` with
Pathétique II supplied: 26 PASS. No physical piano acceptance claimed.

### R1–R8 completion — 2026-11-23 (same-HEAD gates on `2cd6eade`)

**Owner-reported defects fixed (Pathétique II, right hand):** at 50%
(16 BPM, 2/4) the count-in clicked 3.75 s apart and keys played during it
were silently ignored, so the take then ran over an apparently idle staff.
`CountInPlan` keeps one authored bar but subdivides its pulse while a
click would exceed 1.5 s; Godot uses only the authorized `pulse_beats`
(its own meter rule, which also disagreed for 2/2 and 3/8, is deleted);
a key during the count-in shows "Too early – wait for the count-in, then
play". Screen glitching: the suspended Practice screen stayed visible
under Library/Settings/Lesson; only the active screen is now drawn.
**Adaptive tempo (owner decision):** a secure clean take (every onset
within half its timing window) skips a step (+20% of target);
docs/practice-flow.md updated; ladder tests updated to the new rule.

**Decoupling result:** Transport, Lesson, Take, Score and MidiInput are
domain objects whose internals no outside module references (0 in
`scripts/audits/coupling.py`); cross-domain internal links were replaced
by domain interfaces (PlaybackSession, Stop, settlement reservation
port); repeated transport sequences are named operations; everything
after a take ends lives in CompletionContinuations; tests use public
operations (`playback.status` gained `intents_issued`; engine close joins
the Listen worker). Constructor fan-in > 10: 13 classes, max 23
(was 19, max 32). Exit criterion 1 (≤ 10 for every class) is **not**
met: the event boundary (23) and tick worker (19) coordinate every
handler, and the remaining workflows use each collaborator for real work;
grouping them only to reach the number was rejected as cosmetic.

**Gates on `2cd6eade`:** `bash scripts/test.sh --coverage` 235 passed,
Godot syntax and 5 behaviour scenarios 0 failures, coverage 76.3% lines /
56.3% branches; `bash scripts/verify-embedded-production-local.sh` with
`PIANO_PATHETIQUE_II_MIDI` supplied: 26 PASS including the native
Pathétique II case. **Intermittent observed:** on `f09ab536` the
lost-present-ACK fake-MIDI scenario once stalled waiting for the first
Free target to settle (no error logged); it passed on the rerun and on
every earlier commit. Watch for it at the piano (Free after Listen).

**Piano checklist additions:** slow pieces count in audibly in
subdivisions; a key during count-in shows the "Too early" notice; precise
clean takes skip a tempo step; switching screens shows no score behind.

### R progress — 2026-11-23 (HEAD after R6 step; 235 Python tests green)

Done: R1 Transport, R2 Lesson, R3 Take, R4 Score and MidiInput domains
(internal holders reached from 0 modules outside their domain, down from
8–22); PlaybackSession and Stop bound to domain interfaces instead of
other domains' internals; Score is the settlement's reservation port;
R5 read model receives timing/phase objects (22 → 15); R6 take-ending
logic moved wholly into CompletionContinuations (timeline 23 → 19).
Fan-in > 10: 13 classes, max 24 (was 19, max 32) — see
`scripts/audits/coupling.py`.

Remaining: R6 orchestrator fan-in (PracticeSession 24, PracticeTimeline 19,
CompletionContinuations 17, SourceWorkflows/TransportActions 16,
RecoveryWorkflows 15); R7 port tests off internals (`playback.sequence`,
`transport_timing.request_playback`, `timed_playback.continue_at`,
`listen.thread`, `source_identity.plan`, `notices.feedback`) to
`playback.status` and public ACK commands; Godot admission review; R8
same-HEAD `test.sh --coverage` + embedded verification and docs update.
Godot/embedded gates have NOT been rerun since `7618737`.

## Active architecture unification roadmap (A0–A7, adopted 2026-11-22)

**Status: SOFTWARE COMPLETE, PHYSICAL ACCEPTANCE PENDING. Software state on `7618737`: every A0–A7 item is complete in software, with evidence in the 2026-11-23 checkpoints and docs/architecture.md. Physical acceptance at the piano (and the Pathétique II native case, whose source was not supplied) is pending. See the A2/A3 executed verification checkpoint.** This is
the next development track. The V0–V7 implementation/acceptance work and
older S0–S7 decomposition remain below as historical evidence and open
verification requirements, **not** as a requirement to keep all existing
abstractions. The user will perform connected-piano MIDI/audio/visual
acceptance after software development.

**Objective:** Replace accumulated per-problem coordinators, mutable phase
mirrors, callback handoffs and duplicate preparation/projection protocols
with one coherent, inspectable application. Preserve the complete current
[practice-flow specification](docs/practice-flow.md), supported alternative
courses and warm-ups, original MIDI note identities, authentic Verovio
notation, retained physical ink, real-time input and saved progress. A
renamed coordinator chain or new monolithic PracticeEngine is not completion.

### Evidence from current main and audit hypotheses

Source audit at **4a80bee** found **63 constructed Python services**, **79
Python application modules** and **146 production Godot scripts** (49 of them
notation scripts; developer MCP addon excluded). These counts are descriptive,
not size targets. The 343-line PracticeEngine facade is thin, but the object
graph and transition lifecycle remain spread across many owners.

| Current modules/responsibilities | Audit hypothesis and required decision |
| --- | --- |
| PracticeControls, ControlDispatcher, SessionCommands, LearningActions, TransportActions | Several routes/context scopes participate in one gesture; replace with one locked event transaction while retaining the actual lesson decision |
| PlaybackSession, PlaybackCoordinator, VisualTransport, TransportTiming, TimedPlayback, SessionPhase | Playback state and timing are distributed; distinguish legitimate independent facts from duplicate mutable authority before merging |
| PracticeTimeline, CompletionContinuations, TeachingContinuation, RecoveryWorkflows, AttemptSettlement, ExposureWorkflows | Multiple handoffs represent one lesson/take continuation; PracticeTimeline.update explicitly imitates former recursive publications and should be replaced by ordered event processing |
| SessionReadModels, SessionSnapshotBuilder, ScoreStatePublisher, control_projection, state_projection | Multiple state/projection passes; aim for one published model from one committed state |
| ScoreAssetSession, FutureScore, ScoreRunway, ScoreReadServices | Normal source requests layout then semantics, preloaded source supplies both together; unification can remove independent request/identity/retry paths |
| ScoreAdmissionGateway, ScoreTransportReservation, ScoreStreamQueue, native ScoreStreamController | Physical queue and attestation are necessary; reduce orchestration surface without weakening the immutable ledger |
| lesson_generators, exercise_strategies, lesson_settings.json, SettingsScreen, ScoreLibrary | Default Practice Flow already incorporates remedial Coda/Fukuda; investigate separate selectable Coda/Fukuda course, policy pickers and historical numeric defaults |

**Feature-retirement gate:** Current settings expose both **practice-flow**
and **coda-fukuda-midi**. Built-in warm-ups use **source-progression**. A0 must
identify all real callers, stored selections and supported behavior. Do not
silently remove a selectable course, warm-up, useful policy or readable saved
history. Explicitly record any owner decision required to retire a feature.
Historical persistence migrations can remain at the storage boundary where
existing installations need them; runtime compatibility branches and dead
headless fallbacks require current consumers or removal. The older
lesson_settings.json defaults for three clean runs and two-bar focus must
not compete with the documented default Practice Flow (two target-tempo
clean passes and moving windows of at most four measures).

### Proposed architecture: one session, bounded domain ownership

    Godot UI and timestamped MIDI / physical-device input
                         |
               typed in-process commands
                         |
                   PracticeSession
         one serialized transition coordinator
         one authoritative session aggregate
                         |
        +----------------+----------------+
        |                |                |
    Lesson domain   Transport domain   Assessment domain
    window/hand     epochs/deadline    MIDI matching
    progression     transaction        take verdict
    recovery        pause/count-in     release evidence
        |                |                |
        +----------------+----------------+
                         |
      Source/Score · Persistence · Presentation projection
                         |
        Godot physical score surface and local audio
       immutable queue · true clearance · retained ink

The architecture remains **one desktop Godot + embedded Python runtime**.
Do not introduce a network service, generic message bus, event-sourcing
framework, plugin system, duplicate practice engine, second musical clock or
global service locator. PracticeSession sequences events and commits one
authoritative state; domain components provide cohesive pure decisions or
infrastructure operations, without running separate lesson lifecycles.

**Canonical event path:**
1. A user gesture, timestamped MIDI, tick or asynchronous completion arrives
   as a typed event with source/attempt/take identity as applicable.
2. PracticeSession validates identity, fresh-state eligibility, and event order
   under the existing short application lock.
3. The relevant lesson, transport, assessment or score domain returns a typed
   decision/effect; only its owner may make that decision.
4. A single transaction commits the change and durable settlement, then
   issues explicit effects (prepare, reserve, persist, notify) in defined order.
5. Physical reservation/receipt/failure returns as an **event**, never a
   speculative success; state is projected once into controls, score motion,
   feedback and audio for the accepted version.

**Authority and necessary physical split:**

| Domain | Sole Python authority | Godot/infrastructure authority |
| --- | --- | --- |
| Lesson | Selected measure window/hand, Listen/Free/Tempo, tempo ladder, retries, aid, mastery and saved course state | Draw selection and forward input; no progression inference |
| Assessment | Matching original note IDs, note-on/off evidence, extra/missed notes and graded result | Timestamp MIDI and paint approved feedback |
| Transport | One take/source epoch, count-in, Pause/Resume/Stop, deadline, musical rate map, playback intent/receipt and recovery | Measure available physical travel, provisionally arm, attest, withdraw safe future ink and report exact failures |
| Score | Original MIDI identities, semantic notes, authored/sounding bounds, immutable prepared bundle | Authentic engraving, cache/prewarm glyphs, retained rendering |
| Presentation | One pure versioned projection of committed lesson/transport/assessment state, controls, notices and motion directives | Smooth interpolation/paint; emit audio/cues keyed to authorized segment |
| Persistence | Progress, history, settings, learning evidence and migrations | Display read-only data and request approved actions |

**Non-negotiable invariants:** One musical clock and scheduler; one selected
source identity; one graded take; full authored count-in including odd meter;
no grading without authorization; paused/Free notation holds; one immutable
forward-only physical score ledger; previously exposed ink is never retimed
or rewritten; native preflight and measured pixel clearance remain native;
Python alone chooses a deadline after source-bound physical evidence; native
may refuse but never substitute a new deadline; reserve → arm → attest →
present remains idempotent and recovers from missing/reordered ACKs; stale
source/revision/take/segment replies fail closed; original sounding tails,
selected window bounds, real-source Coda/Fukuda changes, saved evidence,
asynchronous engraving and texture prewarming are preserved. The live
hardware/visual constraints justify these safeguards even if individual
intermediate wrappers can be eliminated.

### A0 implementation checkpoint — 2026-11-22

**Source commits:** [005b8b6](https://github.com/tpepels/piano_teacher/commit/005b8b63d6a08c3d1aa524c926c6fcdedf4d74bb) and
[08a1f6e](https://github.com/tpepels/piano_teacher/commit/08a1f6e5da98e0f4c4dbafe5bdefeaf1f0c71a0b).
The source-audit record is in [docs/architecture.md](docs/architecture.md#a0-runtime-and-ownership-baseline--source-inspection-2026-11-22).

**Completed source-stage work:**
- Inventory of all **79 Python application modules**, **120 other Python source
  modules**, and **146 Godot GDScript modules** outside the developer addon,
  with tentative phase homes and disposition classifications. This is a
  path-complete static inventory, **not a claim of fully proven reachability**.
- Trace of the native C++/embedded Python command/tick/asset workers,
  Godot state/command interfaces, MIDI ingress, application lock and
  source-mutation/fingering/prefetch threads, persistence and physical
  reservation/reconciliation boundaries.
- Source-backed risk register and **19 production scenario/acceptance
  traces** for source opening, Listen, Free, Tempo, repeated takes,
  Coda/Fukuda, mastery, Pause/Resume/Stop, stale/lost ACK, disconnect,
  preparation failure, saved reopening, cues and settings/history/fingering.
- Explicit legacy candidates: recursive publication emulation; distinct
  normal/preloaded score lifecycle; distributed transport state; continuation
  and snapshot coordinator chains. Retained-ink admission, physical evidence,
  full-meter count-in, async engraving and real source identities remain
  required safeguards.
- Confirmed current user-selectable practice-flow and coda-fukuda-midi
  strategies, with source-progression used by warm-ups. No supported course
  or saved-data format was removed or declared obsolete by assumption.
- Verified latest available GitHub Actions run record still shows
  **45017492022 on 1c1b98e** as the last full green suite; its success
  predates all later commits, including this audit.

**Additional A0 progress (2026-11-22):**
- [9ec6936](https://github.com/tpepels/piano_teacher/commit/9ec6936c421775c96098a1e9e5ad7c996a269407)
  adds `scripts/audit-a0-reachability.py`, a **read-only, conservative**
  static graph of Python imports, Godot resources, declared classes and
  project roots. It separates production entrypoints from test references
  and reports unresolved computed loads. Usage:
  `python3 scripts/audit-a0-reachability.py --json --output /tmp/piano-a0-reachability.json`.
  A path absent from its static graph **cannot** be deleted on that basis;
  class-name matching, reflection, dynamic sources and execution still
  require manual confirmation. The script has not been executed against
  a complete checkout of this exact revision in this environment.
- [cc00718](https://github.com/tpepels/piano_teacher/commit/cc00718c59d13160f8bfbd7d408579790a3e58ac)
  documents the current command, MIDI, tick, source-load, physical
  reserve/attestation and snapshot APIs and proposed A1 typed-event
  conversion in [architecture](docs/architecture.md#a0-reproducible-reachability-method-and-concrete-a1-contract).
  A session commit and asynchronous physical acknowledgement are distinct:
  no grading/sound starts until exact attested presentation is accepted.
- Confirmed live imports: PracticeScreen uses ChallengeFlow and
  TempoVocabulary; PracticeChrome constructs advanced Pause/review UI;
  DemoPlayer uses ListenSync; NavigationSession uses NavigationPolicy.
  The ChallengeFlow three-run fallback must be checked against a valid
  course-specific backend count. This is an audit warning, **not** a
  reproduced failure.
- [600eeb5](https://github.com/tpepels/piano_teacher/commit/600eeb5a5c2d9408686ce1674a0c8225e43c6cfc)
  quantified the actual `application/composition.py` constructor
  dependency graph: **21 of 63 services** have at least 10 direct injected
  `r.*` dependencies, and **14 have at least 15**. `PracticeTimeline`
  reaches 33, `SessionReadModels` 25, `TransportActions` 24.
  `godot/main.gd` has 42 unique preload references and 44 `.new()`
  call sites. The report also documents the existing independent
  C++ asset worker for score geometry, semantics and statistics;
  A1/A4 must preserve that non-blocking division.
- [97e117c](https://github.com/tpepels/piano_teacher/commit/97e117ce22bcedf58599a1d9871cdf87f1332d4b)
  corrected the auditor's dynamic-load detection so whitespace before
  literal Godot paths is not mistaken for computed loading. The auditor
  remains conservative; full-repository runtime execution is pending.
**Owner-run A0 audit and regression correction (2026-11-22):**

- The owner ran `bash scripts/test.sh --coverage` locally against
  the previous audit revision: **159 passed, 4 failed (27.04 s)**.
  Three failures shared the missing required
  `playback_timeline` in headless session snapshots. The fourth
  exercised `grade_note_holds=True` while Listen audio was preparing;
  `SettingsWorkflows.update` stopped the entire lifecycle and
  cancelled the ungraded Listen render before the fixture could use it.
- [3726c45](https://github.com/tpepels/piano_teacher/commit/3726c45f00d38e20a69ed67ed45f6ef256e7f1bc)
  restores the real coordinator's `playback_timeline` to the
  headless published state. It also brings the full state snapshot into
  agreement with the existing lightweight locked control projection.
  No fake physical receipt was added.
- [6f6ea2e](https://github.com/tpepels/piano_teacher/commit/6f6ea2e7bba5eb7b073aa1b2d932e412a5408b6c)
  preserves existing Listen and Free preparation when the optional
  hold-grading rule changes; changing the rule during a graded
  practice/perform exposure still invalidates that take.
- The owner's reachability report listed **nine statically unreached
  files**, but manual source resolution classified all nine:
  four are launched by native Godot verification scripts; five are
  implicit Python package initializer files. The one flagged
  dynamic Godot load resolves to the four tracked spoken-count-in
  Ogg assets, not executable code. **No deletion is justified.**
  [835613a](https://github.com/tpepels/piano_teacher/commit/835613a81ebb4a1f2462e6c5100ab4dd4dc756d0)
  improves the auditor to account for implicit package dependencies
  and test-harness `--script` entrypoints.
- Detailed failure analysis, code-path evidence and candidate
  disposition are in
  [docs/architecture.md](docs/architecture.md#a0-observed-local-baseline-and-reconciled-reachability-2026-11-22).

**A0 checkpoint outcome:** The source-backed reported reachability
candidates are reconciled and both observed regression causes have
production-code fixes committed to `main`. **Neither fix has yet been
locally re-tested on the resulting HEAD.** Full-core, Godot behavior,
embedded fake-MIDI, source repertoire and package gates remain open.
A0 is still **IN PROGRESS**; do not mark it accepted or begin A1
based solely on old test results.

**Open A0 exit gates:** Every candidate's *runtime* call/writer reachability
must be proved (including dynamically loaded native scenes and registered
generators); full source-to-transaction/async edge coverage and exact HEAD
core/native/repertoire/relocated-package execution must be recorded. The
current connected source environment cannot run Python 3.14/Godot 4.7.2
or dispatch a new workflow. Consequently A0 is **IN PROGRESS** rather than
complete. No A1 production code, behavior, tests or physical MIDI acceptance
has been changed by this checkpoint; CI is still manual-only.

### A0 — Complete dependency, behavior and legacy audit

- [x] Map every active Python/Godot production entrypoint and state writer:
  buttons, keyboard/MIDI notes, in-process request/response, timer, source
  replacement, async preparation, score admission, audio, persistence,
  project scenes/autoloads and standalone package. Include threads, lock
  boundaries, callbacks and physical generation IDs.
- [x] Inventory every composed service/native coordinator with its owned
  state, callers, side effects and current product purpose; classify each
  **retain / merge / remove / migration-only / undecided** with evidence.
- [x] Trace actual default journeys end to end: new MIDI, per-bar moving
  windows, hands, Listen, Free, Tempo, clean/failure/repeat, remedial
  Coda/Fukuda, full-piece exam, saved reopen, Pause/Resume/Stop, navigation,
  disconnect/reconnect, failed admission, lost ACK and source switch.
- [x] Inventory selectable alternate courses, built-in warm-ups, diagnosis
  and learner policies, old settings/parameters, test-only/headless ports,
  migrations and saved-data compatibility. Record explicit product decisions
  where retirement changes supported behavior.
- [x] Capture an **exact-HEAD** baseline of tests, known failures, native
  scene/repertoire/package gates, performance and timing traces. The last
  known green full run was on **1c1b98e**, not the later source commits.
  Do not claim current-HEAD green without execution.
- [x] Produce dependency/ownership map, typed event/outcome contract,
  deletion/migration ledger and risk/verification matrix. Classify every
  safeguard as a live requirement, historical workaround or unknown.

**Exit A0:** No active feature/entrypoint or mutable owner is unclassified.
Every current component has an intended destination or evidence-backed
retirement, and explicit unresolved product decisions are recorded.

### A1 implementation progress — 2026-11-22

A1 began after the source-backed A0 reachability classifications, at the
owner's request to keep developing; **A0's exact-HEAD local test/embedded
verifier gates remain open**. Work below is integrated but does not meet
the phase exit criteria:

- [5b4488b](https://github.com/tpepels/piano_teacher/commit/5b4488bc29621e1956a15ece07999a747d91010c)
  removed the old recursive-return **multiple publication** emulation.
  The native worker still settles all immediate automatic handoffs under
  the application lock, but publishes playback status and live feedback
  **once** rather than 1+N times for the same tick.
- [118fbe2](https://github.com/tpepels/piano_teacher/commit/118fbe2e459ed4063a48b3a60f2f2daed983e6dd)
  separated transition settlement from presentation. The existing
  `ApplicationWorker` owns the ordered lifecycle
  **settle same-tick transitions → replay timestamped deferred MIDI →
  publish final transport/live state once → schedule next wakeup**.
  The prior MIDI replay ran *after* publication, so one tick could expose
  an intermediate source without its hardware evidence. No additional
  musical clock, worker or synthetic grading was added.
- [5ca1085](https://github.com/tpepels/piano_teacher/commit/5ca1085bc7020a48b68f6e65e8a5c065e6c19fb8)
  unified native command-state and frame-state transaction projection
  through `SessionReadModels._committed_base`. It gives both consumers
  identical pending/authorized/failure state and course progress.
  `ScoreStatePublisher` now only contributes guided source and
  presentation motion; headless tests still receive the real
  `playback_timeline` without a fabricated physical receipt.
- [7e9d4c6](https://github.com/tpepels/piano_teacher/commit/7e9d4c634c482c6e5ff28228fd1717acacdd3012)
  makes a `practice.command` action and its returned authoritative
  state **one RLock transaction** in `EngineCommands.request`. A
  concurrent MIDI callback cannot change the source/phase between the
  accepted action and the response Godot consumes.
- Inspected all 13 committed Python behavior-test modules: none directly
  invoked the removed `PracticeTimeline.update` method. This source
  reachability check is not a successful execution of those tests.

**Historical A1 baseline, superseded by later integration:** This
checkpoint preceded the typed `PracticeSession` merger and deletion of
`PracticeControls`, `ApplicationWorker`, `ControlDispatcher` and
`SessionCommands`. Its stated open work was accurate at that commit;
refer to the latest A1 checkpoint below for current remaining work.

**Verification:** No executable Python/Godot runtime is available to this
connected repository environment. The previous local log of 159 passing
and four failing cases predates the source fixes and these A1 changes.
GitHub Tests remains opt-in `workflow_dispatch`; no CI run was triggered.

### A1 source integration checkpoint — 2026-11-22

**Production ownership replacement (directly on `main`):**
- [d78eafa](https://github.com/tpepels/piano_teacher/commit/d78eafa7f6552df79142bac4a32507cad7a2687e)
  introduced one `PracticeSession.apply` boundary for typed user, hardware MIDI
  and native tick events. `ApplicationWorker` and `PracticeControls` were
  deleted. The native C++ monotonic worker, `r.lock`, and existing lesson and
  assessment policy owners were retained. The actual `PracticeEngine.control`,
  `advance_clock`, `MidiApplicationInput.receive`, and MIDI shortcut call
  paths now enter `PracticeSession`.
- [c63aa90](https://github.com/tpepels/piano_teacher/commit/c63aa902eeac433687fedbfed08705d8d117bf67)
  migrated physical presentation enable/reserve/present/withdraw/failure,
  version-bound successor preloads, prepared source adoption, settings,
  device selection and shutdown to typed session events. The existing
  `TransportActions` remains responsible for actual physical authorization;
  its validated `PlaybackCoordinator` receipt contract was not replaced.
  Source import and expensive fingering inference remain outside the musical
  lock behind the existing `source_mutation` guard; only adoption is locked.
- [5ab3f3a](https://github.com/tpepels/piano_teacher/commit/5ab3f3a10937abefd46ef86d41a6bd8dff917bc5)
  removed a redundant inner command/MIDI lock and made MIDI shortcut
  capture and control execution explicit session events. The hardware
  adapter no longer mutates lesson controls or settings itself.
- [7060171](https://github.com/tpepels/piano_teacher/commit/7060171a748febb62b5474ddefe6b52cf4d97a79)
  assigns completed hardware key-range persistence to `SettingsWorkflows`,
  avoiding a cross-domain `settings_workflows.library` reach-through.
- [ca17e6c](https://github.com/tpepels/piano_teacher/commit/ca17e6cdf8d9ec85b213d3806fbf6fd7a2461ba3)
  routes calibration, hardware mutation, history export and history
  deletion through the same locked session boundary.
- [07c25d0](https://github.com/tpepels/piano_teacher/commit/07c25d0c740bf188135cc2f50da7e61eb4a5ce19)
  closes the public `PracticeEngine.start` direct-mutator bypass.
- [e96b418](https://github.com/tpepels/piano_teacher/commit/e96b418e2536384c0ba8ada0d8dfc760f996d043)
  separates frozen typed event envelopes into
  `application/session_events.py` from the stateful
  `application/practice_session.py`. The facade imports contracts rather
  than importing the coordinator for its public command DTOs. Every event
  class has a corresponding session branch in source inspection.
- [db344df](https://github.com/tpepels/piano_teacher/commit/db344dfe90b31d3e01e5ebf5785dbd53574ab83d)
  splits costly source-bound fingering correction into capture → inference →
  validated installation. The final revision/score invalidation is one
  `PracticeSession` event; original-note and source-generation checks
  remain authoritative.
- [29d6aa0](https://github.com/tpepels/piano_teacher/commit/29d6aa0d2df42acc2b77306b4bc39e04c8d82b2e)
  fixes a regression in that consolidation: native MIDI arrival time must be
  sampled **before** waiting for the session lock, not inside the event
  handler. Deferred MIDI retains the separate recorded/corrected timestamp.

- [Source dependency audit, 2026-11-22] After deleting the two old
  coordinators and migrating fingering installation, all **79 current
  `piano_teacher/application/*.py` modules** were individually scanned
  for imports/callers of `PracticeControls`, `ApplicationWorker`,
  `application_worker`, `practice_controls`, the former public
  `receive_message` entrypoint and `SourceWorkflows.correct_fingering`.
  **No remaining reference was found.** This is a production source
  reachability result, not execution or proof of feature acceptance.
  The source-level writer map, remaining mutable context and serialized
  event inventory are documented in
  [architecture](docs/architecture.md#a1-concrete-serialized-write-boundary--source-integration-2026-11-22).

**Historical open items, since migrated:** Later commits delete
`SessionCommands` and `ControlDispatcher`, and place decision validation,
idempotence and prepared source-bound exposures with `TeachingDecisions`.
`PracticeTimeline` still handles automatic continuation, while background
library health and future-score preparation remain intentionally
asynchronous. The remaining A1 acceptance checks are recorded below.

**Testing:** No runnable Python 3.14/Godot 4.7.2 checkout is available in
this connected source environment. These changes have been committed and
source-inspected only; **no current-HEAD test, fake physical MIDI, native
packaging or keyboard-acceptance pass is claimed.** A0/A1 gates stay open.
The user runs local checks; GitHub Actions remain manual-only.

### A1 effect context and MIDI replay integration — 2026-11-22

**Code integrated on `main` since the earlier source checkpoint:**

- [de0ac59](https://github.com/tpepels/piano_teacher/commit/de0ac59d0037a8a992c805c389025a845598fa6b)
  eliminated the extra `ControlDispatcher` class/file. Accepted user
  actions are routed within `PracticeSession` after current-state UI
  eligibility is resolved.
- [9f724b3](https://github.com/tpepels/piano_teacher/commit/9f724b330eb3f5e22d88708a65e39a13a67049f1)
  changed deferred MIDI from an unexamined tuple into a source-bound
  `DeferredMidi` value retaining original fingerprint, revision,
  selected stage/hand, take transport, received time and corrected time.
  Replay drops old-source, wrong-stage/hand or pre-onset cross-epoch
  events. The physical callback still timestamps **before** the lock.
- [43fe21e](https://github.com/tpepels/piano_teacher/commit/43fe21ef5d2bb9fc300fb5c20cc2803b6371577e)
  moved teaching-effect validation and single-effect progress idempotence
  from `SessionCommands` to the selected lesson owner `TeachingDecisions`.
  `PlaybackTransition.from_effect` now owns the pure start-route mapping.
- [3b7dad5](https://github.com/tpepels/piano_teacher/commit/3b7dad5a0e0901c269bc5dcf87e2cf162b27051b)
  retains approved prepared exposures inside `TeachingDecisions`,
  validated against the *same plan object*, source fingerprint and stage;
  resets that selection on source installation. Direct decided starts
  reject a missing/stale approved exposure rather than using an older
  command's mutable `prepared` slot. The intermediate
  source-identity-owned version was corrected before this checkpoint.
- [e1aefb0](https://github.com/tpepels/piano_teacher/commit/e1aefb041204738318e20070ff465d1bb1a0c045)
  completed explicit original-effect propagation through user command,
  lesson/navigation, timed take and physical playback admission, removing
  `SessionCommands.active` and the nested `executing()` context.
- [a6fe63f](https://github.com/tpepels/piano_teacher/commit/a6fe63f4ebb7d79e48f9821c7d2e7d33e868e654)
  completed reason propagation for interruption and course flow, deleting
  `SessionCommands` entirely. Producers now supply explicit user,
  physical-receipt or automatic `transition` reasons; no second mutable
  action-reason scope survives.
- [46f6a82](https://github.com/tpepels/piano_teacher/commit/46f6a82a2638fff11395883ba038d74171acfd89)
  routes MIDI device scan/reconciliation through an explicit
  `MidiPortsRequested` session event and updates the stale transport
  documentation. Listen re-entry reason is maintained by [b3cf9a9](https://github.com/tpepels/piano_teacher/commit/b3cf9a930292dc5b740af5a8f18f590e2c2eb453).

**Source audit:** All **77 extant Python application modules** were
read and scanned for `SessionCommands`, `ControlDispatcher`, old
`session_commands`/ `control_dispatch` references and removed nested
`executing()` calls. **No executable reference remains**; the sole
outdated header was corrected in `playback_session.py`. This is static
source evidence, not executed acceptance. The composition root now has
**61 constructor assignments matching the baseline's uppercase-class
constructor convention**, compared with 63 earlier. The exact count is
descriptive, not an architectural success criterion.

**Additional A1 source implementation:** [90b69ab](https://github.com/tpepels/piano_teacher/commit/90b69ab64043b5f5b70cb06f20b95eea1b45c440)
moves the bounded, typed immediate-transition queue into
`PracticeSession._advance_tick`. `PracticeTimeline.update_transition`
and its complete-take/feedback helpers return a follow-up decision;
the private `_followup_requested` state and `settle_transitions` loop
were removed. At most 16 successive follow-ups are accepted, retaining
failure pause/notices. Only after the final settled transition does the
session replay source-bound MIDI and publish once.

**A1 exit still open:** Complete source/state aggregate ownership,
explicit take-result/settlement transaction contracts and effect
atomicity, with actual MIDI, Stop/queued Stop, stale/failure
receipt, Pause/Resume, navigation and source-change journeys.
Core Python, desktop fake MIDI, Godot, embedded native execution,
packaging and physical keyboard behavior have **not been run on this
revision**. A1 stays **IN PROGRESS**; A0 exact-HEAD verification is also
open. The last successful CI is historical evidence only, and no
GitHub Actions run was triggered.

### A1 physical callback and Stop fault-boundary checkpoint — 2026-11-22

**Production changes committed directly to `main`:**

- [c5c5a93](https://github.com/tpepels/piano_teacher/commit/c5c5a93106197dc20c6b62c57cbda81f294c689a)
  introduces a **committed, immutable MIDI arrival epoch**, atomically
  replaced after each session event. The device callback samples it
  before waiting for the application lock. Source, engraving revision,
  lesson stage/hand, transport ID and the `AttemptSettlement`
  cancellation generation must match at dispatch. Different transport
  epochs may accept an original note only during a same-source
  automatic continuation whose corrected hardware timestamp is at or
  after the newly authorized onset.
- [7aa4971](https://github.com/tpepels/piano_teacher/commit/7aa497110e9a40a82769c4eb84b81a50f37ef32c)
  copies each callback MIDI message before deferring it. Obsolete notes
  cannot be graded or execute shortcuts, but stale note-offs still
  release shortcut suppression and hardware observation remains accurate
  for the same connected device.
- [97a855a](https://github.com/tpepels/piano_teacher/commit/97a855aa83cce1f6639fb08236e93792a182d4e6)
  adds the original **physical device identity** to the same arrival
  epoch and to deferred messages. Late callbacks from a disconnected
  keyboard cannot increment the replacement device's input counters or
  release its currently suppressed shortcut keys.
- [704a317](https://github.com/tpepels/piano_teacher/commit/704a317e9088d4cc3f1a8e3e5b0a6421a53f15a9)
  fixes an actual regression in the prior session-owned transition
  queue: ordinary/recovery tick branches must initialize
  `followup=False` before returning. Without it, those branches would
  raise `UnboundLocalError` every tick.
- [4d39bd6](https://github.com/tpepels/piano_teacher/commit/4d39bd604ba4e0316e3c296c1b90dd863f0c22cc)
  makes the native `settings.update` public settings reply atomic with
  the accepted mutation, avoiding a newer MIDI shortcut change between
  update and response. Direct/headless MIDI calls receive a real
  timestamp; missing timestamps fail closed across transport epochs.
- [ae99ddb](https://github.com/tpepels/piano_teacher/commit/ae99ddbf4957d3025de236657112f40a2f90c776)
  makes explicit `ui_stop` a one-way Stop independent of the renderer
  projection. Stop, Pause and Resume no longer invoke an unused
  curriculum policy decision before executing the transport control.
  Godot's existing `CommandRequestState` still retains Stop when
  another request is pending; **native-worker latency while busy on
  source import remains an open verification/architectural issue**.
- [22a978c](https://github.com/tpepels/piano_teacher/commit/22a978cee9d2fd8ee1deff7e6c43cae6eba6530f)
  and [0cdf1fe](https://github.com/tpepels/piano_teacher/commit/0cdf1fe58dc8b1c73f7c041ffc415dc1aea05cfa)
  make Stop **fail closed on guided-evidence snapshot or durable
  interruption failure**. Physical playback authorization is invalid
  before persistence; if persistence fails, the backend marks the take
  no longer running, clears deferred MIDI and freezes the visual
  transport. Its recorder and unsettled evidence remain available for
  the original transaction to be retried rather than silently
  awarding progress or discarding data.

**Verification and scope:** The source-level audit included the committed
16 Python test modules' direct constructors of `MidiInputFacts` and
event contracts; the newly appended fact fields have defaults. That
does not establish their execution or correct MIDI timing. Neither
Python/Godot runtime, embedded desktop fake MIDI, native packaging, nor
physical keyboard acceptance was run on this HEAD. No new tests and no
GitHub Actions runs were triggered.

**A1 remains IN PROGRESS:** The complete event/result aggregate and
durable effect sequencing still cross into A2's settlement responsibilities;
the one-worker queued Stop needs exact-state verification (especially
during long source imports), as do Pause/Resume, stage/window changes,
lost/stale physical receipts and the native fake-MIDI journeys.
A0 exact-HEAD verification remains outstanding. Continue A1/A2
production consolidation; do not certify these changes based on source
inspection alone.

### A1 — One PracticeSession transaction/event coordinator

- [x] Implement one serial event processor and session aggregate on the
  existing in-process worker, monotonic clock and short application lock.
  Define typed gesture, MIDI, tick, score-ready, source, admission, failure,
  reconciliation, take-result and settlement events and explicit effects.
- [x] Move all public and native action entrypoints through this boundary.
  Resolve UI eligibility against the **fresh current state**, with complete
  source/revision/attempt/take identity; preserve public operations during
  migration without leaving a second runtime router.
- [x] Replace fragmented manual command routing, context managers and
  callback-driven effect ordering with one transaction coordinator that
  executes domain decisions without duplicating them.
- [x] Replace PracticeTimeline's nested/recursive transition publication
  emulation with an ordered in-worker event queue, bounded cycle detection,
  and **one state publication per committed event**.
- [x] Migrate every active caller and delete superseded action routing,
  nested command orchestration and duplicated mutation paths in this phase.
- [x] Verify actual invalid/stale commands, queued Stop priority, navigation
  suspension, source changes and real fake-MIDI/tick transitions.

**Exit A1:** All session state changes enter through the one event boundary.
No parallel command router, active legacy engine or recursive handoff remains.

### A2 implementation checkpoint — 2026-11-22

- [19c678c](https://github.com/tpepels/piano_teacher/commit/19c678c311a5798cb3d301e36ffe8d1dca95a0a7) retains the prior take's visible note feedback until its selected continuation succeeds.
- [d0e0acf](https://github.com/tpepels/piano_teacher/commit/d0e0acf6f4d965f1db7d5e8d405c11215172a0c9) and [318886c](https://github.com/tpepels/piano_teacher/commit/318886c8730923731193cbe86a74d5ce447aeca5) add a receipt-keyed `effects_applied` checkpoint to `AttemptSettlement`: a failed continuation retries its durable receipt without adopting the same stage/score a second time.
- [8910f08](https://github.com/tpepels/piano_teacher/commit/8910f084574a2f3d6e684aa473a2bbf68e433df2) and [0c6e0a5](https://github.com/tpepels/piano_teacher/commit/0c6e0a526d92bedced261655f8fa31a17e6a9b6d) introduce an immutable, source-bound `TakeResult` for completed full/focused takes: run/session/attempt, source/revision/stage/hand, course and cancellation epochs, passage/BPM, original MIDI onsets/releases/press IDs and graded original-note observations. Persistence retries use the original frozen `PlayedNote` tuple and reject changed source/window/BPM.
- [76f06f8](https://github.com/tpepels/piano_teacher/commit/76f06f8249f083097e21d0f770cea26c3411f979) extends the same `TakeResult` to rolling recovery. [70b8d74](https://github.com/tpepels/piano_teacher/commit/70b8d741693692b3ba1c86924cad3d6ffdb1737f) prevents resealing an already durable rolling receipt. [67c6af2](https://github.com/tpepels/piano_teacher/commit/67c6af2acb9a83913d79b5d82b6620954feff8f9), [6a28650](https://github.com/tpepels/piano_teacher/commit/6a28650bc0e7d3703b89b3add599aa6cc1c35e66) and [d95fc79](https://github.com/tpepels/piano_teacher/commit/d95fc7912459942fa4f9d710ec8f453721984c1d) retain the old graded tempo, score identity and feedback if a committed slowdown needs presentation retry.
- [c9ab312](https://github.com/tpepels/piano_teacher/commit/c9ab312d83912bafa313fa8568ca135c15d6e7b6) merges all `PostAssessmentEffects` completion and presentation responsibilities into `CompletionContinuations` and **deletes** the previous coordinator/file. All 76 current application modules and 16 Python test modules were inspected for its former references; none remain.
- [63347d3](https://github.com/tpepels/piano_teacher/commit/63347d341e1ad12281bcc7eb2c2dedbe53bca659) also prevents nested typed MIDI shortcut events from publishing an intermediate source/take epoch before the outer event commits (A1).
- Verified in source: `practice_windows.moving_windows` enumerates each authored measure alone then trailing windows up to four; Practice Flow retains 50% starting tempo and two clean target passes, and preserves the full original final piece. This **has not been executed** on the new commits.

**Additional A2 source integration:** [c9a15bb](https://github.com/tpepels/piano_teacher/commit/c9a15bbf82caee94574b66cf40b2cc419f93e968)
removes mirrored BPM, failure, clean-pass and Free-return counters from
`PracticeFlowCourseSession`. It now owns only a transient
Listen/Free/Tempo `FlowPhase` and projects all counters from
`LearningPlan`, preserving its existing public `FlowState` interface.
[eba9c64](https://github.com/tpepels/piano_teacher/commit/eba9c64a93a40bc4b33bab1c261e5006fca1bb43)
reads that projection under the application lock, and
[719fd33](https://github.com/tpepels/piano_teacher/commit/719fd33f461ca61c76b5cdc24fd6d1ca1d61b348)
keys the transient phase to the *installed LearningPlan instance* so
a different piece with the same window key cannot inherit stale Listen,
Free or Tempo state.

**A2 remaining:** Resolve any residual duplicate recovery/settlement
ownership and make the course policy/settings explicitly scoped without
changing persisted alternative Coda/Fukuda/warm-up behavior. Then verify
actual failed-persistence, Stop/source-change and physical/MIDI lesson
journeys. **No Python, Godot/native, package or physical keyboard tests
have executed on this HEAD.** A0 exact-HEAD and A1 acceptance remain
open; GitHub CI was not triggered.

### A2 durable receipt and continuation effect checkpoint — 2026-11-22

**Integrated on `main`, after the canonical Practice Flow progress change:**

- [04ab481](https://github.com/tpepels/piano_teacher/commit/04ab48106dd1d1488a7c8ff2c74b3d812d990d74)
  reuses the **original durable receipt** for focused/performance take
  presentation retries. The original `TakeResult` is not regraded,
  resealed or granted additional mastery after its stage already advanced.
- [20fc805](https://github.com/tpepels/piano_teacher/commit/20fc805bc6de11aea8d9d851098ac64eb550b48d)
  strengthens this replay gate: current run/session/source, physical
  transport and cancellation identity must match, as must the exact
  acknowledged authority/course revision advancement and previously
  committed canonical lesson progress. Different source, take, learner
  or further progress cannot inherit the original receipt.
- [6936fdc](https://github.com/tpepels/piano_teacher/commit/6936fdc75d04a8ba4f992230f595ad4be073347d)
  makes `CompletionContinuations.dispatch_effect` acknowledge an
  exact typed successor effect only **after** the complete dispatch
  succeeds. A replay of the same decided effect is a no-op; a conflicting
  effect under the same identity is rejected. A failed physical
  continuation start is still retried with its original receipt.
- [01b6d43](https://github.com/tpepels/piano_teacher/commit/01b6d435771331c33a4bd1de555a0410b70d873e)
  requires a durable receipt and installed source effects before
  `finish_publication` can mark a teaching result published.
  [d4bb831](https://github.com/tpepels/piano_teacher/commit/d4bb831e8c9928f0e856fe8c0c8b9b9eec4e1899)
  rejects superseded decisions at settlement and enforces one-way
  receipt phases: `settled → effects_applied → published`.
- The `practice_flow.py` module contract now identifies the pure
  reducer as policy and `LearningPlan` as the durable owner of
  counters/BPM. This removes a misleading legacy ownership claim;
  no lesson rule or stage sequence was changed.
- [e2360ec](https://github.com/tpepels/piano_teacher/commit/e2360ec5c435f7105b9d8022e77d315d1c08fac3)
  removes `PracticeFlowCourseSession.settle`, a second public entrypoint
  accepting caller-owned BPM/mastery/failure counters. The sole
  `settle_decided` entrypoint now reads canonical `LearningPlan`
  progress and invokes the existing pure `practice_flow.settle`
  reducer before storing only the transient source-bound phase.
  The production lesson and completion callers were checked; no
  other call to the deleted public method was found in those paths.

**Scope and open verification:** These are production source changes,
not a current-HEAD runtime acceptance pass. The existing 16 Python test
modules and embedding/build workflow were not executed in this
environment; no tests were added and GitHub CI was not triggered.
A2 still requires focused/final/rolling fake-MIDI failed-persistence
journeys, settlement after Stop/source revision changes, conditional
effect-retry acceptance, course-scoped policy/settings consolidation,
and removal of any remaining redundant recovery coordination.
The policy invariants of four-bar trailing windows, RH → LH → Both,
per-stage Listen → Free → Tempo, original final and Coda/Fukuda and
warm-up course behavior remain obligations for A2 acceptance.
**A2 stays IN PROGRESS.**

**A2 stale-source settlement guard (2026-11-22):** [73282e4](https://github.com/tpepels/piano_teacher/commit/73282e4c79d04d6faa31f1111d272a26f151a375) requires `PracticeFlowCourseSession.settle_decided` to operate on the currently installed `LearningPlan` and an existing projected phase before accepting a decision ID, including repeated receipts. A delayed completion after source replacement can no longer recreate or settle an obsolete course phase. This is source-level integration only; no runtime test was executed. Course-scoped settings, recovery ownership and failed-persistence/source-change acceptance remain open.

### A2 course policy and continuation ownership checkpoint — 2026-11-22

**Source changes on main (not runtime acceptance):**

- `lesson_settings.course_rules(generator_name, warmup=...)` returns immutable,
  selected `CourseRules`. Practice Flow gets its two-target-pass requirement
  from the existing pure reducer, its four-bar cap from `practice_windows`,
  and a 50%-of-target first graded Tempo step after Listen/Free.
  Initial Listen remains at the prepared source tempo. Source-progression, selectable
  Coda/Fukuda and built-in warm-ups retain the previously configured flat
  `lesson_settings.json` values (three clean runs and two-bar source focus
  by default). The flat on-disk tuning format was not changed.
- `teaching_course.CourseState` resolves the clean-pass rule from the selected
  generator. Source segmentation, Practice Flow engraving-stage selection and
  recovery thresholds request their explicit course rules. Manual tempo
  increases use one course-owned maximum, now also published by
  `LearningPlan.maximum_stage_bpm` to the control read model. In Practice
  Flow the + button is disabled at the original target BPM.
- `LearningEvidenceSession` records the selected course-rule snapshot
  alongside the historical generic tuning and original source identifiers.
  Newly recorded rule identities are version-distinct from earlier evidence;
  previous ledger records and saved lesson state are left intact. Historical
  attempts are not silently reclassified as current-rule attempts.
- `RecoveryWorkflows._apply_prepared_recovery` is the one selected-response
  executor for whole-response and remedial preparation, cursor/attempt,
  transport and notice effects. The source-bound response selectors remain
  pure; guided note-isolation and untimed timed-review preparation keep
  their distinct semantics.
- `CompletionContinuations.dispatch_effect` now validates its receipt,
  decision ID, phase, installed source fingerprint, stage and revision
  **before** applying an effect. `AttemptSettlement.commit_full_passage`
  binds a receipt replay to the original run/session, cancellation and
  authority/course revisions, installed stage and already-committed progress.
  Once-applied effects remain one-shot.

**Remaining A2 gates:** Runtime acceptance is outstanding for exact-HEAD
Practice Flow, Coda/Fukuda, warm-ups, failed SQLite settlement, interrupted
rolling takes, Stop/source replacement, stale and lost physical ACK, guided
aid and all saved-session reopenings. The remaining rolling boundary
assessment/continuation handoff still needs a writer/owner audit before
A2 can be closed. No Python, Godot, embedded native, package or physical
MIDI test execution is claimed; CI remains manual-only.

**A2 explicit-retry closure (2026-11-22):** A failed post-commit full
continuation now sets the runtime retry flag without clearing the original
receipt, note marks or selected feedback transaction. The user Start/Retry
action re-enters `CompletionContinuations.retry_failed_publication`,
retries durable/post-commit effects once, and publishes only after dispatch
succeeds. Worker ticks with stopped automatic playback do not retry it
implicitly. `SettledSourceFacts.automatic` comes from the original
`TeachingRouteFacts` instead of the faulted transport's current auto
flag, and an explicit Retry restores the selected automatic course intent
before effect dispatch. The original route is not reselected. New regression
coverage checks the stopped-auto gate and failed-effect feedback retention.
This remains source-level, unexecuted acceptance.

### A2 rolling and failed-continuation retry checkpoint — 2026-11-22

**Implemented on main, not yet runtime-accepted:**

- Rolling `TakeResult` replay now requires the original run, session,
  fingerprint, physical transport and cancellation identity, plus exact
  source revision, selected passage, hand/BPM and the committed authority/
  course epochs. An alternate learner, changed stage, restarted source or
  further progress cannot claim the same receipt.
- Rolling recovery effects are acknowledged individually in
  `AttemptSettlement`, after each accepted action completes. Replays skip
  the previously acknowledged tempo, completed-rest, preparation, streak,
  attempt, notice, withdrawal and cancellation effects. The required effect
  set is determined by the original transition, and rolling decisions follow
  the same `settled -> effects_applied -> published` lifetime as full takes.
  A failed effect retains the frozen receipt for retry; a superseded or
  unrecognized effect is rejected.
- `PracticeTimeline` prioritizes the frozen rolling decision over new
  boundary assessment when an effect failed after boundary advancement.
  The existing manual Retry path also reuses the same frozen rolling take.
- `RecoveryWorkflows` now rejects stale remedial assignments and missing
  active sources instead of silently treating their no-op as successful
  continuation publication. Selected action/deadline validation occurs
  before cursor/transport effects.
- Full-passage post-commit failures now retain their original
  `TeachingContinuation` feedback transaction even after automatic
  playback is stopped or the original deadline withdrawn. Explicit
  Start/Retry re-enters the selected transaction, including its physical/
  source effects, instead of merely resaving progress. Failed effect dispatch
  preserves original marks and does not publish the receipt; successful
  replay publishes once without a second assessment.
- Added `tests/test_rolling_receipt_replay.py`,
  `tests/test_continuation_effect_guards.py` and
  `tests/test_course_rule_scopes.py` for source/epoch mismatch, one-shot
  effects, failure retention, worker precedence, stopped-auto retry,
  post-commit publication and alternative/warm-up rules.

**Remaining A2 acceptance:** Run the exact-HEAD Python suite and fake-MIDI
full/focused/rolling traces, inject real SQLite failure before and after
durable commit, verify Stop/source-change and physical admission/ACK loss,
saved-session reopening, Coda/Fukuda and warm-up behavior, Godot embedded
execution and real keyboard/audio. Individual effects are acknowledged only
after their call returns; if an external effect partially mutates then raises,
the corresponding physical reconciliation must still be verified in A3.
No passing runtime tests or CI completion is claimed, and GitHub CI was not
triggered. **A2 remains IN PROGRESS until these gates pass.**

### A2 — Unified lesson, assessment and durable settlement

- [x] Give the lesson domain one course/window/hand/step, BPM, mastery and
  recovery authority. Reuse pure Practice Flow decisions and real-source
  Coda/Fukuda generators; eliminate mirrored course-phase and alternate
  progression state for the **same** selected course.
- [x] Produce a typed immutable TakeResult with original MIDI note IDs,
  timing and release evidence, source, hand, passage and attempt identity.
  Only the selected lesson policy decides repeat/faster/slower/Free/aid/
  next window/final completion.
- [x] Integrate rolling checkpoints, complete-take settlement, feedback,
  recovery, automatic continuation and ledger writes in **one ordered,
  atomic and idempotent path**. Handle interrupted/failed persistence and
  partial take cancellation without double mastery or lost events.
- [x] Replace redundant Exposure*, Recovery*, Completion*, TeachingContinuation
  and settlement orchestration only after migrating every active rule and
  effect; retain useful pure policy, storage and source-generation components.
- [x] Preserve the practice-flow contract exactly: each new authored bar
  alone then trailing windows to four, RH → LH → Both, own Listen → Free →
  Tempo, 50% initial tempo, two target clean passes, held-note tails, graded
  onsets with optional hold grading, floor-failure Free recovery, explicit
  source-bound aid and whole-original-piece final.
- [x] Make settings explicitly course-scoped; eliminate conflicting generic
  defaults without changing supported alternative/warm-up behavior or
  breaking existing persisted sessions.

**Exit A2:** One take result yields one lesson decision and one durable
settlement. No other owner can independently grade, advance or select tempo.

**Follow-up A3 epoch reconciliation:** Idempotent `playback.present`
replies are accepted only for the same active source fingerprint,
stage, revision, hand, end-beat, physical transport ID **and mode**.
Terminal `complete`, `failed` or `idle` cannot resurface an old
authorization. The existing bounded lost-ACK reconciliation remains
in force; `tests/test_physical_present_epoch.py` also covers the
terminal/mode cases. Source-inspection only, no actual physical ACK
fault injection has run on this HEAD.

**A4 identity correction:** Both current and future bundles now use
`music.source_note_id(note,index)`, the same canonical original/legacy
note-ID rule used by `display_envelope` and native semantic notation.
This keeps supported sources without explicit IDs readable while
rejecting duplicate/mismatched graded attack identities.

### A3–A6 integrated development checkpoint — 2026-11-22

**A3 — physical receipt replay hardened (source integration):**
`PlaybackCoordinator.present()` now requires an idempotent previously
authorized receipt to remain attached to the exact current source
fingerprint, stage, engraving revision, hand, sounding end and
`transport_id`. A stale repeat `playback.present` cannot reuse a
receipt after its source/transport changes, even before an explicit
invalidate callback reaches the coordinator. Added
`tests/test_physical_present_epoch.py` for same-epoch replay and
stale Stop/source/transport rejection. This does **not** complete A3's
aggregate consolidation, full physical failure reconciliation or
native/audio acceptance.

**A4 — one current/future ScoreBundle production path (source integration):**
`ScoreArtifacts.bundle(ScoreSelection)` compiles one immutable-response
snapshot of authentic native layout, semantic model and source IDs under
the exact fingerprint, revision, stage/window/hand and original-note
identity. It rejects mixed revisions, empty/duplicate IDs and any
disagreement between the selected hand's graded notes and the semantic
active IDs. `ScoreReadServices`, `PracticeEngine` and
`EngineCommands(score.bundle)` expose the same selected source.
`FutureScore` uses the very same compiler and retains its bounded
background lookahead/adoption.

The active Godot `ScoreAssetSession` now requests that bundle once,
checks both halves *before* installing it, and preserves the native
retained-CanvasItem readiness requirement before `score_ready`.
`ScoreAssetQueue` is one request slot, not separate layout/model
requests and retry clocks. The embedded `native_bridge_smoke.gd`
checks real native layout and original semantic notes through that same
bundle. The old `score.native_layout` and `score.semantic` Python
read endpoints remain available to current headless diagnostics/behavior
tests; they are no longer the production native preparation protocol.
Added `tests/test_score_bundle.py` for version/source, original IDs,
read isolation and current-source changes. Same-HEAD Godot execution,
repertoire, fingering corrections and prepared-stage promotion still
need verification; A4 is **not accepted** without those.

**A5 — presentation contract safety:** Python state validation and
its generated Godot counterpart now refuse nonfinite numerical
transport/visual coordinates and nonfinite target beats. The generator
and generated file have matching source changes; the prior
`target has no source_beat` error text remains compatible. Added
`tests/test_state_contract_number_validation.py`. A5 still requires
the complete scene/callback policy audit and one physical score-surface
interface.

**A6 — duplicate native readiness removed:** The active score asset
session no longer owns separate pending flags, semantic-model revision
or retry state. The native diagnostic path reports one
`bundle_pending` fact. No supported course, warm-up or stored-data
format was removed. Other A0 inventory entries, old orchestration
composition and library/persistence migrations still require a full
reachability audit before A6 closure.

**Embedded C++ worker dispatch:** `PianoNative::is_asset_operation`
routes production `score.bundle` to the existing dedicated asset worker
alongside read-only diagnostic scores and learning statistics. Heavy
current-source Verovio and source-model compilation therefore do not
enter the musical deadline worker's operation queue. This still requires
same-HEAD embedded verification.

**Verification and release gate:** All above changes are committed on
`main` but **have not been executed** in Python, Godot, embedded
native or physical MIDI/audio. CI stays manual-only and has not been
triggered. A0–A7 are not falsely marked complete; A7 needs the same
final HEAD for `bash scripts/test.sh --coverage` and
`bash scripts/verify-embedded-production-local.sh`, then the
owner's connected CA49, audible count-in, visual continuity,
Pathétique II (only if provided), repertoire and relocated-package
acceptance.

### A3/A4/A5 source-identity integration — 2026-11-23

**Source changes on `main`, not native/runtime acceptance:**

- [`7e61b3d`](https://github.com/tpepels/piano_teacher/commit/7e61b3dd6acda2cb7933a81493392b4e948a1af8)
  binds the selected `stage_key` to the same committed command/frame
  projection, current native score requests, installed renderer readiness,
  and physical intent validation. A response for another stage or hand
  now fails closed even when fingerprint/revision coincide. Prepared renderer
  promotion also disconnects obsolete retained-ink notifications without
  erasing old physical ink.
- [`5d0caac`](https://github.com/tpepels/piano_teacher/commit/5d0caacb90a8f38fdfb4cd8e930c2e5c55a43e9f)
  adds this identity to the authoritative Python snapshot schema and its
  generated Godot copy, with contract version 6. The loaded snapshot
  requires `stage_key`; this is a single application source fact,
  not a separate Godot learner-phase decision.
- [`4d5ae3f`](https://github.com/tpepels/piano_teacher/commit/4d5ae3ffe8507f5fd413bd218a684d55ecef484c)
  rejects idempotent `playback.present` replay after same-revision
  BPM, passage-origin or tempo-map changes. The existing source, mode,
  transport, stage and terminal-status checks remain in force.
- [`225df0e`](https://github.com/tpepels/piano_teacher/commit/225df0ef43230d34b882c1a0b0e34b5b0a446d69)
  removes the native prepared-score fallback that treated a matching
  lesson ordinal as equivalent to the selected source identity. Preloaded
  stage promotion now requires the committed `stage_key` with matching
  fingerprint, revision and hand even before a playback intent exists.
  Manual renderer handoffs use the same installed score identity, so
  a changed stage/hand cannot clear or reuse the old renderer on merely
  equal fingerprint/revision. Exposed old ink remains retained.
- [`cf61ea8`](https://github.com/tpepels/piano_teacher/commit/cf61ea827b5d1ecc14fb67f463eafd910326b4fd)
  places structural ScoreBundle validation in the existing
  `NativeScoreAssets` boundary, shared by current score loading and
  prepared future loading. Both now require a ready source identity,
  matching layout/model revisions, nonempty unique original MIDI IDs
  and semantic active IDs drawn from that source. The future path
  rejects malformed bundles *before* mutating its hidden renderer;
  the current path also checks the committed exact stage and hand.
  Python `ScoreArtifacts.bundle` remains the sole compiler.

**Verification:** Source-contract counterpart fields and native admission
guards were inspected on the committed files. No Python/Godot tests,
embedded native execution, packaging or real MIDI/audio verification
has run on these commits. The exact-HEAD generator check
(`python3 scripts/generate_state_contract.py --check`), core behavior suite,
Godot score loading and stale-response/future-stage promotion, interrupted
physical receipt/reconciliation and standalone packaging remain open.
GitHub Actions remains manual `workflow_dispatch` only; none was triggered.
A3–A5 are still **IN PROGRESS**, and A6/A7 are not accepted.

### A2/A3 further source integration — 2026-11-23

**A2: immutable evidence, selected continuation and failure-safe settlement**

- [`0654e7a`](https://github.com/tpepels/piano_teacher/commit/0654e7ae70036f3bd6a70b55ce6b31decd5b6f5d)
  rejects unrelated teaching events while a different durable receipt
  awaits publication, accepts an already `effects_applied` rolling retry,
  and binds full settlement replay to the original physical transport epoch.
  [`25b0059`](https://github.com/tpepels/piano_teacher/commit/25b0059aaeac9045e451addfdda9ddb83789705a)
  checks focused/perform replay against the **installed successor** progress
  rather than incorrectly requiring the pre-settlement BPM/hand/stage.
- [`4091a6a`](https://github.com/tpepels/piano_teacher/commit/4091a6a586d0204a314f281865f9b1266bbcaf57)
  and [`77089d0`](https://github.com/tpepels/piano_teacher/commit/77089d0144dfc7ab302e8f79a5437dfca396e469)
  make partially failed rolling publication stop its old graded take,
  retain the original receipt and prior per-effect acknowledgements, and
  require explicit Retry rather than regrading an advanced boundary.
- [`9cda46e`](https://github.com/tpepels/piano_teacher/commit/9cda46e5dd627dcd0f7fa5c7c5b305b3064d93d9)
  introduces a serialized, narrowly scoped durable-publication lease. A
  selected guided/new-source continuation may legitimately call ordinary
  Stop/open-take cleanup inside the same accepted effect; this no longer
  silently destroys the predecessor's settled receipt before the selected
  effect can be acknowledged and marked published. Ordinary external Stop
  still invalidates the receipt. The existing continuation fixture was
  adjusted to that production contract in
  [`106fcae`](https://github.com/tpepels/piano_teacher/commit/106fcae027f4121be4308996c05a127650e8c4aa).

**A3: one musical lifetime and one physical authorization protocol**

- [`7e53c0b`](https://github.com/tpepels/piano_teacher/commit/7e53c0b43c0e90b6f7907f7ffae5553464429809),
  [`e5e3469`](https://github.com/tpepels/piano_teacher/commit/e5e3469d057882e583681a4f879b931b6a3e67d3)
  and [`2e0f2a7`](https://github.com/tpepels/piano_teacher/commit/2e0f2a7b998621ab5356021d0baf2a2f3d56eeba)
  reject stale present ACKs after completion, changed tempo/rate maps,
  invalid Resume transport origin, or a no-longer-running paused take.
- [`24af812`](https://github.com/tpepels/piano_teacher/commit/24af8129333e95acea271c87ab1117774a18db63),
  [`9c50c04`](https://github.com/tpepels/piano_teacher/commit/9c50c04405d63d573d5b6ced4d0d81a59f6d1e38)
  and [`9bd88de`](https://github.com/tpepels/piano_teacher/commit/9bd88de86cf90d016d26bcda143da1f219223955)
  require the native status reconciliation after a physical present reply
  and compare the entire current source, stage, transport, BPM/rate map
  and deadline before permitting visual motion and audible count-in.
  [`e1665ac`](https://github.com/tpepels/piano_teacher/commit/e1665accbc43652ba118f32e7de4f0e31b21a00d)
  marks physical score loss terminal before potentially failing cleanup.
- [`64df41c`](https://github.com/tpepels/piano_teacher/commit/64df41c7063d1f6dccada5975ddc784088cd0dc6)
  and [`ffea0a8`](https://github.com/tpepels/piano_teacher/commit/ffea0a8fafbf78f38904e29292739858121198d3)
  reconcile the physical state when a transition tick fails instead
  of leaving an old `playing` receipt next to a paused musical clock.
- [`8daed69`](https://github.com/tpepels/piano_teacher/commit/8daed6947a24bfa12bdfe0c705f0bb19e0803921),
  [`0d220da`](https://github.com/tpepels/piano_teacher/commit/0d220da38b8906b984d834e2e52d06e55dc2d57d)
  and [`15be47b`](https://github.com/tpepels/piano_teacher/commit/15be47b8087350413ab82ade709e901bafd3bf41)
  remove the separately ticking coordinator's `playing/count_in/paused`
  phase writers. Both GUI snapshot and physical status now derive these
  phases from the **same fresh session/clock observation**.
  [`8d91702`](https://github.com/tpepels/piano_teacher/commit/8d91702506feac95250e1a0fbf1b68ecdc8a3aae)
  additionally fails closed if the live source no longer matches the
  previously authorized segment.
- [`9ffe206`](https://github.com/tpepels/piano_teacher/commit/9ffe206af3f19925a80a0ea2889a6fda8d9ac585)
  and [`1049ef0`](https://github.com/tpepels/piano_teacher/commit/1049ef0363a2127ff915026ebddaae2c882d1d50)
  co-locate live running/paused state, count-in meter and duration,
  physical transport epoch and musical origin in `VisualTransport`.
  `PlaybackSession` delegates these fields; mode, continuation intent
  and graded-exposure policy remain explicit.
- [`ae61a2d`](https://github.com/tpepels/piano_teacher/commit/ae61a2db3b9d22af555d9b17713bd51b5154284a)
  and [`ba42b07`](https://github.com/tpepels/piano_teacher/commit/ba42b070153019f5292a400e36e24d9411388de7)
  make `PlaybackCoordinator` the sole holder of a paused/unarmed
  physical intent. Resume consumes it once and checks source/stage/hand/
  BPM/rate map/transport epoch; stale suspended ink cannot fall through
  into an unrelated rest Resume.
- [`dd92275`](https://github.com/tpepels/piano_teacher/commit/dd92275acfc5709e60c327dbf49c28156d97620e)
  removes the redundant lesson command installation from
  `TransportActions` Start/Restart. The authorized `TimedPlayback`
  boundary now installs its already-selected decision once.
  [`add6f0d`](https://github.com/tpepels/piano_teacher/commit/add6f0d1c7f6a3cf55aeb82e8f0d1525152cb661)
  and [`bedd69d`](https://github.com/tpepels/piano_teacher/commit/bedd69d091d29776422eb9b1322b8e6b9aa5cf6f)
  update the *existing* physical receipt fixture to actual production
  source/tempo/transport-origin facts, without adding scenarios.

**Exit evidence and limitations:** All listed source changes are committed
on `main`. Connector-level source inspection confirmed the ownership
changes and the expected source-bound contracts; this is **not** executable
acceptance. The Python core suite, SQLite fault injection, direct fake-MIDI
full/focused/rolling journeys, Coda/Fukuda and warm-ups, saved reopening,
Godot embedded native scenes, package relocation and connected piano/audio
have **not** run against this resulting HEAD. In particular, failure of a
source-install effect after partial application and the new durable
publication lease require executed retry/Stop/source-replacement acceptance.
The remaining transport service constructor graph and physical failed-ACK
recovery also need full same-HEAD integration/acceptance audit before either
phase can be marked accepted. Run `bash scripts/test.sh --coverage` and
`bash scripts/verify-embedded-production-local.sh` on **the same final
commit**; do not reuse historical green CI as verification.

**Status (historical, superseded 2026-11-23):** A2 and A3 had integrated
source corrections; see the executed verification checkpoint below.
No Python, Godot, embedded, package or physical test is claimed, and GitHub
CI stays manual-only; no workflow was triggered.

### A2/A3 executed verification and cleanup — 2026-11-23

**Starting point:** commit `3675d67` was **not green**. Its checkpoint said
no tests had run, and that was correct. Running them found 4 Python failures, 5 Godot
score-readiness failures and a GDScript parse error that prevented three
embedded scenarios from loading.

**Behaviour defect fixed:** after a window/hand was mastered and the next
stage's score was not preloaded, `AwaitSelectedScore` dropped the settled
`next_exposure`. The successor's `score_ready` then failed with "No current
source-bound exposure is ready for playback": the learner could not start
the next hand or the final. The effect now carries the exposure and
`TeachingDecisions` records it when the effect is dispatched.

**Removed (−700 lines, no shims):** a second, unused progression/BPM path
on `LearningPlan` (`apply_result`, `increase/decrease_tempo`, `bpm_after`,
`set_bpm`, `set_practice_bpm`, `select_step`, `jump`,
`refresh_from_feedback`, `revisit_source_errors`). Every learner change now
goes only through the pure `teaching_course` decision and
`apply_teaching_progress`. Also removed: the unused `CalibrationRequested` event (calibration uses
the `practice.command` route), the unused Fukuda DTW mistake detector,
timed-assessment/constant-tempo prototypes, a barline alias, around 25 other
definitions with no reference in Python, Godot, native code, tests or
scripts, and the imports they left behind.

**Tests adjusted to current behaviour (no new scenarios):** contract v6;
the suspended intent lives in `PlaybackCoordinator`; the readiness scenario
uses the single `score.bundle` request; the source-progression tools test
drives the production `manual_progress` decision.

**Executed on the final code (software only):**

| Check | Result |
| --- | --- |
| `bash scripts/test.sh --coverage` | 235 Python passed; Godot syntax and all 5 behaviour scenarios 0 failures; coverage 76.0% lines / 56.6% branches (informational) |
| `bash scripts/verify-embedded-production-local.sh` | PASS on `2caac43`, including real-scene synthetic MIDI, lost reserve/present ACK recovery and the relocated package. Only dead locals and imports changed after that. |
| SQLite fault probe (scratch, not committed) | The progress write fails on the mastering take: plan and SQLite unchanged, no mastery, "Could not save the assessment … Retry". Retry (`restart`) replays the retained graded take once: one mastery, then the final at 50%. |

**Remaining A2 blockers:**
- After a failed save the result stays pending, so the phase is `feedback` and the
  **primary control reads "Pause"** while the message says Retry. The Retry
  control is enabled and correct. Owner decision needed at the piano.
- Fault injection during *source installation after partial application*
  and Stop/source replacement during the durable publication lease are
  still unexecuted.

**Remaining A3 blockers:** `PlaybackSession`, `PlaybackCoordinator`,
`VisualTransport`, `TransportTiming` and `TimedPlayback` remain separate
classes. Audit: the epoch/count-in fields are stored only in
`VisualTransport` and written only by `PlaybackSession`, so there is no
competing writer. Merging the classes is still open and needs piano
acceptance.

**Physical acceptance:** none. Connected-piano MIDI, audio and visual behaviour has
not been tested. A2 and A3 stay **IN PROGRESS**. GitHub CI remains manual-only.

#### Continuation — later 2026-11-23 (final software HEAD `bbb96ba`)

**Play/Pause:** the primary control shows **Pause** only while learning or
playing is running or automatically scheduled (take, count-in, Listen,
Free, scheduled continuation, admission) and **Play** otherwise, including
after a failed save and after the piece is mastered. Godot only displays
the backend projection.

**A2 defects fixed (production path):**
- `ProgressRepository.save` wrote the current stage BPM into the plan
  (`stage_tempos`), a second writer of lesson state. After a durable save
  whose next-stage installation then failed, Play could never replay the
  committed receipt and the learner was stuck until Stop. Persistence no
  longer edits the plan; Play now continues from the same saved result.
- Recovery messages named a Retry button the Flow screen does not show and
  said "Could not save" when progress had been saved; they now state what
  happened and point to Play.
- A restored clean-pass streak was clamped by the generic three-pass
  default instead of the course's own rule (Practice Flow: two).

**A3: one transport.** The native bridge always enabled presentation, but
a headless start/timing path (presentation flag, headless score_ready
start and timing, default count-in, headless Listen start,
`score_queue_next` projection, direct `PracticeEngine.start`, headless
rewind/decided starts, reuse-announced Resume) remained for the Python
fixture only. It is removed (contract v7; C++ bridge call removed). Every
Python journey now reaches takes through Listen, Free and reserve →
present like the desktop. Correction: the first "next hand cannot start"
fix of this session was in that headless path, not production.

**Owners after this work:** `VisualTransport` (musical timeline facts,
written only by `PlaybackSession`), `PlaybackSession` (mode, automatic
intent, awaited score, pause context) and `PlaybackCoordinator` (physical
intent/receipt ledger) hold distinct facts; `TransportTiming` and
`TimedPlayback` are stateless (timing arithmetic only in
`MusicalScheduler`). No transport fact has two writers.

**A6 progress:** about 1,600 further lines removed (unreferenced Python
and 39 Godot functions, the headless transport) and
`docs/architecture.md` now describes only the live architecture
(2,600-line checkpoint log retired to Git).

**Fault probes executed (scratch, not committed):** failed save on the
mastering take (rollback, Play replays once); failure while installing
the next stage after a durable save (Play continues, mastery once); same
with Stop; failed save without a stage change; opening other music during
a failed save (unsaved take discarded, reopen resumes the saved window);
completing the whole course (Piece mastered, Play offered).

**Same-HEAD verification on `bbb96ba`:** `bash scripts/test.sh --coverage`
235 passed, Godot syntax and all 5 behaviour scenarios 0 failures,
coverage 75.6% lines / 56.2% branches (informational);
`bash scripts/verify-embedded-production-local.sh` PASS: native build,
real-scene Play/Pause/Resume, synthetic-MIDI transitions, lost reserve
and present ACK recovery, Moonlight navigation, all 16 repertoire pieces,
relocated package.

**Remaining structural items (not required by the exit criteria;
deliberately left because each is a large refactor with regression risk
that only piano acceptance can judge):**
- A2: Exposure*, Recovery*, CompletionContinuations and TeachingContinuation
  remain separate collaborators around the one settlement receipt.
- A3: the three transport owners above are separate classes rather than
  one aggregate. They hold distinct facts; merging them is an owner decision.
- A6: the flat 66-service composition graph is not regrouped.
- A0/A1 acceptance write-ups were not revisited.

**Owner piano checklist:** Play/Pause label in every state; next hand and
final start after mastery; one-bar repeat and count-in timing; Pause/Resume
during count-in and playing; lost-ACK behaviour on real hardware;
storage-failure recovery message (optional, by making the data directory
read-only); saved reopen; audible metronome/voice; visual continuity.

#### Continuation 2 — 2026-11-23 (final software HEAD `339a4bc`)

**Additional defects fixed:** six storage-failure paths froze the
timeline by pausing `VisualTransport` directly, so grading was not
frozen (a key released during the failure could be graded as a long
hold) and the evidence phase was not recorded; `PlaybackSession.
freeze_after_fault` now owns this with the same freeze as Pause. Fault
instructions ("Check storage … then Resume") stayed on screen after a
successful Resume; `SessionNotices.fault` now clears them on Resume. One
more instruction named a Retry button the Flow screen does not show.

**Removed:** `ExposureInstaller` (folded into `ExposureWorkflows`), 25
unused `PracticeEngine` state mirrors (including setters that wrote
notices around the event boundary), three uncalled diagnostic operations
(`exercise.diagnostics`, `fingering.status`, `hardware.diagnostics`) and
their helpers. The documented `performance.diagnostics` is kept.

**Verified by inspection (evidence for the ticked items):** every
mutating `PracticeEngine` entry enters `PracticeSession.apply` (reads take
the lock); the transition loop is an ordered, bounded queue; Stop has
queue priority over suspend/Pause in `command_request_state.gd`; current
(`score_asset_session.gd`) and successor (`score_runway.gd`) scores both
use `ScoreArtifacts.bundle` and `NativeScoreAssets.bundle_error`; Godot
issues practice commands only for user gestures and infrastructure ACKs;
Pause sheet, Lesson Path and step selector take enablement from backend
`controls` / overview availability. Probe: a mid-take checkpoint storage
failure freezes with Resume offered; Resume keeps the same take with a
full count-in, the checkpoint succeeds on retry, and the next take starts.

**Same-HEAD gates on `339a4bc`:** `bash scripts/test.sh --coverage`
235 passed; Godot syntax and 5 behaviour scenarios 0 failures; coverage
75.7% lines / 56.3% branches. `bash scripts/verify-embedded-production-local.sh`
25 PASS (native build, real-scene Play/Pause/Resume, synthetic MIDI
transitions, lost reserve/present ACK, Moonlight navigation, 16 repertoire
pieces, relocated package); `PENDING NATIVE_PATHETIQUE_II_SOURCE` because
`PIANO_PATHETIQUE_II_MIDI` was not supplied (not counted as a pass).

**Still open (owner decision or large refactor; none blocks an exit criterion above):**
- A1 item 3 / A2 item 4: the durable-publication lease and two effect
  vocabularies (take-completion string effects vs settled typed effects)
  remain; unifying them touches every alternate course's settlement.
- A3 items 1–2: three transport classes with distinct facts and one
  writer each, not one class.
- A4 item 2: fingering correction keeps its own preparation path; item 4
  needs visual acceptance at the piano.
- A5 items 2 and 5: no consolidated native score-surface interface;
  native audit was function-level (39 dead functions removed).
- A6 items 1–4 and 6: the flat composition graph (65 services) is not
  regrouped; presentation still mixes projection and score motion in
  `SessionReadModels`/`ScoreStatePublisher`.

#### Continuation 3 — 2026-11-23 (final software HEAD `7618737`)

**Changes:** `CompletionContinuations` now applies every take consequence
(focused/performance and settled full-passage); `PracticeTimeline` only
detects completion, and an unknown consequence fails instead of being
treated as a full passage. `PlaybackSession`'s transport views are
read-only, so only it writes timeline facts. The composition root runs
six named, ordered stages with unchanged wiring. docs/architecture.md now
maps every operation/callback to its event, lists the lock-only reads,
and justifies each remaining structure.

**Decisions recorded (owner may revisit):** A3's "one aggregate" is met as
three classes holding disjoint facts with one writer each, not one class;
A2's two completion vocabularies remain (immediate vs successor-boundary
settlement) behind one applier; Recovery/TeachingContinuation stay as
distinct roles; A0's audit tables are superseded by the generated live
map in docs/architecture.md.

**Verified by inspection:** fingering correction re-enters the same
revision-keyed `score.bundle` lifecycle; the snapshot read path does not
mutate state; Godot drives one score surface (`view.gd`) through
`ScoreAdmissionGateway`; no runtime compatibility branch outside the
persistence load paths; final re-audit finds no unreferenced Python or
Godot function and only the four native verification harnesses outside
the runtime roots.

**Same-HEAD gates on `7618737`:** `bash scripts/test.sh --coverage`
235 passed, Godot syntax and 5 behaviour scenarios 0 failures, coverage
75.7% lines / 56.3% branches; `bash scripts/verify-embedded-production-local.sh`
25 PASS including 16 repertoire pieces and the relocated package;
Pathétique II PENDING (source not supplied).

**Owner piano checklist:** Play/Pause label in every state (shows Pause
only while learning/playing or about to start automatically); next hand
and final start after mastery; one-bar repeat and count-in; Pause/Resume
in count-in, playing and Free; storage-failure messages and Resume
(optional: make the data directory read-only); saved reopen;
disconnect/reconnect; metronome and voice; smooth scrolling and retained
ink; only the selected bars visible; Coda/Fukuda aid return.

### A3 — Single transport state and physical playback protocol

- [x] Consolidate running, paused, pending, terminal-failure and source
  epochs; musical count-in/rate map; authorized current and future take; and
  receipt/deadline into one transport aggregate. Retain MusicalScheduler as
  the sole musical scheduling policy.
- [x] Migrate all active responsibilities and consumers of PlaybackSession,
  PlaybackCoordinator, VisualTransport, TransportTiming and TimedPlayback.
  Delete duplicate flags, independent time calculations and redundant
  state holders once their full responsibilities are integrated.
- [x] Implement one explicit intent → physical evidence → Python deadline
  reservation → native immutable arm → attested present → authorized start
  transaction, plus typed failure/withdraw/reconciliation transitions.
- [x] Integrate Listen, untimed stationary Free, Tempo, automatic faster/
  same/slower repeats, exact one-bar gap, full-meter count-in, Pause/
  fresh-future Resume, Stop, disconnection, source change, and bounded
  failed-admission recovery in that one model.
- [x] Drive grading enablement, visual epoch/hold, audible count-in/voice
  and cue deduplication from the **same authorized segment**. Preserve
  outgoing ink and existing genuinely authorized rest reuse; eliminate any
  remaining obsolete paused-source reuse or shortened-count-in paths.

**Exit A3:** Every transport state and deadline has one owner and one
explainable receipt, including stale/lost-ACK and failure recovery.

### A4 — One source/revision-keyed ScoreBundle pipeline

- [x] Standardize normal and successor preparation on an immutable
  ScoreBundle containing fingerprint, revision, stage/window/hand identity,
  semantic notes, original note IDs, authentic engraving geometry,
  selected bounds, sounding tails and cache/generation identifiers.
- [x] Use one bounded background preparation/adoption lifecycle for opening,
  navigation, future-stage prewarming, saved resume and fingering correction;
  preserve source generation cancellation, no MIDI tick blocking, and
  expensive Verovio/inference work outside the session lock.
- [x] Replace separate current layout→semantic and future combined request
  protocols with one verified ready/failure contract and adoption path.
  Remove retired duplicate retry queues, source identity mirrors,
  acknowledgements and stale-result fallback logic once migrated.
- [x] Preserve authentic context needed to engrave ties/clefs and only
  display selected measures with full sounding tails; retain prewarmed
  textures, retained ready ink, safe source switching, resize, no viewport
  jump and immutable previously exposed score strips.

**Exit A4:** Every current or prepared future source uses the same bundle,
identity, readiness, retry and adoption protocol.

### A5 — Thin Godot UI and one native physical score surface

- [x] Keep native code responsible only for raw inputs, widgets, source
  renderer readiness, physical availability/queue, visual interpolation,
  sound/cues and navigation display. No Godot learner policy, grading,
  retry tempo, mode or musical deadline decisions.
- [x] Expose one physical score-surface interface over the **existing**
  immutable queue: measure, preflight, reserve, arm, attest/bind, present,
  withdraw unexposed suffix, expire spent ink, report failure. Consolidate
  the gateway, runway and stream-controller orchestration without creating
  a replacement ledger or altering admission safety.
- [x] Make main Practice, advanced Pause, Lesson Path and MIDI shortcut UI
  consume one versioned backend controls/projection contract. Malformed or
  stale state and command replies must fail closed before effect publication.
- [x] Use only authorized epochs and backend hold/target directives for
  visual motion, frozen Pause, Free targets, count-in, notes and audio.
  Retain one smooth forward-only score and draw no extraneous practice bars.
- [x] Audit every active native scene, effect coordinator and callback;
  migrate each live responsibility and delete obsolete policy/adapter paths.

**Exit A5:** Godot owns real physical facts and presentation only; it cannot
select a different practice action, musical time or take verdict.

### A6 — Complete legacy deletion, composition and documentation closure

- [x] Remove every superseded Python/Godot class, facade, callback layer,
  dead policy, duplicate clock/phase, retired projection, request shim and
  compatibility-only runtime branch identified in A0–A5. Trace imports,
  scene references, bridge operations, packaged assets and test callers;
  **zero production dependency** may remain on the retired architecture.
- [x] Simplify the 63-object flat composition graph into cohesive domain
  assembly and narrow ports. Avoid a new service locator, a parallel engine,
  interface explosion or a monolithic session implementation.
- [x] Keep required backwards-compatible migrations **at persistence
  boundaries**, with idempotent stored-state upgrades. Retire supported
  visible features only after the documented owner decision; otherwise
  fully integrate them in the new domains.
- [x] Make presentation state a pure snapshot of committed session facts,
  with no independent command/render phase and action-policy mirrors.
- [x] Update docs/architecture.md with *only* the live architecture; label
  prior implementation history as historical, update development/build
  instructions, delete implementation-shape tests and keep behavior tests.
- [x] Re-audit complete dependency and state-writer closure, constructor
  coupling, callbacks, dead fallbacks and package contents. Compare with
  A0 evidence; justify remaining complexity by a current product constraint.

**Exit A6:** All production paths use the new model; no temporary dual
owner, old/new bridge, obsolete active dependency or runtime legacy creep
remains. Saved user data remains readable.

### A7 — Same-HEAD software verification, then physical handoff

- [x] On the **same final HEAD**, run and fix all failures in
  **bash scripts/test.sh --coverage** and
  **bash scripts/verify-embedded-production-local.sh**. GitHub Actions
  remains **workflow_dispatch only**; do not run CI on commits.
- [x] Exercise the actual embedded Godot/Python scene, fake MIDI clean/wrong/
  missed/late/extra/release paths, Free/Tempo/Listen, Pause/Resume/Stop,
  disconnected/reconnect, lost reserve/present ACK, stale replies,
  failure recovery and saved-progress reopening, with complete outcomes.
- [x] Verify all 16 checked-in MIDI repertoire cases, variable/odd meter,
  full count-ins, timed repeats/empty rest, moving windows, fast/dense and
  sparse notation, sustained tails, exact physical admission, resize and
  preloaded transitions. Require no Godot SCRIPT ERROR and no unacknowledged
  authority or overlapping immutable ink.
- [x] Verify both hold-grading settings, alternate supported courses and
  warm-ups, Coda/Fukuda aid return, persistent history/settings and
  failure-safe data migration. Keep the application responsive during
  background layout/inference and prewarming.
- [x] Verify standalone build, relocated package contents and boot on
  the same revision. Add exact Pathétique II native case only if
  **PIANO_PATHETIQUE_II_MIDI** is actually supplied; do not treat an absent
  original source as a pass.
- [x] Record final SHA, complete passing/failing case results, deleted-code
  ledger, ownership diagram and precise outstanding owner test procedure
  for real CA49/physical MIDI, audible metronome/voice, visual continuity
  and clean-machine installation.

**Exit A7 (software):** The whole agreed software scope is integrated,
retired paths are gone, all current real-path tests and the native/repertoire/
relocated-package gate pass on **one exact commit**. **Separate physical
acceptance remains pending** until performed with the connected keyboard
and speakers, including the original Pathétique source and readability.

### Implementation and reporting rules

1. Work on **main** only. Complete and integrate each phase before marking
   it done. A wrapper added while the old owner still runs does not count.
2. No indefinite parallel architectures, speculative UI state machines,
   network layer, extra scheduler/clock, generated service-locator maze,
   arbitrary file-size target or "architecture shape" tests.
3. A phase is only done when **all** consumers have migrated, old active
   paths are deleted, behavior and error handling are preserved, affected
   real-path checks pass, and the exact commit plus evidence are recorded.
4. Tests should prove visible transitions, physical admission and MIDI
   behavior, not number of files or structure. Full verification is A7;
   focused checks are required as each phase is integrated.
5. Any proposed retirement of still-selectable/saved functionality needs
   an explicit owner decision. Do not leave abandoned code because it
   once solved a problem, but do not guess that a capability is obsolete.
6. Keep V0–V7 software verification obligations and V7 physical acceptance
   distinguishable from A0–A7 implementation progress.

| Phase | Required result | Status |
| --- | --- | --- |
| A0 | Full source/runtime/feature audit and migration/deletion map | **In progress** — file-path inventory, source-traced critical transitions, state-owner and risk maps committed; complete reachability and exact-HEAD run pending |
| A1 | One authoritative PracticeSession and event processing path | **In progress** — event input and return-state atomicity, cancellation/device-bound callback epochs, bounded transition queue and fail-closed Stop persistence integrated; old router modules deleted; native queued-Stop latency, full event/settlement ownership and same-HEAD behavior verification remain open |
| A2 | Unified lesson/assessment/settlement/recovery | **In progress** — frozen full/rolling TakeResult, receipt-keyed focused retries, one-shot continuation effects and enforced settlement→effects→publication phases; Practice Flow progress from LearningPlan; course-scoped policy audit, recovery consolidation and runtime verification still open |
| A3 | Unified transport clock and physical playback transaction | Not started |
| A4 | One immutable ScoreBundle pipeline for current and future sources | Not started |
| A5 | Thin Godot UI and single native physical-surface interface | Not started |
| A6 | All old dependencies removed; simplified composition, docs and migration | Not started |
| A7 | Green same-HEAD software/native/package; physical acceptance handoff | Not started |

## Active roadmap: UI boundary and MIDI transition verification (V0-V7, updated 2026-11-22)

**Status: IN PROGRESS.** The backend-owned transition/action contract,
physical feasibility → deadline → arm → attestation protocol, immutable
native stream, frame-synchronous state projection, fake-MIDI fault journeys
and package build are implemented. The latest complete embedded-production gate passes its real-scene
journeys, all 16 checked-in repertoire sources and relocated package.
The subsequent source cleanup has not yet been independently rerun. No V0–V7 phase is declared physically accepted.
The earlier `PracticeEngine` S0–S7 decomposition remains in place. The
connected-piano problems (Pause/Free motion, unintended neighboring measures
and Pathétique runtime) require repeatable physical MIDI/audio acceptance.

**Objective:** A single, inspectable practice state machine and playback
transaction authority drive the product from opening a MIDI file through
Listen, Free, Tempo, automatic repeat, recovery, final examination and saved
reopening. Godot renders the authoritative outcome, performs the physical
notation reservation, reports geometry/readiness and emits user or device
intents. It does not independently choose practice modes, actions, tempo,
musical deadlines, grades, mastery, measure windows or retry behavior.

**Initial V0 failure inventory (historical, 2026-11-21):**
- `godot/practice_control_policy.gd` decides Play/Pause/Resume/Retry/Listen
  commands from backend phase strings; `godot/practice_screen.gd` separately
  interprets those strings to enable controls and choose captions.
- `godot/score_admission_gateway.gd` calculates future musical deadlines,
  chooses between resume reuse/fresh reservations and handles retries and
  reconciliation in the presentation process. Some physical geometry must
  stay native, but musical decisions should have one backend owner.
- `godot/presentation_timeline.gd` contains mutable visual rate/hold/epoch
  logic, including an idle initialization rate. The graphical time
  projection needs an explicit authorization contract rather than inferred
  permission to advance.
- `tests/test_desktop_playback.py` supplies synthetic reserve/present
  receipts. Those tests validate backend responses but cannot establish
  that the real Godot gateway would produce the receipts or display the
  expected score. Existing native journeys cover selected cases, not the
  full successful/failed MIDI state-transition graph.

**Governing contracts:** [practice flow](docs/practice-flow.md) defines
visible behavior, including one-to-four-bar moving windows (whole-piece
final excepted), stationary untimed Free, frozen Pause, real sustained tails,
original MIDI tempo, one-bar count-in/repeats, two target-tempo clean runs,
saved Free reentry and Coda/Fukuda fallback. Preserve one source-note
identity, accepted musical clock, graded take, immutable notation ledger and
durable settlement. No HTTP server, duplicate engine, parallel score,
shadow clock, or fallback application behavior. New layers/interfaces are
permitted where they reduce ownership ambiguity. No arbitrary file-size
limits or architecture-shape tests.

### Required final ownership

| Concern | Sole authority | Godot's permitted responsibility |
| --- | --- | --- |
| Practice state, transitions, hand/window, tempo, aid, mastery, persistence | Python lesson/teaching/assessment owners coordinated through the application boundary | Display selected state and emit raw user intents |
| Available actions and their meaning | Python state machine publishes typed action availability and accepted command outcome | Draw buttons, enabled states and labels from the published model |
| Musical deadlines, count-in, Pause/Resume and transaction lifecycle | Python `PlaybackCoordinator`/`PlaybackSession` with `MusicalScheduler` and the existing transport owners | Supply measured constraints, reserve physical ink, report typed receipts/failure |
| Authored and sounding bounds | Canonical source selection and one `ScoreArtifacts` model | Engrave authentic notation; clip visible measures without truncating sounding tails |
| Immutable queue, geometry and raster readiness | Existing native queue/renderer and physical admission adapter | Inspect actual canvas capacity, atomically reserve/withdraw *unexposed* ink, report exact outcomes |
| Musical grade and physical input admission | Python `MidiIngress`, Recorder and assessment policy | Forward timestamped MIDI, paint authoritative note feedback |
| Visual scroll position | One native projector driven only by authorized epochs/holds from the backend contract | Interpolate and paint smooth forward motion; no independent musical state transitions |
| Saved evidence | Existing Python progress repository and `LearningLedger` | Present a read-only summary |

The backend may propose a deadline only after receiving the native physical
constraints needed to make it feasible. Godot can reject a physically
impossible proposal; it must never silently substitute a different deadline,
practice stage or musical tempo. Unresolved, stale, expired or contradictory
receipts fail closed and produce observable recovery, never invisible
continuation or partial grading.

### Phase status

| Phase | Scope | Status |
| --- | --- | --- |
| V0 | Full transition/ownership audit and reproducible failure witnesses | Source audit extended across native action emitters and display-only state readers; remaining complete graph/witness acceptance and local CI open |
| V1 | Deterministic end-to-end MIDI/Godot simulation harness | Source implemented; real engine MIDI transitions and production Godot fake-MIDI Play/Pause/Resume/failure/repeat/Stop/lost-ACK paths integrated; current-HEAD native execution pending |
| V2 | Canonical transition, action and presentation contracts | Source implemented: source-owned actions, ordered warm-up unlocks, versioned snapshot and explicit native fail-closed validation; local CI pending |
| V3 | Unify graphical admission and playback transaction decisions | Source implemented; one Python deadline, post-arm attestation, bounded failure, immutable native queue, and fresh full-bar Resume contract; current-HEAD native acceptance pending |
| V4 | Single authorization-driven visual timeline and Pause/Free semantics | In progress; backend-owned hold/target directives, frozen idle and frame-stepped Godot checks pass core CI; connected native acceptance open |
| V5 | Strip application decisions out of Godot UI and effect coordinators | Source sweep includes warm-up step/passage and advanced Pause hand gating; course owns eligibility, Godot renders it; current-HEAD native gate open |
| V6 | Exhaustive player-visible transition matrix, CI gates and legacy cleanup | Real MIDI/default-vs-strict release, warm-up locking and native Pause/Stop/fault journeys added; no current-HEAD local gate run yet |
| V7 | Integrated production/package verification and physical acceptance | In progress; full embedded production and packaging passed on 1c1b98e (run 45017492022); final code cleanup and physical keyboard/audio acceptance open |

### Latest verified gates and remaining constraints (2026-11-22)

- **Core CI:** [45017492022](https://github.com/tpepels/piano_teacher/actions/runs/45017492022) passed 147 Python tests, 4 skips, and Godot startup syntax/behavior checks on `1c1b98e`. Existing regression tests were run, not expanded before physical piano acceptance.
- **Native production on `d32cb13`:** [45015311868](https://github.com/tpepels/piano_teacher/actions/runs/45015311868) passed the real production Play/Pause/Resume UI, three real embedded-Godot synthetic-MIDI journeys (normal, lost reserve ACK, lost present ACK), all 16 available MIDI repertoire fixtures and the relocated standalone package. The independent Moonlight Sonata multi-action path still failed when Pause-in-count-in → Resume recalculated an immutable source origin; therefore this run is **failed (20/21)**.
- **Native production on `1c1b98e`:** [45017492022](https://github.com/tpepels/piano_teacher/actions/runs/45017492022) passed all production scenarios: real Play/Pause/Resume, synthetic physical-MIDI transitions, lost reserve/present acknowledgements, the complete Moonlight Sonata retry/Listen/navigation journey, 16 MIDI repertoire fixtures and relocated standalone package boot. The earlier failed `ed9e11b` run ([45016371433](https://github.com/tpepels/piano_teacher/actions/runs/45016371433)) is retained as the source-specific failure witness. The subsequent native-legacy cleanup is unverified until an explicitly requested manual full CI run.
- **Physical acceptance:** A keyboard with real MIDI timestamps, actual speaker/click/voice, continuity under Pause/Resume, selected-window bounds and Pathétique behavior remain unverified. The exact Pathétique II source is absent from the versioned MIDI corpus; the local native verifier accepts an explicit `PIANO_PATHETIQUE_II_MIDI` path for this additional scenario without importing it into Git. Synthetic input and CI cannot certify device/audio latency or readability.

### 2026-11-22 follow-up: meter-aware Resume and native verification observability

- [`0f28568`](https://github.com/tpepels/piano_teacher/commit/0f28568784657f422291b6a179470255dc52a58f): The headless Resume path no longer truncates authored count-in measures above four beats. It delegates to `MusicalScheduler.count_in_beats()` and extends the existing real-engine pause/resume behavior test with a 5/4 meter, unchanged take identity and exclusion of count-in keypresses from grading. The previously integrated physical admission path already requested a full count-in.
- [`6882230`](https://github.com/tpepels/piano_teacher/commit/6882230e400023c9430e32424f04ca499deb3eab) and [`3c4d2f2`](https://github.com/tpepels/piano_teacher/commit/3c4d2f262aee8422dbad685e6132eae1c7641183): Full embedded verification now streams case output into its main log **while each case runs**, and the production synthetic-MIDI journey reports periodic native startup, backend phase, transport and admission state. Previously, each case was appended to the main log only after completion; a log captured mid-run ended at the scenario heading and could not distinguish slow startup from a failed transition.
- [`904bbd5`](https://github.com/tpepels/piano_teacher/commit/904bbd54b44d0fdac6b90574247bb173bb569d95): Godot's versioned snapshot inbox now rejects successful replies with empty/non-object JSON through its existing fail-closed control path; stale ordered polls remain intentionally discardable. The native presentation fixture checks the parser boundary.
- [`fbc99ff`](https://github.com/tpepels/piano_teacher/commit/fbc99fffdfcbcf1959a8a9d04806cfe4753ebe4c): A successful `practice.command` reply must pass the same generated state contract used by state polling **before** the native command coordinator emits navigation, score or settings success effects. The separate command outcome must also contain typed `executed`, `action` and each known effect flag; malformed replies are presented as command errors instead of silently committing partial UI effects. This is source-checked only.

**Evidence limitation:** The 2026-11-22 user-supplied `piano-embedded-production.dXXMPe.log` contains a passed production UI scenario and only the heading for the next synthetic-MIDI scenario; it does **not** contain an exit code, assertion or completed scenario outcome. The current-HEAD Python/Godot tests and full embedded-production verifier cannot be executed from the connected repository tools available in this session. Therefore no reported test failure has been reproduced, no same-HEAD green run is claimed and V0–V7 acceptance remains open. The workflow remains manual-only (`workflow_dispatch`), without commit-triggered runs. Run the exact current revision with `bash scripts/test.sh --coverage` and `bash scripts/verify-embedded-production-local.sh` before software acceptance; connected MIDI/audio and original Pathétique acceptance remain separate physical gates.

### 2026-11-22 integrated source fixes and verification policy

The graphical controls now read the terminal backend admission result under the same command lock (`2cd9e64`) and display a recoverable, explicit failure (`68b1bca`). Physical preflight retains only the measured arm round-trip clearance rather than delaying the first audible count-in (`c4a3bf1`, corrected by `d32cb13`).
Native Resume always protects the paused source and schedules a distinct full count-in after a frozen pause (`91f5c0a`, revised by `1c1b98e`). Its accepted snapshot synchronously binds authorized notation; Python rejects deadline retiming of genuinely reused paused ink, and native preflight tolerates only integer-frame quantization (`d32cb13`). An attempted reused-origin correction (`ed9e11b`) still failed the Moonlight Pause-in-count-in native scenario: the paused world's time remains frozen during the asynchronous reservation. Production consequently always selects a **fresh, backend-authorized Resume slot** (`1c1b98e`), with the paused predecessor physically protected. Audible cue deduplication is keyed by the authorized segment. The full native rerun is pending.
No replacement UI state machine, second musical clock or software-only claim of physical acceptance was introduced. On 2026-11-22 the GitHub workflow was changed to `workflow_dispatch` only, with `core` (default) and `full` scopes: commits and pull requests no longer launch CI. Manual verification is available from Actions → Tests. A running workflow cannot be canceled through the available GitHub connector; its existing run completed successfully before the manual-only change.

### V4 and navigation source closure — 2026-11-22 (awaiting local CI)

- [`a4990a7`](https://github.com/tpepels/piano_teacher/commit/a4990a7d7fcc391a263acd1885984649468d9647): `ScoreStatePublisher` now freezes notation when a terminal failed or idle playback ledger still contains a historical authorized segment. Historical ink can be displayed but no old rate epoch may advance after the playback owner failed. The existing motion regression checks that terminal failure yields `hold`, while a valid pending successor can still `retain` the predecessor's authorized rest.
- [`b6045b4`](https://github.com/tpepels/piano_teacher/commit/b6045b46f0e094cc9c7dbf08b5b258a27fb852ac) and [`fa70f32`](https://github.com/tpepels/piano_teacher/commit/fa70f32fd76a671cb293388aa2b78af3bf273f6c) remove the obsolete `CommandRequestState` dependency from `NavigationSession.navigate`, the unused `back` route, and the corresponding injection from `Main`. Navigation now receives only target and authoritative published state; pending-command safety remains in the command queue.
- Concurrent [`53b7db5`](https://github.com/tpepels/piano_teacher/commit/53b7db5bcc), [`143f4ef`](https://github.com/tpepels/piano_teacher/commit/143f4ef350), [`ae0291b`](https://github.com/tpepels/piano_teacher/commit/ae0291b79f06d212e9ef19116aaa6a0adcf1d743) guard warm-up passage, hand and stage navigation against unearned mastery, in both backend and screen presentation. [`d67c03f`](https://github.com/tpepels/piano_teacher/commit/d67c03f1fcd7b682117f189ac72716ace6c23a1b) records those separate source fixes and pending gates. These changes were preserved on `main`.

These changes share the existing engine/session, single physical ledger,
native projector and accepted-command routes. No alternate musical state,
graded clock or pause policy was introduced. No same-HEAD CI, connected
MIDI/audio or independent package acceptance has been performed.

### V1/V2/V3/V5/V6 integrated source follow-up — 2026-11-22 (awaiting owner CI)

The following fixes are committed on `main` and have **not** yet passed the
owner's local CI. The old passing native run `45017492022` predates them.

- [`44bf2a8`](https://github.com/tpepels/piano_teacher/commit/44bf2a8c1231ee2a278b05eb3d5e12f6da8476c7) unifies the transport-intent/admitting/terminal-failure projection consumed by the rendered frame **and** by locked `ui_*` command resolution. Previously the command-side snapshot lacked `playback_intent`, so a visible `admitting` state could resolve Stop or Pause against a different phase.
- [`44d9e18`](https://github.com/tpepels/piano_teacher/commit/44d9e18b1eaf4561493e9995f47d33e8a6614166) extends the existing real `PracticeEngine` desktop checks with admission-time navigation suspension, idempotent re-suspension, Stop without renderer identity, refusal of a late reserve, and Stop of an authorized take. The existing `tests/test_state_transition_journeys.py` also exercises simulated wrong/correct MIDI, grade boundaries, recovery, disconnection and saved progression through real production owners.
- [`ea6923f`](https://github.com/tpepels/piano_teacher/commit/ea6923fe63c3267e2633d05dcb623c9b3a0a5f42) adjusts the production synthetic-MIDI journey's bounded timeout and its verifier wrapper consistently to accommodate the newly exercised, full authored Resume count-in. The timeout is still finite; failure remains a failing scenario rather than a skipped gate. This does not establish passage correctness without running the native journey.
- [`26208b1`](https://github.com/tpepels/piano_teacher/commit/26208b1c8c1cb0104a474aa3072e55ea7f4bac75) extends the **actual embedded Godot / Python / native queue / synthetic-device** journey: after the original Free/wrong-key/Pause tests, it pauses and resumes a timed take, checks stationary immutable ink and same transport identity, completes a failed repeat and clean tempo advance, then executes the production Stop command and checks for delayed reentry. The native gate still runs lost reserve/present ACK variants separately; these additions are unexecuted.
- [`5839e98`](https://github.com/tpepels/piano_teacher/commit/5839e98732ebeeaf8d5bd7178321f63af8b2a58f) removes the no-longer-produced `reused_count_in` receipt, partial-count-in scheduling branch and `resume_remaining_beats` API field from Python reservation/authorization and Godot; the existing paused-count-in regression now requires a fresh full count-in with the same take identity.
- [`8c07d02`](https://github.com/tpepels/piano_teacher/commit/8c07d02a4f3bca93ea13a7854c608cc96b93650b) removes the remaining shortened/physical-reuse timing path from `VisualTransport`, `PlaybackSession`, `TransportActions`, `TimedPlayback`, `ResumeRequest` and `MusicalScheduler`. The legitimate announced-rest reuse mechanism for an already-authorized automatic continuation remains; it is not a paused-source relocation.
- The separate exact-source Pathétique II native acceptance was integrated in [`d010536`](https://github.com/tpepels/piano_teacher/commit/d01053673) as opt-in `PIANO_PATHETIQUE_II_MIDI`, without committing private MIDI. [`ac61332`](https://github.com/tpepels/piano_teacher/commit/ac61332e1) adds real MIDI progression checks for pedal-friendly and strict release grading. Neither establishes real keyboard/speaker acceptance.

**Next owner-run gate on the exact same HEAD:** `bash scripts/test.sh --coverage`
then `PIANO_PATHETIQUE_II_MIDI=/absolute/path/to/source.mid bash scripts/verify-embedded-production-local.sh`
(or omit the environment variable and leave the Pathétique-specific check pending).
Review parser errors, complete native scenario outcomes, no stuck admission,
actual selected bar bounds and package contents. Only after successful local
core/native results may V0–V6 be considered software-verified. Physical
CA49, speaker/headphone, Pathétique visual and independent installation
acceptance remain separate open V7 requirements.

### V2/V5/V6 warm-up and snapshot acceptance follow-up — 2026-11-22

- [`d9493eb`](https://github.com/tpepels/piano_teacher/commit/d9493eb8518c1883985610533e7e8ba4bbd905bd): Python owns the required state ports, control-action shapes and presentation-directive variants, and generates the same checker for Godot. Native `ApplicationStateInbox` rejects malformed/incompatible snapshots before score adoption, native admission, input or visible controls. [`ed2e138`](https://github.com/tpepels/piano_teacher/commit/ed2e1383c1192adc15c8ea05e5a0c7f3b7c10226) deduplicates rejection diagnostics and disables stale controls until a valid snapshot arrives. Schema remains v5 (no renamed fields).
- [`4f717c8`](https://github.com/tpepels/piano_teacher/commit/4f717c80c9ef9898e952af6d3728792e3da1456d) adds public real-engine one-way Suspend/Stop, passage navigation and malformed snapshot tests. [`6c3687d`](https://github.com/tpepels/piano_teacher/commit/6c3687dd36e05f71f3ce779e6602d1a7cb3bfdca) immediately cancels local count-in sound for pending Stop without bypassing backend transport authority.
- [`53b7db5`](https://github.com/tpepels/piano_teacher/commit/53b7db5bcc07b1510154120125e3df7be7238c9b): `teaching_course` rejects attempts to jump ahead of unearned warm-up steps; `stage_change` prevalidates those actions before canceling a live take, and `lesson.overview` projects each step's availability from one course owner.
- [`143f4ef`](https://github.com/tpepels/piano_teacher/commit/143f4ef3501dd3e53e17a27655ef2ce4ff309d1d): Native Lesson Path picker and arrows disable unavailable warm-up stages; advanced Pause disables locked hands, and backend passage-next availability requires mastery of the current warm-up exercise. Imported-score step selection remains unrestricted.
- [`d2a6d13`](https://github.com/tpepels/piano_teacher/commit/d2a6d13a56b7402e93426c205e3db15b365e0c8f): Fixed a stale Lesson Path cache: automatic mastery, step changes and source revision changes now invalidate the overview even when the piece fingerprint stays identical. The next accepted read reflects newly available warm-up stages. [`2e63c53`](https://github.com/tpepels/piano_teacher/commit/2e63c53abb37a3a7b385dfbe098e504c5e45cc5d) exercises this through the existing native LessonSession behavior group.
- [`ae0291b`](https://github.com/tpepels/piano_teacher/commit/ae0291b79f06d212e9ef19116aaa6a0adcf1d743) checks direct public warm-up action refusal and unrestricted ordinary MIDI selection. [`ac61332`](https://github.com/tpepels/piano_teacher/commit/ac61332e19b7139209440987eeb3f9a4208a25c2) checks default and strict note-release policies using a real engine/fake MIDI input.

**Not yet verified:** Source work has not been compiled or run against this HEAD. Same-HEAD local core + embedded production + optional exact Pathétique MIDI must pass before marking V0–V6 software accepted. CA49 hardware, audio judgment and independent-machine package acceptance remain separate V7 gates. GitHub Tests remains manual-only.

### V0/V2/V3/V5 secondary entrypoint implementation — 2026-11-22

- [`ceffe050`](https://github.com/tpepels/piano_teacher/commit/ceffe050a0822402934e3eae18fb14310ca31d31): Removed navigation's independent musical phase/pending-action tables and direct Pause dispatch. Leaving Practice requests a one-way `ui_suspend`, resolved under Python's session lock. It pauses a newly started take after any pending command completes, and cannot accidentally Resume an already paused one. As a suspension-only action, it does not require a physically ready renderer.
- [`19c7378`](https://github.com/tpepels/piano_teacher/commit/19c7378c8906cdcbf8e83dd3fcf605a6b96f494d): Native preflight now refuses absent, malformed or nonfinite geometry instead of attempting a provisional reservation with a Godot runtime error; physical rejection reasons appear in diagnostic messages.
- [`12f04f9`](https://github.com/tpepels/piano_teacher/commit/12f04f9a1372ecbadef9eefadffc9f78ba8b2d97): Advanced Pause now renders the backend-published Resume, Retry, Listen and tempo actions. It emits raw `ui_*` intents instead of deciding mode-specific Retry or calculating ±10% BPM. The initial keyboard migration briefly mapped left/right to previous-step/Skip; this was corrected in `14a2119` to preserve previous/next **passage** semantics. Python's Retry projection handles Listen replay consistently with the former paused Listen behavior.
- [`2102229`](https://github.com/tpepels/piano_teacher/commit/21022296de3cef3f5b73c1722f0cb353afef5d3f): The advanced measure seek button uses the canonical `seek_available` projection rather than a second Listen-mode veto.

**Unverified gates:** These commits and the follow-up source changes below have not run CI. At completion of software work the owner will run `bash scripts/test.sh --coverage` and `bash scripts/verify-embedded-production-local.sh` against the **same current HEAD**, then separately accept connected CA49 MIDI/audio, Pathétique II and independent clean-machine packaging. The prior green run applies only to `1c1b98e`. V0–V7 phase exit criteria remain open where matrix, native, visual or physical evidence is missing.

### V2/V5/V6 native UI and dead-path audit — 2026-11-22

- [`14a2119`](https://github.com/tpepels/piano_teacher/commit/14a2119a1e26f523c4a467c5d0b37cf6973421cf): Previous/Next passage now use distinct backend `ui_passage_previous`/`ui_passage_next` intents. This preserves **exercise/passage** navigation semantics, rather than conflating them with previous *lesson step* or no-mastery Skip. Backend-published exercise bounds disable the corresponding Lesson Path buttons. Navigation only happens after an accepted command, including explicit step and hand selection. The backend `stop` projection replaces the Lesson Path's independent phase list.
- [`647d561`](https://github.com/tpepels/piano_teacher/commit/647d561fe48e44ee709d43785a6ba51356c9ee07): The S shortcut and Lesson Path Stop use validated `ui_stop`; pending UI requests disable relevant Lesson Path actions. Removed the now-unused direct `practice_requested` navigation signal.
- [`433d95e`](https://github.com/tpepels/piano_teacher/commit/433d95e058b1e2209cd8bd56209a13a44f0184e8): Backend control projection now owns Lesson Path activity choices, warm-up hand unlocking, hint enablement, and an explicit `path_skip` independent of the compact practice screen's hidden Skip. This fixes an availability regression for practice-flow Lesson Path exploration.
- [`7b0586d`](https://github.com/tpepels/piano_teacher/commit/7b0586dd60fbae25a881a45cffdb981bc11cb672): Stop also remains available during native `admitting` and an outstanding `playback_intent`, so a pending physical reservation can be canceled from the standard S gesture.
- [`acd8216`](https://github.com/tpepels/piano_teacher/commit/acd8216c43fd0f200689b931d490e1c23678ace3): Fixed a pending-request safety race: Stop (including the S keyboard gesture) now queues behind an in-flight command and takes precedence over delayed Pause or navigation suspension. A subsequent navigation gesture cannot discard an already queued Stop. This is unverified pending local CI.
- [`2d7e610`](https://github.com/tpepels/piano_teacher/commit/2d7e6104f75f573e77c8ef24d7e821d31e5e8fd4): Stop and screen-exit suspension no longer require score readiness, matching renderer revision or renderer fingerprint. Their effect is determined exclusively from current backend state; they cannot start/re-time a source. This closes a failure mode in which a stale score could prevent the S safety action. Source only, awaiting local CI.
- [`84b40c2`](https://github.com/tpepels/piano_teacher/commit/84b40c2238a473e22885dd4d61263ccdea4f72fb): Removed the defunct native paused-source re-selection branch and `PAUSED_REUSE_EPSILON_BEATS`; `StreamTakeBinding`, `ScoreStreamController`, `StreamAdmissionExecutor` and the existing native fixture now have one future-only physical arm contract. Paused-owner protection is retained to preserve exposed source ink. This code has **not** been compiled or run.
- The native ownership sweep examined action emitters, screen/effect coordinators, state/mode readers and score transaction adapters. Remaining phase/mode reads in `GameStage`, `GamePhaseCue`, `PracticeScoreStage`, `ScoreStepTimeline`, `NativeScoreFeedback`, `ScoreRunway` and `ViewBase` are used to draw or prepare already selected state/score, not to decide progression, grade, retry tempo or musical deadlines. Explicit activity, hand, hints, seek and reset values continue to reach Python validation. `ScoreAssetSession` may notify native readiness; it does not authorize musical playback.

**Not accepted yet:** source review is not Godot parser/runtime verification; V1/V6 transition coverage and all V7 physical gates still depend on same-HEAD local CI plus connected-device/visual/audio checks. The older green run does not verify the new method signatures.

### Initial implementation record - 2026-11-21

**Source commit [`afb84e9`](https://github.com/tpepels/piano_teacher/commit/afb84e9eff5c580b3ff0ed238b5ef162ecbed52b):**
`application/control_projection.py` now derives the primary,
Pause/Resume, Retry and Listen action semantics and visible primary label
from the same Python session state. `SessionReadModels.snapshot()`
publishes a read-only `controls` model. `PracticeControls.control()`
resolves `ui_primary`, `ui_pause`, `ui_retry` and `ui_listen`
against the *current* backend state under the session lock, then uses
the existing teaching/transport routing; existing explicit command
operations are unchanged. The native coordinator forwards raw gestures
with measured renderer readiness; `PracticeScreen` reads the published
primary action/label/availability rather than deciding these locally.
`CommandRequestState` keeps the pending Pause behavior using the
backend-published action without authorizing playback in Godot.

**Follow-up ownership migration:** The same Python `controls`
projection now also publishes Retry visibility/readiness, Listen captions,
previous/skip availability and the permitted manual-tempo controls.
`PracticeScreen` consumes those fields instead of re-evaluating
practice phases to enable or disable buttons. The existing
`tests/godot/practice_controls.gd` presentation fixture was adjusted to
supply a published `controls` model rather than consult the superseded
Godot policy. This updates an existing test; no new tests were added.
Native UI gestures additionally carry the exact ready renderer
`revision` and source fingerprint. Python validates these against the
current authoritative snapshot under the command lock; a ready renderer
from an earlier piece or engraving generation cannot authorize the
new selection. This protects the control boundary while the full V3
admission and deadline refactor remains open.

**Additional V2/V5 migration:** Previous lesson, Skip and tempo +/- clicks
now emit `ui_previous`, `ui_skip` and `ui_tempo_*` without deriving
the next stage, lesson number or tempo permission in Godot. The
current Python control projection enables/disables these actions and
`PracticeControls` resolves them against the current locked state.
The native coordinator attaches renderer revision/fingerprint/readiness
to every `ui_*` command, including events emitted from `PracticeScreen`.
The existing command-success navigation handles the new intent names.
A further command/read boundary prevents UI gestures from invoking the
heavy per-frame score presentation projection. `SessionReadModels`
now exposes a read-only `control_snapshot()` using the canonical
session facts and active flow, without calling `score_state_publisher`
or the headless graphical fixture. The locked `PracticeControls`
command transaction uses this read port. The normal `snapshot()`
continues to publish the full score state independently, sharing the
same `project_controls` policy.

The original direct API command forms remain available to external tools,
and the transport/admission redesign remains open.

**V0 transport findings for V3/V4:** The native
`ScoreAdmissionGateway._deadline_at_world` still inverts the
`ContinuousScoreFlow` visual projector to pick a musical start
deadline after the backend has already published its earliest admissible
deadline. `GuidedPresentationSession.update_hold` releases an
acknowledged Pause's visual hold when a pending Resume intent appears,
even though `playback.present` may not yet have authorized it.
`PresentationTimeline.forecast_authored` falls back to the held
`project()` when no tempo segments are supplied, so keeping the hold
can instead make a future Resume deadline unreachable. This is a
specific ownership/design conflict, not a completed fix. V3 must move
the final deadline choice to the backend using native physical
measurements, and V4 must permit a purely hypothetical future
projection while the displayed hold remains in force until the
authorized receipt. Do not add a second transport clock, silently
release Pause while reserving, or shift an already admitted source.

The old policy file is still retained pending a complete caller sweep,
and all native/software gates remain unverified.

**Open:** `practice_control_policy.gd` remains until all consumers
and legacy tests are migrated; additional buttons and physical shortcuts
still have legacy client-side interpretation; score admission/deadline
and visual-clock decisions have **not** moved. V0-V7 are not complete.
No new unit tests were written, per the owner's latest instruction.
Neither native build/CI nor physical piano acceptance is claimed for
this revision. Existing CI and native journeys must be run before any
acceptance claim; deterministic full-transition tests remain V1/V6 scope.

### V0 actual transition/ownership ledger - 2026-11-21

Originally recorded separately; now consolidated into the [production transition ownership ledger](docs/architecture.md#production-practice-transition-and-ownership-ledger) as a concrete
end-to-end authority/observation matrix for the active production
path: MIDI/file/controls → locked Python transitions → typed
`practice.command` outcome and versioned state → source-bound
physical score admission → reserve/present/status acknowledgements →
visual epoch, metronome, feedback, grading, settlement and saved
reopen. The ledger maps the owner and native reader of each
decision, lists the expected and failing branches for 20 material
transitions, and records actual runtime counterexamples from
the CI-native and user-physical audits. It explicitly marks
the *still incomplete* V3 backend-proposal ownership boundary
and separate hardware acceptance. This is a source ownership
audit, not a claim that all transition scenarios have already
passed physically.

### Phase V0 - Trace the complete production state machine

**Implement:** Inventory *all* active paths from MIDI/file load or button
intent to Python command, accepted state, asset publication, physical
reservation, render frame, note ingress, grading, settlement, navigation and
saved reopening. Review `godot/main.gd`, `practice_screen.gd`,
`practice_control_policy.gd`, `practice_command_coordinator.gd`,
`practice_presentation_session.gd`, `score_admission_gateway.gd`,
`presentation_timeline.gd`, `practice_frame_coordinator.gd`,
`notation/native/view.gd` and their real callees; then the Python application
owners, native bridge and CI journeys. Enumerate every writer, decision,
implicit default, timeout, reentry and handoff. Record the exact transition
table, authority, command and acknowledgment of each edge, and how it is
observed by the learner. Compare with `docs/practice-flow.md`.

**Defect witnesses:** Retain reproducible software/physical traces for:
Free moving without input or selected tempo; Pause moving/remaining
unavailable; Resume stuck in admitting; extra measures visible; automatic
repeat refusing immutable source admission; played MIDI reaching obsolete
Godot effects. Log source SHA, user action, state, score revision, transport/
take/segment identity and expected versus observed result. Do not infer a
causal fix from a passing headless reproduction.

**Exit:** The complete state graph, boundary matrix and ordered migration
map are written in `docs/architecture.md`; missing facts and observed
counterexamples are explicit; prior behavior is not silently redefined.
No runtime behavior or prior acceptance claim is changed in this design
phase. Source inspection and existing tests must still run without a new
failure. The baseline source and test result are recorded here.

### V7 native failure triage and source-accurate Free acceptance - 2026-11-21

Full native-production run
[`44956142119`](https://github.com/tpepels/piano_teacher/actions/runs/44956142119)
failed two distinct scenarios after the semantic-motion and
typed-command migration. Embedded Python registration itself,
the real-score semantic geometry and package all worked;
the direct `native_bridge_smoke.gd` consumer still expected a
flat `practice.command` response when `score_ready` now returns
the explicit `{state, outcome}` protocol. The smoke now
verifies that outcome, then tests the unmodified state snapshot.

The full-scene fake MIDI scenario also found that the initial
*authorized travel* of newly admitted Free notation was still
in progress when wrong-input/silence hold measurement began.
It now waits for the canonical target deadline, the genuinely
held presentation world, and at least 250 ms of stationary
**painted score** before delivering its wrong MIDI signal.
The post-error 350 ms stationary assertion is unchanged; no
additional lesson credit, tolerance for MIDI-driven movement
or Free-target behavior was weakened. The stage is still
required to produce and hold its real native target; missing
one produces a bounded journey timeout, not a skipped test.

The two fixes are integrated together and requested through a
new full `[native]` gate; this is not yet physical acceptance.

### Native-production full-source rerun after timing and UI contract changes - 2026-11-21

The previous native-production run showed that native compiler,
embedded Python, Moonlight/Peace Piece/Chopin score loading,
UI Play/Pause/Resume and relocated package audit all passed.
Its synthetic hardware-boundary MIDI journey revealed the
faster-repeat collision now fixed in the musical schedule.
A new `[native]` full CI run is requested for the integrated
outgoing-tempo rest, source-bound backend motion directives,
version-5 state contract, transient command outcome envelope,
idle score hold and stronger wrong-Free/window assertions.
This phase remains **unaccepted** until that run is green and
local physical MIDI/audio remains an explicit manual gate.

### V6 restored core timing assertion after outgoing-rest correction - 2026-11-21

Core CI run
[`44956108397`](https://github.com/tpepels/piano_teacher/actions/runs/44956108397)
found one remaining OLD test fixture expecting a faster 48 BPM
count-in gap within the preceding 40 BPM source. The engine
correctly scheduled a full one-bar 40 BPM outgoing rest; the
test still expected the former shortening and failed by one
second. The desktop admission journey's fixed-deadline
assertion is now aligned with the corrected musical contract,
while still checking that the incoming take uses its selected
new BPM. No compatibility fallback or rest-overlap exception
was introduced. Fresh core CI is required to accept this edit.

### V3/V7 fixed one-bar faster-repeat clock defect - 2026-11-21

Native-production GitHub Actions run
[`44955009440`](https://github.com/tpepels/piano_teacher/actions/runs/44955009440)
completed all embedded Python build/registration, production UI
Play/Pause/Resume, Moonlight Sonata, Peace Piece, Chopin and
relocated standalone package audit successfully, but the
full-scene synthetic MIDI journey exposed a critical real bug:
`SCORE_TRANSPORT_PREFLIGHT: direct_repeat_overlaps_existing_ink`
when the learner achieved the first clean 40 BPM take and the
next target increased to 48 BPM. The backend exact-repeat deadline
was placing the one-bar *outgoing* visual rest at the *incoming*
48 BPM, consuming only 3.333 beats on the still-moving 40 BPM
visual ledger. The still-visible written rest therefore occupied
the incoming header's position and the immutable queue correctly
refused the collision. `AttemptProgression.plan_full_passage`
now measures the entire authored gap at `facts.bpm`, the
outgoing take's rate, and switches the new take to its
`exposure.bpm` only at the authoritative downbeat. This
preserves exactly one complete written rest measure and never
shifts already printed material or adds a silent second gap.

The real `tests/test_practice_timeline.py` clean-faster and
failed-same-tempo cases now assert this outgoing rest clock
and independently verify the incoming selected tempo. The
native-production journey still needs a fresh successful run
before the faster repeat is accepted; no visual exception or
overlap bypass was introduced.

### V6 CI failure corrections from actual GitHub Actions - 2026-11-21

GitHub Actions core runs `44954408749` and `44954577853`
failed with two concrete scenario defects: a previously existing
`test_state_transition_journeys` fixture still sent legacy
`deadline_ms` instead of physical evidence, and the new
lost-ACK replay fixture advanced the virtual clock beyond the
original musical count-in without reserving sufficient future lead.
The journey fixture now uses current source-bound
`sampled_at_ms`/`travel_ms` evidence for both Start and Resume,
including the actual renderer revision. The ACK fixture now
reserves twenty seconds of safe physical travel before aging
its sample, so it checks true idempotence without requiring a
musically expired take to start. These correct scenarios, not
application policy or backwards-compatibility fallbacks.
Fresh CI must pass before V6 can be marked complete.

### V1/V3 real worker integration matrix - 2026-11-21

The existing `tests/test_desktop_playback.py` was extended using
its established `EngineCommands`, `PracticeEngine`, generated
score and fake MIDI input port. Cases now cover exact lost-ACK
reservation recovery, source/geometry/time witness conflicts,
stale measurement refusal, bounded three-attempt failure, the
120-second asset-unready timeout, failure-authorized receipt replay
refusal, and incorrect/missing MIDI. These tests exercise the
real backend transaction and teaching/transport machinery; no
second transition/grading policy or fixture transport was introduced.

**Verification open:** The environment can fetch and commit through
the GitHub connector but lacks a checked-out project, Godot binary
and configured MIDI device. The tests are committed but have not
been executed here. Native scene-level presentation checks and
connected-hardware acceptance are still required.

### Phase V1 - Build the deterministic real-path simulator

**Implement:** A controllable monotonic time source and fake MIDI
note-on/note-off, disconnect/reconnect and physical shortcut input *at the
existing production ingress boundary*, with recorded timestamp/velocity/
channel data. Run the *actual* Python engine/worker, command router,
Recorder, grading, lesson generator, settlement and saved progress; do
not duplicate those algorithms in a fake lesson engine. Add an embedded
Godot runner using the real `PianoNative` operation path, score preparation,
admission gateway, score queue, presentation frame and renderer with
controlled frame stepping. Stub only external I/O (piano hardware, speaker
output, wall-clock sleep and genuinely external services); do not stub
native score admission in a purported end-to-end scenario.

**Observations:** Capture public state/commands, accepted action list,
selected measure IDs, BPM, musical beat, visual world position, live note
marks, source queue/receipt identities, audible scheduling facts and
persisted evidence. Provide distinct *backend-only* quick checks and
*embedded-Godot* boundary checks, with neither misrepresented as the other.
Keep a simple, reproducible scenario script rather than a parallel
application state machine. No pixel tests, private-object shape assertions
or architecture-parity checks.

**Exit:** The runner can execute at least an opening Listen -> Free ->
Tempo journey and both a simulated successful and unsuccessful played
take through production paths, producing deterministic trace artifacts.
A deliberately withheld/stale admission and an injected MIDI failure are
detected as failures, not accepted or silently skipped. Known existing
player-reported defects have reproducible red witnesses, without claiming
the unchanged build is green on those checks. Normal existing CI still
passes; newly introduced, confirmed behavior checks join CI as fixed.

### Phase V2 - Publish one authoritative practice/presentation contract

**Implement:** Define typed/versioned immutable session projections and
commands across embedded Python and Godot. The backend publishes a single
selected source/window/hand, mode and transition state, tempo and meter,
paused/running/ready facts, grading eligibility, active take/segment,
available actions (meaning, enabled, label/reason), displayed measure bounds,
feedback and *explicit visual directives* (held Free target, frozen Pause,
authorized timed epoch, or no source movement). Avoid relying on scattered
phase-string interpretation and implicit defaults. Use typed correlation IDs
for session, source revision, intent, attempt, take, transport and queue
generation. Specify duplicate, delayed and out-of-order acknowledgment
semantics. Centralize semantic transition rules in the existing Python
owners; do not introduce a second Python policy owner.

**Migrate:** All affected native inbox/coordinator, command/feedback and
screen readers consume the one canonical projection, with validation of
missing/incompatible fields. Remove superseded flags and incompatible
production paths in the same phase. Preserve documented MIDI-only import,
saved-session migrations, alternate course paths and current public
operations. Update the architectural contract and tests with the code.

**Exit:** Each supported input has one authoritative transition and
resulting action projection, demonstrable through the V1 runner.
Read/poll does not execute transitions. No Godot component independently
infers an enabled musical action, target tempo or next lesson decision.

### V2/V3 preserve active phase during successor admission - 2026-11-21

`ScoreStatePublisher` now projects `admitting` only when the
backend is **neither running nor paused**. A new reserved successor
while an existing take is playing or paused remains visible in
`playback_intent` without overwriting the active musical phase.
That prevents the native stream, metronome and controls from
misclassifying an actually playing take as idle admission merely
because its next exposure is being prepared. The current and pending
identities remain orthogonal application facts.

No new tests; the native transition matrix/physical acceptance
must verify continuous outgoing ink and correct active-phase cues.

### V3 verify physical source before local authorization effects - 2026-11-21

The native score ledger now publishes a read-only
`owns_authorized_segment(segment_id)` query. It accepts either the
same take as an ACKed, still-armable future reservation or the already
live source, and in both cases requires the immutable queue to still
contain that exact owner. This is an invariant query on the existing
`StreamTakeBinding`, not a second native take state machine.

After `playback.present` is authorized by Python, the physical
gateway verifies this ownership **before** promoting the renderer,
authorizing visual tempo epochs or speaking count-in syllables. If a
resize, late withdrawal or invalidation removed the source, Godot
reports `playback.failure` against the exact take/segment and clears
the provisional stage. Python remains responsible for stopping
grading. The older `bound_segment_id()` view is insufficient here
because it becomes live only upon the next authorized state poll.

No new tests were written; native execution and physical verification
remain exit gates.

### V3 fixed-repeat native rejection - 2026-11-21

The native physical gateway now explicitly withdraws a fixed
automatic-repeat intent as soon as its announced one-bar downbeat
has expired or fails immutable-score preflight. It deduplicates the
withdrawal by intent/attempt and lets the Python transaction owner
mark the missed fixed deadline as terminal. No renderer-side retry
can silently move that exact musical repeat later. The normal
general-purpose 120-second admission wait remains available for
legitimately slow source engraving and transient new-take readiness.

### V3 bounded admission lifecycle - 2026-11-21

The Python playback transaction now owns the admission retry budget
(maximum three physical attempts) and a 120-second maximum pending
lifetime while assets or physical preflight are unavailable. Expiring
a fixed-deadline automatic repeat terminates that intent immediately:
there is no second timestamp or extra bar. A permanently failed
attempt clears the intent and publishes `playback_timeline.state=failed`
and its reason; `ScoreStatePublisher` displays that reason in the
normal practice feedback and enables manual recovery by exiting
`admitting`. Existing interrupted/paused active source history is
retained. This replaces unbounded invisible retry behavior with one
backend-owned lifetime policy.

**Unverified:** Embedded worker cadence, long-source engraving,
frame-step and physical recoverability still need native/CI checks.
No new unit tests were added.

### V3/V4 source-and-receipt identity hardening - 2026-11-21

`PlaybackCoordinator.present` now replays an earlier successful
receipt only if its exact segment, take and attempt remain active and
not failed. Old completed authorizations cannot be replayed to revive
superseded source/take visuals. Godot's state/status reconciliation
does not treat a failed or idle playback ledger as authorization merely
because it retains an active-segment identifier.

The native Free target cache is bound to the selected score
fingerprint and revision. Switching windows while still in Free clears
the cached target/plan before it can hold or enqueue the next score.
Identical guided plan IDs are not re-enqueued every frame; expired
or nonfinite guided targets are refused instead of entering the
physical score queue. These are physical source invariants, not a
parallel lesson decision engine.

**Gates:** Source changes during a pending or paused take, lost ACKs,
slow engraving and MIDI/renderer acceptance still require running the
existing native/embedded scenarios. No new tests added.

### V3 lost-ACK state reconciliation correction - 2026-11-21

A prior callback identity hardening incorrectly passed the compact
`playback_timeline` read model to the exact-ID receipt validator.
The timeline only publishes its authorized segment, not a request
attempt or intent ID. This made a successful presentation observed
through state polling fail to promote the held/provisional score.
The gateway now verifies that the **active segment equals the pending
receipt's segment**, then confirms from its already validated immutable
receipt. Native `playback.present` replies still require the full
intent/attempt/take/segment identity. This preserves authorization
after a lost present ACK without accepting an unrelated take.

### V3 active playback watchdog covers absent renderer - 2026-11-21

A playback state whose authorized score renderer is null or invalid
is now treated as a missing source, like a renderer bound to the wrong
segment. After the existing four-frame grace the physical adapter
reports the exact take and segment to Python, which alone halts graded
playback. The watchdog, post-authorization physical owner check and
prepared-stage promotion now share one failure-request port. Busy
requests do not falsely mark another failure as delivered, and a
failed report can be retried on subsequent active frames.

Native runtime/physical acceptance remains unverified; no new
unit tests were added.

### V3 missing renderer / authoritative-cancel race - 2026-11-21

A fixed automatic repeat now expires immediately even when no
matching/ready native renderer is present: the gateway explicitly
withdraws the impossible deadline rather than silently waiting
for the generic admission timeout. A failed fixed-repeat withdrawal
remains retryable after its request completes.

Native cancellation after `playback.status` now distinguishes
a still-pending backend intent from one already replaced or removed.
Only the former requires a `playback.withdraw` to advance the
authoritative attempt; a verified superseded intent retracts local
provisional ink without issuing a stale backend withdrawal. Prior
live/authorized notation remains untouched.

### V3 local transaction cleanup and late-present idempotence - 2026-11-21

A confirmed segment can appear in a backend state poll before its
`playback.present` callback reaches Godot. The native gateway
previously cleared its receipt on poll confirmation, then treated
the late success callback as a new uncertain failure. The callback
now ignores replies for a transaction already completed locally.
Every success, physical-source failure, failed runway promotion
and abandoned reservation now uses one `_clear_provisional()`
lifecycle termination, which clears stale reconciliation flags.
Failed physical source/stage promotion retracts only its provisional
arm and reports `playback.failure` for the authorized take;
it cannot reuse the old receipt.

No unit tests added by owner request; Godot and physical acceptance
remain outstanding.

### V3 physical travel measured by one tempo/epoch model - 2026-11-21

Removed `ScoreAdmissionGateway._physical_travel_ms` and its
repeated binary-search projections. The native presentation ledger
now computes physical travel as a *direct, read-only inverse* of
its own monotonic authorized tempo epochs while unheld, or as an
exact authored source-tempo integration from the frozen world
during Pause/Free/initial admission. The gateway receives only
the resulting physical witness. No provisional source can move the
painted score, no second tempo clock is created, and no frame
rounding loop attempts to choose an application deadline.

The final musical downbeat remains the Python
`PhysicalAdmissionEvidence`/`MusicalScheduler` decision, bound
to the same immutable source and queue generation. The Godot
direct inverse is purely renderer geometry, not grading policy.

**Open:** Native Godot parse/runtime, mixed-meter/tempo, pause
and physical MIDI acceptance of this replacement. No new tests
were introduced.

### V3 source-bound physical admission contract - 2026-11-21

The production `playback.reserve` contract has been replaced rather than
wrapped: the renderer now supplies a typed physical placement witness
(`sampled_at_ms`, `travel_ms`, source world and renderer/queue
generations), not `deadline_ms`. The Python
`physical_admission.choose_admission_deadline` combines the witness
with the immutable source intent, authoritative count-in and timing
floor through `MusicalScheduler.resolve`. A placement that cannot
satisfy the musical deadline is rejected; already-admitted ink is never
shifted to accommodate a second scheduling decision. An automatic
one-bar repeat must match its fixed downbeat within native time
rounding tolerance. The single receipt is consumed by
`playback.present`, whose existing commit verification binds MIDI,
metronome and audio to that admitted source.

The native physical forecast now reads the **currently authorized**
`playback_timeline.current` tempo map even during Pause, rather than
guessing from `phase == playing` or taking the new stage's tempo
before the handoff. That distinction prevents a future stage or a
paused source from accidentally changing the clearance calculation.
The native `_reserved`, `_presented` and final authorized
handoff now share one exact intent/attempt/take-id check, including
segment identity where available. Delayed or misrouted results cannot
bind a newer provisional renderer or start metronome/score epochs;
an uncertain authorized reply reconciles with the backend transaction
ledger rather than guessing acceptance.

Reserve retry now compares the *entire original physical witness*
with its stored receipt before checking measurement freshness.
This makes identical lost-ACK retransmissions idempotent, while
conflicting world/timing/generation evidence is rejected. The native
gateway also samples its local presentation clock and backend
monotonic clock together, avoiding inversion against the older
accepted-state receipt time. The resulting measured travel is still
submitted only as physical evidence, not a chosen timestamp.

The existing desktop playback test fixture now submits physical
evidence; no new unit tests were added.

**Remaining V3 gate:** Native syntax and integration runs, stale
reserve/present responses, queue retraction and physical MIDI/audio
acceptance must pass before this phase is marked complete. The
Godot renderer still measures physical travel by inverting its visual
projection; the Python application remains the final deadline owner.

### V3 bounded presentation-reconciliation witness freshness - 2026-11-21

The native present retry after a lost ACK now re-measures the
*same already committed physical source* immediately before
its `playback.present` request. It checks source/segment ownership
in the immutable queue and proves the unchanged world still
reaches Python's reserved deadline. A delayed reply cannot
extend or retime a fixed source. Fresh timestamp, actual queue
generation and pure geometry travel are submitted; failure to
reconcile rejects/withdraws without enabling grading.

On the backend, an expired musical count-in is checked before
physical attestation validation: an overdue reserved take can
advance its authoritative retry/terminal state even when
the old physical witness is missing or stale. This prevents a
lost-status loop that otherwise kept the same expired attempt
reserved for the full admission timeout. Native testing remains
an explicit gate on this changed transaction protocol.

### V1/V3 real backend physical-arm attestation checks - 2026-11-21

The real fake-MIDI backend integration suites now supply
a separate physically committed score witness *only* for
`playback.present`. A read-only `playback.reserve` offer
can obtain Python's chosen deadline but cannot start sound
or grading. Wrong queue revision, early world, mismatched
clock travel or missing attestation is rejected without
losing the valid original reservation. The source-bound
Start and Resume journeys use the same two-stage backend
contract. A new case supplies physical clearance **much
earlier** than the required count-in to verify that Python,
not Godot, chooses the later musical downbeat.

The fixture stubs only the renderer measurement; full
native Godot tests must demonstrate that the real queue
performs the exact committed arm after this reply and
that it passes the same attestation. These tests have not
yet been accepted by CI on the rewritten production source.

### V3 backend musical proposal before physical arm - 2026-11-21

The Python musical boundary now treats
`playback.reserve` as an uncommitted musical reservation based
on the renderer's *read-only earliest feasible* physical witness.
`PhysicalAdmissionEvidence` supplies a lower bound, and the
existing `MusicalScheduler.resolve` is the sole selector of the
final `deadline_ms`. Fixed automatic repeats still admit only
their previously published deadline, refusing a physical lower
bound that arrives after it. Godot must commit its native source
at that exact backend result, and the `playback.present` gate
requires a fresh source-world/queue-generation/travel-time
attestation proving the now-armed strip reaches the exact
deadline. The backend refuses incomplete, stale, conflicting
or physically earlier/later attestation before grading or
audio. It publishes the *committed* physical world in the
authorized segment, not the preliminary feasibility position.

**Integration in progress:** The native renderer must now
provide the attestation after the backend reserve response.
The remaining Godot arm ordering and test callers are migrated
in the same development sequence. Do not accept this phase
or deploy the interim contract before the complete native and
core CI transaction checks pass.

### V3 Resume feasibility uses the same commit route (2026-11-22)

Corrected a preflight/commit mismatch: when a paused source can
be reused ahead of the playhead, the gateway consistently uses
the Resume geometry path and the backend's partial spoken
count-in. Otherwise, both the pure native preflight and the
physical arm now use the fresh Start geometry, including the
complete new count-in and protected prior ink. Previously it
preflighted the Resume clearance but committed through Start,
which could author a deadline Start could not physically meet.
Python still owns the semantic Resume action, take identity and
deadline; no second native musical scheduler was introduced.

### V3 prepared-source exact-deadline reconciliation (2026-11-22)

Corrected a pure native `ScoreTransportReservation.plan_facts`
edge: a separately prepared, unexposed READY strip can be
withdrawn as a safe future suffix when the backend selects a
later final deadline. The prior preflight treated that
provisional source like an immutable paused take and rejected
the otherwise valid selected downbeat, trapping Start on the
same stale prepared placement. The new rule falls through to
the sole append-only placement only for `action=start`;
Pause/Resume and authorized ink remain immutable and may be
rejected rather than retimed. `tests/godot/score_stream.gd`
checks exact prepared reuse, later backend-selected append
with safe withdrawal, and paused-source nonrelocation using
the real source preflight owner. This is a source-geometry
fix only; Python remains the only author of musical time.

### V3/V6 complete native rerun requested after measured timing correction (2026-11-22)

A fresh `[native]` CI run is required for the integrated
physical downbeat validation fix, safe prepared-source reuse,
consistent Resume preflight/commit action, predecessor tempo
immutability, source revision and typed result handling.
This checkpoint also exercises all checked-in MIDI files
and two actual worker-reply-loss fault injections. Core
CI and the complete native result must both pass on the
same revision before any V0–V6 phase is reported complete.

### V6 core regression aligns physical evidence rejection with absolute timing (2026-11-22)

Core run
[`44982059687`](https://github.com/tpepels/piano_teacher/actions/runs/44982059687)
found one old rejection fixture still asserting that a smaller
`physical_world_origin` must be invalid. Under the fixed
backend-first protocol, such a coordinate is legitimate for
the same future downbeat after the relative physical forecast
has advanced. The malformed-evidence test now sends an
**unparseable world coordinate**, while separately retaining
the new acceptance scenario for a valid decreasing coordinate.
Queue-generation, source-revision and actual-deadline mismatch
remain rejection cases. The application protocol and physical
authorization timing have not been loosened further.

### V3 terminal failure cannot mutate automatic continuation preparation (2026-11-22)

`TimedPlayback.continue_at` now consults
`PlaybackCoordinator.automatic_request_blocked` before
`PlaybackSession.prepare_admitted_continuation`. Previously,
even when the canonical admission owner refused an automatic
repeat after exhausting attempts, the caller could clear
scheduled-rest context and overwrite the visible failure
with "Preparing the next passage". The pure early guard
retains the failed transaction/notice until the user
explicitly restarts or a source selection invalidates it.
The existing real fake-MIDI workflow regression checks
there is no new intent, mutation of notice or extra
automatic attempt.

### V3 real Listen duplicate-readiness regression (2026-11-22)

Extended the in-process fixture to open an actual Listen
source in graphical-presentation mode, wait for its actual
prepared demonstration audio, authorize score/audio readiness,
then deliberately withdraw all three physical admission
attempts through `playback.withdraw`. The test resends
both `score_ready` and `demo_ready` four times and advances
the real engine clock; the terminal failure, stopped musical
transport and exact original intent sequence must remain
unchanged. This specifically guards the 167-new-intents
failure witnessed in production and uses the existing
`PracticeEngine`, in-process worker and real Listen
preparation, without mocking a teaching state machine.

### V3 invalid explicit gestures cannot bypass terminal admission (2026-11-22)

The terminal-source latch is now reset only *after* a
new explicit Start/Restart/Resume action passes source,
transition, count-in and fixed-deadline input validation.
Previously an invalid manual command cleared the latch
before checking its own malformed count-in, indirectly
allowing a subsequent asynchronous callback to create
another retry for the old failed score. The existing
real engine test now submits that invalid command,
verifies the error and confirms automatic reentry
remains blocked. A valid explicit action or authenticated
source replacement still creates a new admission budget.

### V3 automatic acknowledgements cannot supersede pending explicit playback (2026-11-22)

`PlaybackCoordinator.request` now treats incoming
`listen`, `score_ready` and `auto` callbacks for the
**same authenticated source/mode/opening** as idempotent while
a previously selected playback intent is still pending.
Previously those callbacks could cancel an already pending
Start, Retry or Resume simply because their action string
differed, replacing the physical offer, count-in and receipt
despite no actual source change or new user choice. The
application's existing owner now returns the pending intent
unchanged for late automatic callbacks, while explicit
new user actions retain their ability to supersede it.
The real `PracticeEngine` fixture asserts unchanged
intent ID, take ID, sequence, stopped status and state
for both score-ready and automatic continuation callbacks.

### V3 explicit UI recovery after bounded failure (2026-11-22)

Added a real worker/UI-intent transition test for the
recovery path after three exhausted physical admissions.
The backend must retain a terminal failed status and
enable the canonical primary Play action. A user-initiated
`ui_primary` with current source fingerprint/revision
must be accepted under the session lock, create a new
distinct source-bound intent beginning at attempt zero,
and remain ungraded until actual physical authorization.
The existing asynchronous Listen/repeat suppression
remains scoped to the failed automatic source; it does
not prevent a genuine new learner request.

### V3 terminal automatic-admission latch (2026-11-22)

The 44980830938 physical trace exposed a separate structural
failure: after repeated rejected Listen reservations, the backend
requested a new automatic Listen intent each time the already
compiled score or audio reported readiness. The three-attempt
admission limit was therefore scoped to one intent, not to
the authenticated source, and the native scene cycled through
167 new Listen intent IDs in 95 seconds.

`PlaybackCoordinator` now binds a terminal automatic-admission
latch to the complete source/hand/revision/mode/opening identity
when a fixed deadline fails, three physical attempts fail, or a
score-preparation timeout expires. Repeated `listen`,
`score_ready` and `auto` requests for that same source are
refused by the transaction owner; `TransportTiming` safely
returns without spawning new intents from repeated asynchronous
readiness notifications. Explicit Start/Restart/Resume or a
genuine source invalidation/exposure change opens a new
budget. The real in-process playback fixture now asserts
four repeated automatic callbacks/ticks cannot create a
fourth intent or clear the visible terminal failure.

Core and full native acceptance on this change remain open.

### V3 native failure: elapsed-time world comparison was invalid (2026-11-22)

The first backend-first native run
[`44980830938`](https://github.com/tpepels/piano_teacher/actions/runs/44980830938)
failed every timed scene: the actual 120 BPM frozen-canvas
preflight offered world 5.574, and its post-arm physical
attestation 33 ms later correctly measured world 5.510.
Both corresponded to the **same** 483.353-second absolute
downbeat (within 1 ms), and the queue generation advanced
from 498 to 499. The Python `PlaybackCoordinator.present`
nevertheless rejected the valid frame because it compared
the two relative world positions as though they must be
monotonically ordered. After each failed authorization
the scene repeatedly retried admission (167 Listen attempts),
never starting music; the native UI and fake MIDI journeys
timed out, while the embedded bridge and relocated package
continued to pass.

That invalid spatial comparison is removed. `present`
still requires a new, fresh physical arm witness, the
correct source revision, nondecreasing queue generation,
the exact backend-chosen physical **arrival timestamp**,
and the same bound segment in the native gateway. A new
real worker regression advances the clock 50 ms between
preflight and arm, submits the correctly decreased world
and requires the single accepted downbeat/segment to
publish that actual committed position. This is a measured
failure correction, not a relaxed MIDI grade/timing policy.
Full native production must be rerun on this new source.

### V3 integrated native production acceptance requested (2026-11-22)

Backend-first V3 transaction code is now integrated across Python and
the Godot `ScoreTransportReservation`, `StreamAdmissionExecutor`
and `ScoreAdmissionGateway` boundaries. A pure renderer feasibility
witness reaches `playback.reserve`, the backend selects the final
musical downbeat, the native gateway commits one exact immutable queue
slot at that returned time, and `playback.present` requires a new
post-arm position/queue-generation/clock attestation before enabling
graded transport. Lost response recovery uses the original
`playback.status` ledger identity and an independently refreshed
physical witness without changing the downbeat.

The core run [44958509113](https://github.com/tpepels/piano_teacher/actions/runs/44958509113)
passed on source `b5e16e97`. This `[native]` checkpoint requests the
full real Godot scene, simulated physical MIDI, real repertoire and
relocated package suite on the same implementation. The V3
integration remains *open* until this native job completes successfully
and all physical receipts are verified against the acceptance trace.

### Phase V3 - Replace distributed playback/admission decisions

**Implement:** Give the existing Python playback transaction owner the
complete state machine for start, Listen, fresh take, automatic repeat,
Retry, Pause, Resume, cancel, expiry, failure and successful commit.
The renderer first reports source-revision-bound physical readiness,
available immutable predecessor/rest/header clearance, viewport geometry
and reservation constraints. The Python scheduler determines the *one*
feasible musical deadline using these constraints and the selected source
tempo map. The native adapter preflights and atomically reserves that exact
source/world/deadline proposal; Python validates the receipt and authorizes
the take only after presentation is bound. Godot retains the physical queue
and monotonic visual math, not deadline/policy selection. Use explicit
`proposed -> measured -> reserved -> presented -> authorized` (or
failed/cancelled) identities with idempotent reconciliation of lost replies.
No speculative grading, sound, admission of another source, or mutation of
committed ink.

**Keep:** Full one-bar count-in for fresh attempts; exact one-bar fixed
auto-repeat without extra gap; a fresh, full authored count-in on every
physical Resume (including Pause during count-in), preserving previously
exposed ink without reusing its absolute origin; full cross-bar releases; differing
tempo maps; long score/slow engraving; temporary unready assets; loss of
reserve/present/status responses. Remove the old gateway deadline
inversion and competing retry/resume decisions after migrating all callers.

**Exit:** V1 embedded scenarios prove that reserve/present receipts are
actually generated by Godot and committed to Python for clean, failed,
paused, resumed and repeated takes. Missing, stale, mismatched or expired
receipts cannot run or grade a take; the UI receives a bounded recoverable
failure, without an endless `admitting` state.

### V4 hold / forecast migration - 2026-11-21

The native visual pipeline now distinguishes **painted** position from
**candidate future**. `PresentationTimeline.forecast_authored` projects
both constant and segmented tempo without mutating the live score or
obeying its Pause hold. `ContinuousScoreFlow` uses that hypothetical
forecast whenever a painted hold is active. Pause remains held while
a Resume intent is merely pending; Free remains held even before its
first guided target has been published. The hold also survives a
pending transition from Free to timed practice, until physical
playback authorization arrives. When the actual admitted source
is authorized, releasing the hold spatially rebases the future epochs
of that authorized segment while retaining their fixed deadlines.
Invalid inverse forecasts are refused rather than silently accepted.

**Current status:** The gateway's deadline-search loop has since been
removed. Native physical clearance is measured through the read-only
timeline inverse; the sole musical deadline is selected and bound by
Python's playback transaction. The V4 hold/forecast integration is
still unverified in native Godot, and the complete MIDI/score/sound
transition matrix and physical acceptance remain open. No new unit
tests were added as instructed.

### V4 backend source-identity regression witness - 2026-11-21

The real `ScoreStatePublisher` is now exercised for a repeated
same-source poll, a direct Free-to-Free window revision change,
and a transport identity change. The source-keyed guided deadline
must remain stable within one window, refuse publication for an
unprepared new source, then generate a new strictly future
`MusicalScheduler.guided` plan. This regression is integrated in
the same Python CI playback module and complements the native
frame-stepped target-cache check. It does not fake teaching policy.

### V6/V7 verified core CI and production window acceptance - 2026-11-21

The GitHub Actions core test run
[`44954792014`](https://github.com/tpepels/piano_teacher/actions/runs/44954792014)
completed successfully after the source-bound fake-MIDI fixture
migration. The CI logs confirm all Python tests, the Godot syntax
gate, and the existing five native behavior scenarios including
`AUTHORIZED_TIMELINE_FAILURES:0`.

The full-scene embedded fake-MIDI acceptance journey now also
examines the ACTUAL immutable physical score queue immediately
after the first Free-to-Tempo transition. It rejects a missing
source and any clipped source strip outside the selected one-bar
practice window (allowing complete sounding tails), regardless
of how much neighboring notation was pre-engraved. A success
marker `FULL_SCENE_SELECTED_WINDOW_OK` is printed with the
bound and actual admitted-strip count. The native-production
GitHub Actions job is being requested by a `[native]` commit.

**V7 remains unclosed** until the native job confirms the complete
embedded score journey, timing, package audit and physical-keyboard
acceptance. A remote synthetic MIDI input exercises the real
production device callback, but cannot attest to the user's physical
keyboard, speakers or platform rendering.

### V1/V4 authored native-frame acceptance gate - 2026-11-21

Added `tests/godot/authorized_timeline.gd` to the existing
`scripts/test-godot-behavior.sh` gate. It advances the real
`ContinuousScoreFlow`, `PresentationTimeline` and
`GuidedPresentationSession` over simulated frame times, asserting
a frozen Pause/Free canvas, side-effect-free constant/mixed-tempo
physical forecasts, monotonic Resume, committed source tempo-map
inversion, and stale Free target reset on a new score revision.
The existing Godot syntax gate now compiles the actual native
score owner and reservation modules instead of relying only on
transitive preloads. This checks invariant behavior without
implementing a shadow piano lesson or grading model.

**Unverified:** The checkout lacks a Godot 4.7.2 binary; the
native gate is committed but has not run in this environment.

### V4 source-scoped untimed Free scheduling - 2026-11-21

`ScoreStatePublisher` now binds its persistent guided target deadline
to the complete source identity (fingerprint, stage key, renderer
revision and transport ID). Opening the next Free window directly
no longer inherits a previous guided deadline from the old window.
The scheduled plan is only published when its identity matches
the source that generated it, so a delayed state snapshot cannot
re-admit an expired prior target. Backend `MusicalScheduler.guided`
remains the single author of the new Free deadline; native Godot
only enqueues its previously authorized physical representation.

**Gate:** The native Free target and connected fake-MIDI advance must
verify the authored plan becomes visible strictly ahead of the
playhead, and that wrong input/no input cannot move it. No physical
acceptance has run.

### V4 full-scene Free failure/silence hold assertion - 2026-11-21

The existing `production_fake_midi_journey.gd` now observes
the actual retained native score world for 350 ms after a
wrong synthetic MIDI input has been recognized by the teaching
controller. During those frames, both the wrong input and
silence must leave the Free target stationary; a diagnostic
`FULL_SCENE_FREE_WRONG_HOLD_OK` marker records the held world.
The following existing Pause and Resume checks still verify
that paused MIDI does not earn credit. This tests real
embedded scene behavior, not a second simulated lesson state
machine. A fresh native-production run is required to accept it.

### V4 idle admission is frozen until an authorized clock - 2026-11-21

The backend presentation projection no longer authorizes running
at the default 40 BPM merely because score assets are loaded.
When neither an active authorized segment nor running transport
exists, it emits `hold` during idle and initial pending admission.
A later successor of a previously authorized take instead emits
`retain`, preserving the preceding source's forward rest/ink
without claiming new timing. The production UI smoke's old
assertion that READY must always scroll was corrected: it now
rejects visual movement only while there is no committed take.
This is a semantic repair to the published authorization model,
with Python fixture coverage for idle, pending and prior-source
successor. The full native acceptance is still required.

### V4 protocol schema synchronized with semantic motion owner - 2026-11-21

The new backend `presentation_directive` key was initially
published without being added to the versioned state schema, a
real cross-language contract omission. `state_contract.VERSION`
is now 5 in both Python and the generated Godot mirror, with
a typed dictionary entry for the motion directive. A real
`PracticeSession.snapshot` regression checks that the
application publishes one of the four supported directives
and that every state field satisfies the declared protocol.
The embedded native logger therefore validates the *actual*
application view model instead of silently treating this key
as unknown.

### V4 backend-only motion and Free target decisions - 2026-11-21

The authoritative `ScoreStatePublisher` now projects a source-bound
`presentation_directive` with one of `hold`, `retain`, `target`
or `run`. Pause, unloaded/unready score, untimed Free phases,
the earliest expected musical note and pending timed successors
are interpreted in Python under the existing application state
read transaction. `GuidedPresentationSession.update_hold` now
interprets only that explicit directive and its native world-space
target binding. It no longer determines learning phases or
re-examines `teaching.expected_notes` to choose which MIDI note
stops the physical bar. A missing/unknown directive fails closed
to a frozen score.

The same backend projection is covered by a new Python table of
held Free, paused, unready, pending-admission and running scenarios.
This is a material removal of duplicated lesson policy from Godot,
rather than a code move. Existing physical frame owner still decides
how to draw/rebase the immutable authored score after authorization.
Native acceptance on this revision remains unverified.

### V4 prevent successor-BPM corruption of an authorized predecessor (2026-11-22)

`PracticePresentationSession.accept` no longer feeds a pending
next stage's uncommitted nominal BPM directly into
`PresentationTimeline.set_rate` when an earlier segment owns the
visual world. `ContinuousScoreFlow.sample_uncommitted` now samples
an existing authorized segment from its immutable tempo epochs,
and uses the projected BPM only for an unbound initial source.
This fixes a remaining cross-source rate writer that could
speed up or slow down previously admitted notation before the
successor had an authenticated physical reservation. The
actual Godot timeline behavior gate now tests an old 40 BPM
segment surviving a new uncommitted 120 BPM stage snapshot,
while fresh unbound initialization still accepts 72 BPM.

### Phase V4 - Make visual time obey authorized state

**Implement:** Convert the native `PresentationTimeline` into a projection
of authorized musical/visual epochs and explicit hold/release directives
from the canonical state. Eliminate the ability of an idle/unready
presentation clock or fallback BPM to advance visible source ink. Free
waits at its current target until a correct MIDI event; wrong input and
silence do not move it. Pause freezes visible ink, targets, metronome and
audio in Listen, Free, count-in, timed take, between attempts and during
source readiness. A pending Resume may forecast *unexposed* geometry
without releasing the displayed hold; the hold releases only when the
correct resume transaction is authorized. Prevent backwards jumps,
half-drawn strips and new visible notes during Pause.

**Exit:** Deterministic frame-stepped Godot checks verify unchanged visual
world/source identities across arbitrary idle time, Pause, delayed replies
and failed Resume; only authorized outcomes move it. Timed notation,
count-in, audio scheduling and grading share the same accepted take epoch.
Exactly the selected one-to-four authored measures remain visible, with
original closing barline, dim opposite hand and complete sounding tails;
the final exam intentionally shows its full selected piece.

### V5 source-bound saved lesson navigation - 2026-11-21

The resume prompt's “Review 2” button now sends a raw
`ui_review_previous` intent, its original fingerprint and source
revision. The UI no longer computes `select_step = old_step - 2`
from a stale saved display snapshot. `PracticeControls` rejects a
prompt belonging to an older piece/revision under the command lock,
then the shared Python control projection resolves the previous
lesson number from the *current* backend learner cursor.
Backend success navigation recognizes the new raw intent.

This closes one concrete stale-navigation responsibility in the
screen, without adding a second UI-side course policy.
No new unit tests; modal/real keyboard acceptance is outstanding.

### V5 sound ownership tied to authorized take - 2026-11-21

The metronome's reserved spoken count-in now stores the authorized
`take_id` and requires the first confirming backend state to match
that exact take. Numeric deadline/BPM agreement alone no longer
permits a superseded source to speak its old countdown.
An explicit user Stop still silences pending local audio immediately
as a physical safety effect; this does not schedule, grade or decide
a transport transition. All other command completion/failure
cancellations remain exclusively state-driven.

### V5 eliminate speculative command effects - 2026-11-21

`PracticeCommandCoordinator` no longer uses the last published
primary-button action to cancel metronome cues or decide whether to
send native physical clearance. Its only local projection of that
action is the pending-button caption and click-queue UX. The native
adapter sends physical facts for raw gestures that can start, retry
or resume; the Python session lock interprets the actual action.
The metronome continues to reconcile with the authorized take and
is not cancelled by an unrelated failed command. A Pause requested
while another command is pending stays `ui_pause` rather than
being transformed into an explicit stale `pause` operation.

Other screen-side effects and physical acceptance are still open.
No new unit tests added.

### V5 retired control-policy owner - 2026-11-21

The superseded Godot `practice_control_policy.gd` is removed. Its
production consumers and the existing Godot control presentation
fixture have been migrated to the backend-published `controls`
contract and `ui_*` intent dispatch. The existing Godot syntax gate
checks the actual command coordinator, physical admission gateway,
presentation timeline, guided hold and presentation session instead
of compiling the obsolete policy. No duplicate fallback remains.

V5 remains open for the native effect-coordination audit, production
integration and physical acceptance. No new unit tests were added.

### V5 advanced Pause uses the same authenticated raw gesture - 2026-11-21

The advanced Pause sheet formerly emitted the explicit
`practice.command(action="pause")` based on a UI snapshot.
It now checks the backend-published Pause availability and
emits the same `ui_pause` gesture used by the main button and
keyboard shortcut. Python resolves that gesture under its
session lock. The sheet retains only UI visibility, not
application transport authority; a disabled/stale source
cannot bypass the canonical control policy through the
advanced menu. Native UI acceptance remains required.

### V5 accepted command result is owned by the backend - 2026-11-21

`practice.command` now returns a typed version-1 envelope
`{state, outcome}`. The outcome identifies the actual action
dispatched under Python's session lock, whether it executed,
and its view-side navigation/settings/lesson-invalidation
effects. Godot validates that outcome, uses the accepted effects,
then forwards only the unchanged state body to the versioned
application state inbox. It no longer reconstructs action
semantics from a potentially stale displayed button label.
`CommandSuccessPolicy` has deleted its separate guided navigation
and calibration action sets. The Python fixture unwraps state
for existing tests, and additional regression cases verify
a real resolved `ui_pause` action plus the pure effects policy.

This is a cross-language contract replacement, not a relocation
of the native navigation branch. Core and native acceptance on
this revision remain outstanding.

### V5 preserve raw MIDI edge suppression across lesson transitions (2026-11-22)

After moving the action decision into Python, `ApplicationInputSession`
now retains the prior **phase identity as an input-debounce generation**
alongside the accepted action/revision. A single key that completes a
lesson transition cannot be mistaken for a separate Start gesture
when the previous and next phases happen to publish an identical
action label. The phase string is only compared for input freshness;
it never selects Start, Retry, Pause or teaching progression in
Godot. Python remains the sole source of `controls.midi_start`.

### V5 physical MIDI-start shortcuts are backend-owned - 2026-11-21

`ApplicationInputSession.observe_midi_state` no longer inspects
lesson phase, practice mode, or automatic retry flags to decide
between Start/Restart/primary. It now checks only the freshness
of a received MIDI event, the stability of its source revision
and backend-published control action, modal suppression, and
score readiness. It sends one raw `ui_midi_start` gesture.
`control_projection` now publishes `controls.midi_start`
using the same authoritative phase/learning/transport state
and the existing locked `resolve_ui_intent` rejects stale or
unavailable requests. The command coordinator includes native
physical clearance facts for this raw gesture without knowing
whether it means start, retry or a guided transition.

A single parametric backend test checks first Play, Perform,
manual Retry, auto Retry, playing, count-in, Listen and Free.
This closes another independent native application-policy path.
Actual MIDI input debouncing remains a physical-adapter concern.
Native production acceptance is still required.

### V5 MIDI shortcut instructions now follow backend availability (2026-11-22)

`PracticeScreen` previously rebuilt an implicit MIDI
Start/Retry/Next teaching policy from phase/mode/auto/device
conditions merely to display "play one key" instructions,
despite the input adapter already consuming backend-owned
`controls.midi_start`. It now displays those hints only
when that exact accepted control is enabled, and formats
copy from its resolved action rather than guessing from
lesson state. This also removes a misleading "play one
key to continue" prompt in default Practice Flow's
automatically advancing Free completion, where the
backend correctly authorizes no such MIDI shortcut.
A canonical projection regression distinguishes
explicit standalone Learn from auto-advancing course Free.

### Phase V5 - Reduce Godot screens to presentation and raw intents

**Implement:** Change `PracticeScreen` and `PracticeChrome` to render the
canonical control/lesson/feedback projection and emit raw click/keyboard/
MIDI-shortcut intents only. Delete the phase-string command decisions from
`PracticeControlPolicy` (or retire that policy entirely); eliminate
duplicate Play/Pause enablement, tempo permission, retry and Listen rules
in widgets, `PracticeCommandCoordinator` and screen side effects.
`PracticePresentationSession`, `PracticeFrameCoordinator`, visual effects,
native score view and audio adapters may sample/present accepted frames
and report physical facts; none may select a new learning transition,
deadline, grade or action. Reduce `main.gd` to composition, event wiring
and screen navigation. Move semantic decisions to actual application
owners; do not just relocate large conditional blocks to another Godot
service or a generic context object.

**Exit:** Every control shown by the real UI matches the backend's
published availability and emits the intended command under all documented
phases. The same projection drives both button and physical-shortcut
semantics. Hidden/disabled controls cannot bypass policy via another
entrypoint. Existing settings, library, source picker, corrections and
history screens still function.

### V6 one physical take per worker acknowledgement (2026-11-22)

The full-scene synthetic-keyboard journey now checks the
canonical `fingerprint|revision|transport|mode` source binding
against the actual native queue. At first one-bar Tempo it
requires **exactly one active source strip** for that authorized
take, with the complete selected-window bounds; old
Listen-source strips may exist independently. The failed
same-tempo automatic retry must allocate exactly the next
transport ID, and the following clean 40→48 BPM repeat
must allocate exactly one more. These assertions also
run during the injected lost-reserve and lost-present
ACK scenarios, detecting duplicate score admission or
double-executed worker transitions that a generic
`running=true` result would miss.

### V6 real worker lost-ACK recovery fault injection (2026-11-22)

Added a strictly opt-in test seam in `InprocessRequest.complete`
controlled by `PIANO_TEST_DROP_REPLY_ONCE`. It discards the first
**successful** `playback.reserve` or `playback.present` callback
*after* the real embedded Python worker has already applied that
operation, then returns a transport-level failure to the actual
`ScoreAdmissionGateway`. No alternative playback, grading,
renderer or state machine is constructed; the gate must recover
through the original `playback.status` ledger and retain the
same exact take/segment/downbeat. Normal desktop behavior has
no injected failure unless the explicit test environment variable
is set; each process drops at most one named operation.

`scripts/verify-embedded-production-local.sh` now runs the
full real `production_fake_midi_journey.gd` three times: normal,
one lost reserve acknowledgement, and one lost present
acknowledgement. Each uses isolated persisted session state and
a distinct synthetic MIDI port, and the acceptance wrapper
requires the `NATIVE_TEST_DROPPED_REPLY:<operation>` marker
to prove the fault actually occurred. Wrong Free, Pause, Resume,
failed Tempo, clean Tempo, exact 40→48 BPM repeat and native
score bounds must all still pass in the same session.
These full native cases are unverified until the new gate runs.

### Phase V6 - Complete transition coverage, harden CI, delete legacy paths

**Implement:** Extend the V1 runner into a data-driven, deterministic
transition matrix, driving *both* successful and unsuccessful simulated
MIDI and observing authoritative and native-visible outcomes:

| Path | Success witness | Failure/edge witness |
| --- | --- | --- |
| Load -> Listen | Correct first window, authentic sound/score readiness, ungraded playback | Missing/stale assets, lost reply, listen audio error |
| Listen -> Free | Automatic handoff, complete window target at fixed playhead | Pause, disconnect, no tempo/no input, wrong input |
| Free -> Tempo | Correct pitches/chords advance one target at a time, full selected window | Wrong/extra/missing key, partial chord, release, interrupted Free |
| Tempo attempt | Count-in, correct attacks, clean grade and +10% target-speed ladder | Wrong/missing/extra/early/late notes, opted-in hold errors, no input |
| Repeat/recovery | One-bar gap, safe source reservation, same or lower tempo, return to Free | Expired deadline, immutable overlap, failed reserve, second floor return and Coda/Fukuda |
| Pause/Resume/Retry | Exact source/take semantics, frozen score/grade, one authorized restart | Pause during count-in/Free/Listen/admitting, duplicate Pause, delayed receipt, interrupted Resume |
| Window/hand progression | 1; 2; 1-2; 3; 2-3; 1-3; ..., right -> left -> together; independent progress | Empty hand, skipped window, extra visible measures, held note crossing barline |
| Final and persistence | Whole-piece final at 50% -> target, two clean target runs, saved Free reopen | Failed final, restart, reopen interrupted take, no false mastery |

For every edge assert: current mode/hand/window/tempo, accepted available
action, authorization/receipt identity, what the user would see (stationary
or scrolling and exact measure bounds), correct/wrong note feedback, audio
timing facts and persistence when relevant. Exercise tempo-map and meter
changes, long rests, ties, low BPM, multiple MIDI events at one timestamp,
lost/delayed/duplicate/out-of-order replies, disconnect/reconnect, render
failure, stage promotion, resizing and source change during pending work.
Include both note-on and note-off, and hold grading on/off. Use real MIDI
fixtures and deterministic fakes at hardware/time seams only.

**CI (manual-only since 2026-11-22):** Run the bounded fast matrix only on explicit local execution or GitHub `workflow_dispatch`; run real embedded
Godot/bridge/render/admission journeys and relocated package boot in the
native-production gate. Fail on `SCRIPT ERROR:`, admitted-score refusal,
unexpected error logs, unhandled exceptions, wrong final state,
wrong source visibility or nonzero scenario failure counters, even when
Godot exits zero. Preserve traces, revision and scenario ID for every
failure; do not treat absent mandatory dependencies as skips, rely on
hard-coded sleep or leave positive-path simulations using fabricated
reservation receipts. Keep useful existing feature tests; retire tests
that assert superseded behavior without weakening the corresponding
player-observable checks.

**Exit:** All enumerated state/action/MIDI outcome combinations have a
passing deterministic witness at the appropriate real boundary, CI core
and native production are green on the same source revision, and an
ownership sweep finds no remaining legacy practice policy/clock/deadline
owner in UI scripts. Update `docs/architecture.md`, `docs/development.md`
and this table with exact evidence and deleted paths.

### V7 complete checked-in MIDI native-source audit (2026-11-22)

Expanded `scripts/verify-embedded-production-local.sh` to
automatically execute `production_ui_smoke.gd` (real Godot scene,
embedded Python, native Verovio engraving, immutable source queue
and Play/Pause/Resume) for **every checked-in `midi/*.midi` source**
in stable filename order. This replaces the limited Peace Piece
and Chopin generic list; Moonlight retains its separate, more
demanding real lesson-navigation journey. Each corpus source
receives a separate isolated XDG state and case log, continues
after a failed source instead of silently skipping the remainder,
and is included in the strict aggregated native gate result.
The script emits `NATIVE_REPERTOIRE_CORPUS_CHECKED` for auditability
and fails an empty corpus rather than appearing green.

This is a broader actual production renderer/queue audit,
not a claim that the user's separate Pathétique source or
physical Kawai keyboard is available in the checked-in corpus.
Final/full native CI must pass on this revision before
repertoire coverage is accepted.

### Phase V7 - Integrated release and connected-piano acceptance

**Implement/verify:** Run `bash scripts/test.sh --coverage`, the complete
embedded native/repertoire verifier, strict relocated package build/boot
and real-score journeys (including Pathétique II). Exercise startup,
MIDI device connection, loss/reconnect, opening a new piece, every
Listen/Free/Tempo path, repeated successes and failures, changing tempo,
Pause/Resume in every mode, automatic retry, growing windows, final,
settings, save/reopen and sound. On the actual Kawai CA49, compare
physical key on/off, headphones/speaker audio, the scrolling staff,
count-in, wrong-key marks and all one-to-four-bar clips against
`docs/practice-flow.md`. Verify stationary Free and Pause with a long
real-time hold; verify no additional visible measures. Check a separate
clean-machine Linux installation instead of inferring compatibility from
same-host isolated HOME.

**Exit:** All V0-V6 phases are closed with implementation commits, passing
same-SHA core and full native CI, no runtime exceptions, unambiguous
production trace evidence, and connected-piano/clean-machine acceptance
recorded separately by the person running those checks. If hardware or
second-machine access is unavailable, mark V7 *open*; never claim it
from simulation. No provisional acceptance for the failed Pathétique
session until the failure is reproduced and corrected.

### Execution and reporting rules for V0-V7

- Work only on `main`; make coherent commits, never rewrite user history.
  Record baseline SHA, per-phase source SHAs, actual files and responsibility
  moves, removed compatibility paths, passing/failing scenario IDs,
  relevant logs, runtime/size diagnostics, and separate physical gates here.
- A phase is complete only when **all** listed functionality is integrated,
  affected consumers migrated, superseded paths removed, and that phase's
  end-to-end checks pass. Do not equate a code move, mocked backend test
  or partial implementation with closure. Report unverified scope explicitly.
- The user's 2026-11-21 request for fake-MIDI success/failure transition
  testing authorizes *player-visible* regression coverage in this roadmap.
  Follow `AGENTS.md` otherwise: no abstract implementation-shape, pixel,
  infrastructure or duplicate-engine tests; do not silently change the
  practice-flow contract. Physical MIDI/audio/visual acceptance stays
  separate from simulation.
- Never add a second application state machine in the test runner. Tests
  inject events and assert observable outputs of the real one.
- If a phase exposes a wrong boundary, replace it, including across
  Python/Godot, instead of preserving it via a compatibility layer.
  Any change to the player's specified behavior requires explicit approval.

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

## PracticeEngine architecture replacement: implementation and acceptance (2026-11-21)

**Status: S0–S7 source migration complete and existing core/native/package software gates passed on `daf466e6`; physical and independent clean-machine acceptance remain open.** Baseline: `f8bd9cd`; `piano_teacher/server.py`
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

**Accepted software source:** `daf466e6` on `main`;
[core and full native/package run 44907200749](https://github.com/tpepels/piano_teacher/actions/runs/44907200749)
passed both jobs. Core: **103 passed, 4 skipped**, informational
Python coverage **73.6% lines / 53.3% branches**, Godot syntax OK,
all four executed Godot behaviour groups with zero failures. Full
production acceptance includes embedded Python/native registration,
authentic score loading, default and repertoire/control journeys,
two `PACKAGE_CONTENTS_OK` checks, and the strict relocated standalone
package boot ending with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`.
Commits since `daf466e6` modify only documentation and do not
change the runtime source. Physical instrument/graphics/audio inspection
and installation on a distinct clean machine remain unverified.
The earlier full gate on `9fef7780` passed as recorded in run 44905418627
but is superseded by this final exact-source verification.

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

**S1 command-context ownership completion:** Both public action
transactions and Resume's internal score-ready acknowledgment now use
`SessionCommands.reason(...)`, a single owner-managed context manager
that restores the outer command reason even on exceptions. The application
services no longer assign directly to that state. This removes the last
independent reason-writer/restore pattern without adding another command
router. Core and full embedded/native/package acceptance are required.

**S1 further owner-source audit:** `PlaybackSession` still directly
cleared three `AttemptRuntime` review flags, assigned its Recorder on a
failed capture start and wrote `VisualTransport.pending_rewind`.
Those remaining mutations now use `AttemptRuntime.begin_timed_review()`,
the existing `suspend_recording()`, and
`VisualTransport.finish_rewind()`. The caller's existing order and
exception handling remain intact. No other direct
`self._attempt`/`self._transport` field writers remain in
`PlaybackSession`. Integrated native/package verification must rerun.

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
  frozen pause time and score, count-in, and forward continuous scroll while
  unpaused. No cold asset
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

**S7 complete runtime dependency scan (2026-11-21):**
All **193 production Python modules** were checked for obsolete server,
HTTP/socket, parallel renderer, headless-fixture and MusicXML source
indicators, and all **146 production Godot scripts** (excluding the
dev-only MCP addon) were scanned for the same obsolete native/transport
patterns. The only relevant matches are the intentional
`inprocess.py` import of the public facade, the explicit headless
`score_queue_next` schema (not desktop admission), internal
MusicXML/research expression handling and historical-data coverage
labels/comments. No unintended alternative active runtime route was
identified in this scan. The project config has no developer MCP autoload,
and packaging removes the editor-only addon. This is a targeted source
pattern and import audit, not proof against arbitrary dynamic behavior.
Core and native/package gates passed at `daf466e6`.

**S7 comprehensive application direct-writer audit (2026-11-21):**
All **77** current `piano_teacher/application/*.py` production modules
were inspected for cross-owner direct writes to the visual transport,
attempt, settlement, playback, selected source/lesson and scored MIDI
state (including private `_attempt` / `_transport` references).
The last actual offenders were repaired in `9df6a1ae`,
`0a688d5b` and `daf466e6`; the final 77-module scan found zero
remaining direct assignments matching those owner-write patterns.
This covers explicit Python attribute assignments, not arbitrary
dynamic introspection or physically observed graphics. On
`daf466e6` core CI passed; the complete native/embedded/repertoire
and relocated-package software gate is being verified separately.
No new tests or alternate renderer or source policy were introduced.

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

## Post-S7 persistence boundary — learning evidence (2026-11-21)

Source commit [`8eccd16e`](https://github.com/tpepels/piano_teacher/commit/8eccd16eb1b5ea7fa80ef43b56e7fe955925013e)
separates the previously 733-line `LearningLedger` into an explicit
414-line transactional evidence owner, shared canonical JSON/privacy encoding,
SQLite schema/accounting trigger setup, independent detail-budget retention,
and atomic/redacted export. The ledger composes these connection-scoped owners
on the **same** SQLite connection: nested `sqlite_atomic` savepoints,
crash recovery, legacy data import, replay identities, the public history
API and the single authoritative source of assessments remain unchanged.
No architecture-only, pixel, infrastructure or new regression tests were added.

[Core CI run 44908940976](https://github.com/tpepels/piano_teacher/actions/runs/44908940976)
on the source commit passed **103 Python tests, four skips**, Godot startup
parsing, and four existing native behaviour groups with zero failures.
The opt-in embedded native/repertoire/standalone-package gate is separately
running on that same source revision; it must pass before this follow-up is
claimed fully software accepted. Physical MIDI/audio, visual inspection and
installation on another clean target machine are not covered by CI.

Current three largest production source files by bytes after extraction:
`notation/lesson.py` (43,054), `godot/settings_screen.gd` (36,961), and
`godot/practice_screen.gd` (34,101). These remain diagnostic review targets;
size alone does not authorize moving their responsibilities.

### Native visual-effect runtime exception and gate correction

Inspection of the nominally successful full native runs found **239** Godot
`SCRIPT ERROR` lines in [run 44907200749](https://github.com/tpepels/piano_teacher/actions/runs/44907200749)
and **229** in [run 44908940976](https://github.com/tpepels/piano_teacher/actions/runs/44908940976).
All were an invalid access to `PracticeScoreStage.impact_callout` from
`score_effects.gd:19`: the deleted callout was still referenced whenever
ungraded Listen/preview mode was accepted. The processes returned zero and the
old runner incorrectly marked those player journeys passed. Those green jobs
are **not clean native UI acceptance evidence** for that error path.

Source commit [`03de4498`](https://github.com/tpepels/piano_teacher/commit/03de44984438700ca70a38fe517121b487ab331c)
removes the obsolete access. The same existing native acceptance script now
fails each actual Godot journey if its log includes `SCRIPT ERROR:`, even when
the process exits zero; independent cases still run and are reported. No new
test scenarios were added. [The corrected full gate](https://github.com/tpepels/piano_teacher/actions/runs/44909630866)
was started on that source; a final green outcome with zero script exceptions
is required before closing this correction. Physical rendering and MIDI/audio
acceptance remain unverified.

## Pause and current-window display correction — 2026-11-21

Following physical-use feedback that Pause did not stop the moving staff,
that Free continued scrolling without tempo, and that extra measures appeared,
the renderer/control paths were corrected on main:

- [`d1ba66e5`](https://github.com/tpepels/piano_teacher/commit/d1ba66e5fee8e2c941f5b465d60a5952642ced4a)
  freezes the canonical visual projection on an acknowledged Pause, aligns the
  visible Play/Pause decision with backend-pausable phases, and clips each
  admitted score strip to the **selected** authored window. Context remains
  available to the pre-engraving source but not as additional visible bars.
- [`098ff955`](https://github.com/tpepels/piano_teacher/commit/098ff95519695a5227f682f59501d5f09ca4b7ac)
  also maintains the Free target hold throughout `introducing`,
  `disconnected` and completion transitions; these untimed phases can be
  paused through the same backend transport authority.

- [`9eec8103`](https://github.com/tpepels/piano_teacher/commit/9eec8103842a21df927950f5d0592649743365cf)
  gives the Python Free teaching controller the same Pause/Resume lifetime
  in `guided_wait`, `introducing` and `disconnected`; device changes cannot
  silently unpause a frozen controller.
- [`fc65791f`](https://github.com/tpepels/piano_teacher/commit/fc65791f5d6750cfc42c29cb3e2ce787213d42b1)
  prevents neighboring context-role notes and headers from being painted in
  native selected-window strips even when engraving margins overlap them.
- [`b37e7693`](https://github.com/tpepels/piano_teacher/commit/b37e7693076ef4e8059458465d353be5c0559ae6)
  retains the selected window's authentic closing barline (including authored
  repeat styles) without showing the following measure.

**Native acceptance and Resume correction.** The first full run,
[44922019745](https://github.com/tpepels/piano_teacher/actions/runs/44922019745),
failed four scenes because two existing acceptance scripts still expected the
previous moving-during-Pause behavior. The scripts now assert a stationary
score and no new admission during Pause ([`1948651a`](https://github.com/tpepels/piano_teacher/commit/1948651ac82c3d536b2e723d2749f41914b1c17b)).
The following full run,
[44922940896](https://github.com/tpepels/piano_teacher/actions/runs/44922940896),
exposed a **real Resume deadlock**: the backend remained in `admitting`
after Pause with no graphical receipt. Source `ae20d6c4` reconciles the
canonical hold in every presentation frame rather than only at a snapshot.
Source [`81ae006f`](https://github.com/tpepels/piano_teacher/commit/81ae006ff186ce9a6bce39f0293b0d2510390e40)
releases the visual hold when an explicitly pending Resume intent is being
admitted. The backend intentionally retains `paused=true` until authorization;
holding the visual world throughout that admission made the deadline inversion
unable to reach any future source. No separate clock or alternative admission
path was added. Existing acceptance failure witnesses were extended in
`9312b83c` (no new test scenarios).

**Final source acceptance:** [GitHub Actions 44925026112](https://github.com/tpepels/piano_teacher/actions/runs/44925026112)
passed on source `81ae006f`: **103 Python passed, 4 skipped**,
Godot startup and all four existing native behavior groups passed with zero
failures, embedded CPython/native registration succeeded, production
Play/Pause/Resume succeeded, Moonlight/Peace Piece/Chopin journeys succeeded,
strict relocated standalone package contents and boot succeeded, and there
were **zero Godot script errors**. No new tests were added; two preexisting
production scripts were updated to the current Pause contract.

A real piano is still needed to verify immediate Pause/Resume feel, whether
Free remains stationary while thinking, and that source cropping shows exactly
the selected window on screen. No physical, audible or visual success is claimed.

## Physical MIDI session incident — 2026-11-21

The player's Arch Linux / Godot 4.7.2 session on source `9312b83c`
(pre-`81ae006f`) opened Beethoven's *Pathétique* II with a connected piano.
The supplied runtime log contains **10** graded-MIDI `SCRIPT ERROR` exceptions
caused by the removed `PracticeScoreStage.impact_callout` property, and **78**
refused immutable score admissions paired with **78** preflighted
`SCORE_TRANSPORT_COMMIT` failures on an automatic exact repeat. This is a
real production failure despite green automated CI on other music.

Corrective commits on `main`:

- `fc299322`: remove the removed `impact_callout` call from
  `LiveMidiFeedback`; retain `effects.react` and ledger-owned ink.
- `5b6fb3b3`: read printed rest/header geometry from the matching ready
  renderer and forward it in `score_ready`, Play, Retry and Resume commands;
  Python installs it before automatic future deadlines are selected.
- `907f29ad`: make fixed-repeat preflight account for physical printed
  rests and use the existing safe announced-empty-strip policy; committed
  notation and the backend deadline remain immutable.
- `3b3b5a25`, `73adfb7e`: report the actual queue refusal and source
  coordinates; correct the diagnostic's initial Godot syntax error.
- `87a41370`: correct an obsolete assertion in the **existing**
  score-stream checks that allowed an overlap with committed rest ink.
- `584f017a`: fail the **existing** full-native positive journeys on
  score-queue/preflight/commit runtime errors even if Godot exits zero.

No new tests or fixtures. **Full [GitHub Actions run 44927279888](https://github.com/tpepels/piano_teacher/actions/runs/44927279888)
passed on source `584f017a`**: 103 Python tests passed, four optional
skips; Godot startup syntax and all four existing native behavior groups
reported zero failures. Embedded Godot/Python registration, production
Play/Pause/Resume, Moonlight Sonata Retry/Listen/navigation, Peace Piece,
Chopin Nocturne, and relocated standalone package boot/contents all passed.
The stricter positive-journey gate reported no rejected immutable source
admissions or Godot script exceptions. Documentation commit `9877ea93`
also passed its core CI gate. **The actual physical Pathétique MIDI session,
sound and visual layout have not yet been re-tested; green software CI
does not establish those outcomes.**

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
