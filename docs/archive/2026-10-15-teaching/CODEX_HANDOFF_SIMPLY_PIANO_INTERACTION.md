> Historical document preserved on 2026-10-25. This describes an older revision; current source and tests take precedence.

# Codex Handoff - Simply Piano-style learning interaction for Piano Teacher

**Scope: learning method, interactive feedback, lesson UI, transport modes. NOT songs/catalogue/preloaded exercise content.**

**Repository:** `tpepels/piano_teacher` (Godot 4.7 + Python on Arch Linux). Baseline inspected: `66faf823bf50fc9b7d8e522e0d682481ee761203` on 2026-10-15. **Fetch latest main at start and rebase your work if newer; previous commits can arrive while you work.**

**Input assets:** `moodboard.png` in repository root is the approved **low-glare dark theme**; preserve that design language. Read `SIMPLY_PIANO_INTERACTION_GAP_ANALYSIS.md` (if copied alongside this handoff) for evidence, source links and comparisons. Research sources are also listed at the end of this file.

## Mission

Our app already imports arbitrary MIDI/MusicXML; generates skeleton, outline and original exercise variants; renders real notes with Verovio; follows a Python-authoritative beat clock; assesses MIDI events; performs delayed five-error rewinds and 10% tempo recovery; saves progress; and has a dark UI. Do **not** revert to a MIDI visualizer, reintroduce white UI, or replace the tested playback system gratuitously.

The missing product is **a guided piano teacher**. Separate (a) acquiring a note with hints, (b) practicing it with musical time, and (c) performing without interruptions. The user needs to understand exactly what to play, when, why an exercise repeats, and what happens next. Do not invent a library of proprietary Simply Piano material: all activities are generated from the user's imported MIDI.

### The user-defined interaction rules (preserve)

- A **short moving count-in** before each timed attempt, tempo-capped to approximately 4 seconds at slow BPM. Music approaches a fixed timing line *during* count-in. No giant 1-2-3-4-5-6 overlay.
- At **five distinct wrong/missed required notes** over a recent two-measure span, **finish the current musical two-bar chunk**; then provide feedback and repeat from the relevant boundary. Do not stop mid-attack.
- Slow by **10%** after failure; a clean performance raises tempo toward the current chosen target in steps. Do not override a user-selected target BPM.
- Require **three consecutive clean full attempts at target tempo** to master an exercise. A slowed take, hinted take, no-device preview or partial retry never falsely awards full mastery. Make current streak visible.
- Autoplay successive attempts with a brief, visible, nonblocking break. Student can always pause/stop/restart/navigate.

These thresholds are *our* product choices, not verified Simply Piano internal constants.

## Verified Simply Piano interaction principles

Official 2026 help center documentation describes:
1. **Teach Me:** a series of short exercises leading to a moving full-song stage.
2. **Live feedback:** correct without hint / correct after a hint / wrong use distinct colours. An on-screen keyboard appears when needed, shows notes heard, and highlights the expected key.
3. **Wait-for-note Practice option:** the next note does not advance until the right note is played (documented for Song Library on iOS).
4. **Manual practice controls:** tempo, RH/LH/both, restart, metronome, optional Listen and seek, dependent on platform.
5. **Automated error help:** historical official documentation describes entering slower metronome practice after repeated mistakes and returning to normal tempo after mastery.

Do **not** assume exact proprietary algorithms, universally available platform controls, or that every Simply Piano lesson is a moving-score exercise.

## Current repository and preservation constraints

Read, at minimum:
- `ROADMAP.md` and `docs/verification-2026-10-15.md` first.
- `godot/main.gd` and `godot/practice_theme.gd` (current dark styling, transport and visual overlay).
- `piano_teacher/server.py` (`PracticeEngine`, `/state`, `/control`, `/lesson` and score revision acknowledgement).
- `piano_teacher/learning.py` (`LearningPlan`, stage levels, consolidated sections, mastered steps, migration).
- `piano_teacher/exercise_generator.py`, `lesson_score.py`, `lesson_validation.py` (the exact note set shared by rendering/grading).
- `piano_teacher/practice.py`, `live_feedback.py`, `recovery.py` (pitch/timing/duration and sliding-window evaluation).
- `scripts/check_visible_playback.py`, `scripts/check_desktop_ui.py`, `scripts/smoke_adaptive_godot.py` (real software-rendered evidence).

At the inspected commit `66faf823`, local verification claims 207 Python tests passing, real desktop score movement at 30/40/80/120 BPM, dark UI inspected at multiple window sizes, and a consolidated Merry-Go-Round-of-Life curriculum of **301 stages instead of 1,209**. Those are **reported tests**, not acceptance of the user's physical USB piano; physical latency/speaker tests are outstanding. Do not undo these fixes. Re-run tests against fresh HEAD and report new counts, not stale ones.

## Proposed student experience

There are three clearly named **interaction modes**. These are *our* design framework, not a claim about Simply Piano's labels.

### Mode A - LEARN: note-by-note guidance (NEW; highest missing feature)

- Show 1-2 measures, or even a single pattern/chord, generated from the **active** lesson variant.
- Introduce the pattern with a one-sentence goal: e.g. `Right hand · Learn the melody outline · 6 notes`.
- **No advancing wall-clock cursor**. A target note or chord is highlighted. The user plays the correct keys; advancement happens **on correctly recognized input**. Chords must recognize required pitches together within a configurable window, not just whichever key arrives first. Held notes and repeated pitch attacks require explicit treatment.
- After a first mistake or a short configurable stall, show a subtle **virtual piano keyboard** below the staff: current expected pitch(es) gently highlighted, played keys shown separately; give helpful note names/octaves (C4 etc.). Don't show hints immediately when the student is succeeding. Make optional persistent hints available.
- Correct without hint -> distinct restrained success state. Correct after hint -> separate assisted state. Wrong -> distinct but not flashing/scolding. Do not advance for the wrong key; ignore unrelated MIDI noise safely.
- Guided mode should be tolerant of slow playing; it teaches pitch/key location. Rhythm is introduced in timed Practice, not graded harshly while waiting.
- User may Listen to the short idea, Retry, Skip explanation, Switch hand, or choose Practice when ready. Guided completions can prepare the user for timed practice but cannot count as clean target-tempo mastery.
- Disconnecting MIDI immediately surfaces `No piano connected — timed preview only`, without allowing false progression.

### Mode B - PRACTICE: timed passage + feedback/recovery (REFINE)

- The same displayed notes must be exactly what `PracticeEngine` grades. Use the existing monotonic Python transport (`clock_beat`), never a second Godot song clock.
- The **score translates continuously** under one fixed, visible timing line. During short lead-in, blank measures move too. Keep notes visible at normal screen size. Use source/geometry coordinate transforms already validated; only refactor if evidence demands it.
- As notes cross the timing line, resolve their state: expected, correct, assisted, wrong, missed, early, late, short/long. Avoid showing `missed` before the scoring grace window ends. Show live success and late/early on noteheads; brief, optional summary at bottom. Ensure MIDI note matching supports same-pitch repetitions and simultaneous chords.
- Failed 2-bar chunk -> finish boundary -> ~1-2 seconds `Let's retry bars N-M · slower at X BPM` -> automatic short moving count-in -> retry. Optionally return the learner to guided LEARN when mistakes persist in the same pitches. Keep the user informed about *why* the change happened.
- A clean partial recovery is a useful success, but then resume longer passage; it is not full mastery. Clean full runs at target BPM fill `1/3, 2/3, 3/3`.
- Resume on the *same* exercise and tempo after an ordinary pause; explicit Restart creates a new attempt.
- Provide a true audible **Listen** mode for the active generated note set at selected BPM, without accidentally recording/assessing the preview. If no piano synthesizer is available, implement a simple local note synthesis/driver or make the button visibly unavailable with explanation; do not leave a fake clickable action.

### Mode C - PERFORM: fluent phrase/whole-piece play (NEW interaction distinction)

- Same moving score and graded note set at correct tempo, but **do not automatically rewind** or interrupt for errors. Let musical time continue across the phrase/piece, even if the player misses everything.
- Give restrained live feedback and a clear end summary: accuracy, timing, missed pitches, weakest bars, and an invitation to Practice weakest section.
- A longer performance should not restart at the first mistake; it exists to experience music, not pass micro-quizzes.
- Full-song performance must use **all original MIDI events**, not a simplified subset.
- Listen-to-example and Perform are different: a demo does not count toward mastery.

## Interaction state and contracts (implementation guidance)

Avoid booleans scattered across UI scripts. Model an explicit mode and phase alongside the existing stable transport:

- `mode`: `learn`, `practice`, `perform`.
- `phase` (example, refine as needed): `ready`, `introducing`, `guided_wait`, `count_in`, `playing`, `paused`, `feedback`, `recovering`, `loading`, `finished`, `preview`.
- `lesson`: stable exercise identifier + variant (skeleton/outline/original), hand, absolute and local beat/bar boundaries, required MIDI note IDs.
- `expected_notes`, `heard_notes`, `note_feedback`: note events with IDs, onset/pitch/status and *hint-used* field; emit only settled feedback states.
- `transport`: authoritative beat/time, BPM, target BPM, transport attempt ID, moving lead-in length, recovery begin/end and score revision.
- `repetition`: clean consecutive count, current mode, assisted count, latest mistake locations and proposed next action.
- `device`: connected/disconnected/preview with device label, recent note events and latency configuration.

The score geometry, playback, live grading and keyboard hint layer must share the same **active exercise IDs and pitches**; never engrave one variant while grading another. A stale PNG revision or obsolete network response must not advance the lesson. MIDI input belongs to the backend and is timestamped at receipt, not at an animation frame. Consider a dedicated `TeachingController` in Python that consumes stable events rather than embedding pedagogy in `main.gd`.

Godot: split `godot/main.gd` if helpful into `PracticeScene`, `ScoreViewport`, `HintKeyboard`, `LessonProgress`, `PracticeControls`, `FeedbackBanner`, `SettingsView`, preserving existing public behaviour and tests. Build controls for user tasks, not all-purpose identical buttons. Continue using `godot/practice_theme.gd` and `moodboard.png`: forest/charcoal, sage/teal, stone text, **no bright white canvas**. Score must dominate vertical space; virtual keyboard expands only when helpful and should not squeeze notation into illegibility. Do not imitate macOS traffic-light chrome in the moodboard.

### Example of one generated lesson

Input: arbitrary two-hand MIDI phrase. Backend produces right-hand skeleton, then outline/original, left-hand equivalent and both-hands practice when useful.

1. Show `Learn · Right hand · Melody outline` with 4-6 noteheads; first note gently highlighted; no moving timeout.
2. If note is incorrect: retain target; show key hint; let student play again. When correct, reveal next target, subtle positive change.
3. When all targets can be found: `Ready for rhythm?` -> brief animated lead-in (capped ~4 s).
4. Timed Practice: staff moves steadily left under timing beam; events graded in real time; user may struggle, but score still moves.
5. If threshold is reached: complete two-bar unit; show one concise reason and X BPM; auto-retry relevant two-bar portion after lead-in, possibly route to guided mode for persistent recurring pitch errors.
6. Clean practice restores selected target BPM and accumulates 3 full clean target-speed passes; show one-line progress, not a score dump.
7. Advance to next genuinely useful level, or connected phrase. Eventually offer uninterrupted Perform.

## Ordered implementation milestones and acceptance gates

### P0 - Ensure current behaviour is real, capture baseline (do this first)

- Pull latest main, inspect `docs/verification-2026-10-15.md`, run tests and real Godot smoke. **Do not rewrite the reported fixed camera purely because an earlier user screenshot showed it broken.** However, physical acceptance is still open; write clear repro instructions for the target machine.
- Save normal desktop screenshots/recorded frames at 40 BPM, at least one onset during lead-in, mid-phrase, notehead crossing, held rest, and end-of-phrase. Compare at normal display scales to `moodboard.png`.
- Verify no unhandled errors on Start/Stop/Resume; no accidental scoring without connected MIDI.
- Deliver: baseline evidence and known limitations. Any actual regression in moving score must be fixed before the next milestone.

### P1 - Implement guided LEARN and hint keyboard (main new work)

- Implement explicit guided exercise state, chord and repeated-note recognition, expected-note cursor, conditional virtual keyboard with pitch labels, separate correct/hinted/wrong statuses.
- Test note ordering, chords, repeated notes, held notes, wrong note then correction, early release, no device, pause/stop, stage switching.
- Integrate into the existing practice screen; do not require brand-new preloaded exercise data.
- **Acceptance:** Load an arbitrary MIDI -> automatically show a generated short learnable fragment -> user plays correct pitches at any speed -> clear inline success -> next target; after a wrong note shows the precise key to press; never gives false clean-take credit.

### P2 - Timed PRACTICE with instructional recovery

- Explicit timed Practice mode with current score transport, feedback and short lead-in. Recover after five wrong/missed notes at a *completed* two-bar boundary; repeated trouble can send the user back to relevant guided LEARN targets.
- Include `What happens next` feedback label: `Retry bars 3-4 at 36 BPM`, `Clean pass 2/3`, `Now restore missing chord notes`.
- Test latency/jitter, 30/40/80/120 BPM, 3/4 & 4/4, rests, multi-system, deferred retry and 10% restoration. Under missed notes the score must **keep moving**.
- **Acceptance:** A simulated learner who misses five targeted events reliably reaches a boundary retry with the right segment and tempo; guided recovery neither corrupts the normal clock nor awards mastery.

### P3 - Audible LISTEN and uninterrupted PERFORM

- Implement *active-variant* audible demo (pitches/durations), separate from listener/recorder. No fake Listen button. Add PERFORM with no automatic interruption and meaningful end summary.
- Test that demo playback and no-device preview never count as student notes; verify same source identity/order and no lost rests/held endings.
- **Acceptance:** User can listen to a 2-bar exercise, then practice it, then run a complete phrase without forced rewinds, with accurate summary afterwards.

### P4 - Finish the dark learning UI and navigation

- Refine the existing moodboard-based screens and typography, emphasizing lesson instructions rather than numeric step counts (e.g., don't foreground `1/301`).
- Practice HUD shows song, hand, passage, current action, BPM/target, mode, 3-clean counter, MIDI connection state and next transition; avoid overwhelming metadata.
- Provide accessible color + shape/text indicators for note results and visible keyboard. Support fullscreen, 1536x960, 1024x768, 800x600.
- Pause sheet: Resume, Retry, Listen, slower/faster, hand, Exit, seek to bar if reliable. Keep keyboard shortcuts, ensure no dead controls.
- **Acceptance:** A new learner can identify *what to play and why* without terminal instructions and without needing to decipher a sheet-music debugger UI.

### P5 - Natural progression and stateful learner model

- Work from current consolidated 301 stages, not old 1,209. Improve progression around **meaningful skill units**: ease-appropriate placement, don't force repetitive simple patterns, offer optional placement/skip without secretly claiming mastery, exercise-to-exercise transitions, saved trouble spots.
- Preserve 3-clean rule on a *required* exercise while allowing redundant generated stages to be skipped by documented criteria. Do not invent star-rating copies.
- Add regression fixtures with easy melody, mixed-meter two-hand song, sparse long rests, dense fast section, repeated chord, whole 237-bar sample and missing MIDI input.
- **Acceptance:** A 16+ bar piece teaches manageable units, revisits errors, connects hands and phrases, and ends with an original full-piece Perform stage. Interactions remain responsive and honest about progress.

## Testing protocol - mandatory before 'done'

Current tests (verify commands in repo):

```bash
python -m pytest -q
./scripts/check_godot.sh
python scripts/smoke_phase0.py
python scripts/smoke_godot.py
python scripts/smoke_adaptive_godot.py
python scripts/check_visible_playback.py --output-dir /tmp/piano-visible
python scripts/check_desktop_ui.py "/path/to/example.mid" --output-dir /tmp/piano-desktop
./run.sh
```

New tests must cover a **whole simulated student's journey**, not a manually forced state: from generated notes -> Learn with wrong pitch -> keyboard hint -> correct response -> timed lead-in -> missed-note recovery -> slowdown -> clean restoration -> 3 target-speed passes -> stage advancement -> Listen -> Perform. Use fake MIDI input to the test backend where needed, not a production API that lets random clients submit perfect answers.

Capture **rendered frames**, not just backend phases or changing cursor coordinates. Assert score notes and staff remain visible while the notes move relative to fixed playhead. Include screenshots of the dark interface and hint keyboard. Physical speakers and USB instrument tests remain a separate manual gate; report them as pending until the user can test.

Do not claim a successful Godot smoke proves the USB piano was recognized or the metronome is audible.

## Work agreement and output

1. Start with fresh `main` and preserve other concurrent changes; do not overwrite fixes Codex or the user made since the baseline.
2. Keep tasks small and commit coherent milestones. Give exact SHA, tests and screenshots paths, what changed, what remains.
3. Don't wait for CI for every change; run local checks and report CI status separately.
4. Do not add a proprietary song library, copyrighted course content, mock album artwork or fabricated learner statistics. Use imported MIDI/MusicXML only.
5. Do not copy Simply Piano artwork, branding or code. Implement comparable **interaction principles** with our own design and algorithms.
6. Don't treat UI screenshots as final unless Godot actually produced them. No static/mock-only substitute for a playable screen.
7. Keep fast keyboard navigation and low-glare dark theme. If user requests additional changes, prioritize observed behaviour over previous assertions that tests passed.

### Final definition of done

The student imports arbitrary music and sees **a comprehensible learning task**, not a page of metadata. Notes can first be learned at an untimed pace with contextual hints, then practised in time with a reliably moving staff, then performed uninterrupted. The application recognizes MIDI input, supplies immediate useful feedback, provides intelligent short retries at lower tempo, increases tempo after real improvement and progresses through musical sections with minimal manual work. All of that is delivered inside the approved, polished, low-glare Godot UI.

## Evidence for Codex (avoid overclaiming Simply Piano internals)

Official help:
- https://piano-help.hellosimply.com/en/articles/7943680-understanding-play
- https://piano-help.hellosimply.com/en/articles/7943490-learning-with-simply-piano-the-basics
- https://piano-help.hellosimply.com/en/articles/16945914-simply-piano-song-library-menu-navigation
- https://piano-help.hellosimply.com/en/articles/7943591-understanding-star-levels
- https://partners.hellosimply.com/faq (older archived product description)

Independent observations:
- https://www.musicradar.com/reviews/simply-piano-review
- https://www.pianodreamers.com/simply-piano-review/
- https://eprints.lancs.ac.uk/226859/3/2024gottlerphd.pdf

Project docs and implementation:
- `ROADMAP.md`, `docs/verification-2026-10-15.md`, `godot/practice_theme.gd`, `godot/main.gd`, `piano_teacher/server.py`, `piano_teacher/learning.py`, `piano_teacher/lesson_score.py`, `piano_teacher/practice.py`, `piano_teacher/recovery.py`.
