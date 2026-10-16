# Piano Teacher

An offline Linux piano teacher built with Godot 4 and Python. Import your own
MIDI or MusicXML, learn simplified passages, restore the original notes, then
connect the passages into a complete performance. All progress stays local.

The interface follows `moodboard.png`: forest background, charcoal workspaces,
stone notation and a restrained teal timing line.

## Install and launch

On Arch Linux:

```bash
sudo pacman -S godot python python-pip alsa-utils
python -m venv .venv
source .venv/bin/activate
pip install -e '.[godot,test]'
./run.sh
```

The launcher validates Godot's script, starts the local Python service, waits
for it to become ready, and stops it when Godot closes. Port 8765 must be free;
it will refuse to connect a new window to an older backend. Optional Godot
arguments can be passed through, for example `./run.sh --windowed`.

Use **Browse library** to choose music from `~/Music/Piano Teacher`. Settings
can select another folder; its subfolders are scanned automatically. Supported
formats are `.mid`, `.midi`, `.musicxml`, `.xml` and `.mxl`. The library displays
real filename and format metadata; files are never moved or rewritten.

Select your actual piano in **Settings → Piano input**. A virtual MIDI Through
port is not automatically treated as a connected instrument. Play a note to
verify actual input activity. A saved available device reconnects automatically.

## Built-in warm-ups

**Browse library → Built-in warm-ups** includes six original beginner studies.
No downloads or personal-music files are required. All studies now use **half
notes (two beats)** instead of difficult irregular ties; the 3/4 classical
study also uses one quarter note per measure. The Hanon-inspired and jazz
patterns start with deliberately uncomplicated rhythms.

Each warm-up is a three-step course:

1. **Left hand**, three consecutive clean full-study performances.
2. **Right hand**, three consecutive clean performances.
3. **Both hands**, three consecutive clean performances.

An incorrect performance resets the clean streak; it never advances to a
harder hand. The student's current hand, streak and unlocked stages are saved
locally. During the beginner studies there is no automatic two-measure
rewind/slowdown. The count-in, moving notation, Listen demonstration, manual
Restart and hands-free MIDI start still work. Without a piano, a timing preview
cannot earn mastery.

| Warm-up | Tempo | Focus |
|---|---:|---|
| Chord Changes | 68 BPM | C-G-Am-F beginner triads and alternate bass |
| Five-Finger Ladders | 70 BPM | Slow parallel finger motion |
| Classical Melody | 64 BPM, 3/4 | Original G-major phrase, half and quarter notes |
| Pop Accompaniment | 72 BPM | Steady pop chord changes without syncopation |
| Jazz Chord Voicings | 60 BPM | Gentle Dm9-G13-Cmaj9-Am9 harmony |
| Jazz Phrasing | 66 BPM | Long, easy two-note jazz-influenced phrases |

These are new original exercises, not downloaded song MIDIs. Imported song
curricula remain unchanged.


## Phase 7.6 - Playhead onset cue

When the fixed playhead crosses an engraved source onset, its vertical strike
line briefly strengthens (135 ms). This is the timing cue at the playing line,
not a guessed notehead graphic; the notehead's confirmation ring remains
reserved exclusively for graded physical MIDI input. The trigger searches a
cached index and fires once per source chord, not once per note or HTTP poll.
Pausing, restarting or seeking clears any stale cue.

## Phase 7.6 - Stable timebase under noisy MIDI/HTTP timing

The visible musical clock filters *phase error*, not the moving sheet music.
Normal polling jitter has a 0.025-beat deadband and low-pass filter so the
camera moves at the requested BPM rather than accelerating/decelerating on
each response. Persistent phase differences are corrected gradually with
a 2% maximum tempo adjustment (down from 6%). Retry, pause, resume, score
changes and actual seeks still reset synchronously. The regression checks
both alternating network delays and independent timestamp jitter, including
the exact downbeat and a whole 9.6-second passage.

## Phase 7.6 - Stable scrolling through system joins

A reproducible Godot/Verovio audit runs both a regular rhythmic passage
and a two-handed exercise with chords and cross-bar ties. The regular fixture
has a permanent maximum **1.25×** system-join velocity budget.
The chord-and-tie passage has its own **1.20×** maximum, and both fixtures
must retain at least **0.90×** normal speed at joins. The additional measured
padding is empty staff space only; no engraved glyph is stretched.

For generated two-hand piano lessons with **unchanged clefs, key and meter**,
the scrolling strip discards repeated *printed-system headers* at the
start of subsequent systems and, where Verovio exposes the true final
barline, trims unused staff extension after it. Where the pixels between
the final sounded event and that barline contain **only the staff's own
horizontal rules**, Godot removes that redundant blank run and stitches
the two untouched raster regions together. Any slur, beam, tie or other
visible ink triggers a conservative fallback instead of being cut. Reprinted
clefs and excess blank staff are not musical time yet used to make the
fixed playhead race across empty space at every join.
The original starting clefs, staff, barlines, musical glyphs and Verovio
attack coordinates remain intact; no notehead or tie is stretched. Imported
MusicXML and passages with notation changes retain their original headers,
rather than risk hiding musical instructions.

Regression tests compare the exact same raster pages with and without
the safe crop, check every notehead still hits real image ink, and confirm
system joins cannot become longer after header removal. This reduces
one source of velocity peaks, but does not guarantee absolute constant
pixels per beat when native engraving needs collision clearance.

## Phase 7.6d - focused practice transitions

A small phase cue presents Ready, Get Ready, Pause, Clean Pass, Retry,
Short Retry or Preparing. It follows backend states without restarting its
animation on each HTTP poll. Beat lights remain the sole numeric count-in.
The former large recovery banner no longer obscures the score; detailed
next-action instructions and backend tempo-change notices remain below it.
A phase cue fades out when Playing begins instead of vanishing abruptly.
During active graded playback,
redundant status text and full hand-stage cards are hidden. Preview warnings,
audio failures and unmapped-feedback messages stay readable. The full
teaching context returns at Ready, Pause and Feedback. All musical timing
and grading remain backend-authoritative.

## Phase 7.6c - instrument controls and minimal practice stage

The transport buttons are large piano-console keys with a separate icon well,
centred text region and physical hover/press/release response. Godot's ordinary
centred Button text is hidden *only on these keys*, so it never overlaps
the icons. The controls still expose their actual accessible text and use
native button pressed/focus signals. Narrow windows keep all three controls.

Music, Path, Settings and Exit use quiet small navigation links rather than
competing action cards. The stage drops decorative grids, corner brackets
and its duplicate progress bar; an understated musical progress rail remains.
The existing musical note mapping is unchanged, while an upper limit on
rendered staff spacing prevents the two-note warm-ups from magnifying beyond
a readable notation scale.

## Phase 7.6b - engraved-note feedback, first pass

The next source note or chord receives a slim, tilted notehead-shaped teal
outline. Correct MIDI attacks briefly create an expanding, fading response
*behind* the Verovio note raster. Incorrect or missed notes use precise red
outlines on the affected engraved notes, instead of filled circles, labels,
checkmarks, or a separately drawn wrong-pitch note. Timing deviations are
amber. Unmappable feedback stays in the status line below the score rather than a clipping in-score panel.
Disconnected preview information remains in the ordinary status line.

The genuine notehead coordinates and source-attack IDs still determine
visual positions. The teaching engine alone owns grading. The sound preview
remains ungraded.

## Phase 7.6a - phase-locked score motion (first pass)

The scrolling camera still places the actual engraved beat under a fixed rule
42% across the stage. Screen motion now uses a dedicated visual musical clock
which follows the backend's tempo, without resetting screen position on every
variable-latency HTTP poll. Backend corrections are limited to +/-6% of nominal
rate, preventing poll-driven sudden accelerations or backwards movement. A new
attempt, tempo change, pause or resume explicitly resets/freezes the clock.

This addresses **timing jitter**, not all **engraving-spacing variation**:
Verovio sometimes places equal-duration attacks at unequal horizontal
distances. True constant-pixel-speed movement with exact per-note timing
requires further proportional re-layout of that real engraving, without
stretching noteheads, ties or staff lines. Do not replace notation with
approximate graphical notes or use camera easing that moves attacks off-time.

The regression suite includes a standalone Godot test with alternating
HTTP delays, 68 BPM motion, downbeat, pause/resume and new-attempt resets.

## Phase 7.6 polish - animated game transport
Retry, Play/Pause and Listen/Practice have distinct engraved icons and
animated press/hover depth; the active transport has a subtle pulse.
The count-in LEDs animate from the authoritative beat clock. The in-stage
progress rail eases toward engine progress without changing musical timing
or progression rules.

## Phase 7.6 polish - Exit and Listen audio
Exit is visible in the practice header; Ctrl+Q also closes the app
from fullscreen or a drawer. Settings → Listen Audio has a separate
demonstration gain (-12 to +12 dB), default +6 dB and saved locally.
It does not change the MIDI piano or metronome. Reduce loud chords
if they distort.

## Game interface overhaul (Phase 7.6)

The practice surface is an **instrument-focused game HUD**, not a set of
website cards. The music is drawn on a dedicated dark, illuminated stage
with unobtrusive corner guides, a source-clock progress rail and brighter
engraved notation. A three-light meter shows the backend's actual clean
full-pass streak. It briefly pulses when the engine confirms a clean
take; red assessment, missed chord pitches and wrong-note ghosts retain
priority over this decorative presentation.

The primary controls are large, tactile **Retry / Play-Pause / Listen**
buttons. They show short verbs instead of shortcut explanations and
retain keyboard focus and hover/pressed states. Music, Path and Settings
are secondary compact actions. During playing, the extra explanation
is hidden to give more vertical space to the moving notation; it
returns when learning, waiting or reviewing a mistake.

The count-in has quiet metered preparation LEDs, driven by the same
authoritative transport beat used by the metronome. It does not start
another clock, play a separate jingle, grade a note or replace the score.
The overall palette, note contrast, rounded score surround, stage
progression chips and pause/error cues share the same visual language.
Decorative surfaces ignore mouse input, so they cannot block physical
piano or UI interaction.

The visual checks use actual Godot container layouts at
**1536×960, 1024×768, and 800×600**; they assert usable score
dimensions, three primary transport controls, unobscured Settings,
count-in meter behavior and the non-interactive stage. Physical input
latency and perceived appearance on the real desktop still need
acceptance testing during Phase 8.

## Short musical challenges and clean-run progression (Phase 7.5)

The practice screen now shows one short, readable challenge at a time,
based entirely on the authoritative engine's existing **three clean
full-pass** rule. The visible cue identifies the active hand and displays
progress such as **LEFT HAND · 1/3 CLEAN**. An assessed clean take shows
**CLEAN PASS · 2/3** together with the remaining automatic transition
time; failures show **RETRY**, leaving the red note-level assessment
available. Completing a hand displays a brief **LEFT HAND COMPLETE ·
RIGHT HAND UNLOCKED** cue without opening another page or adding a
button. The next hand and short exercise are selected by the backend,
never by the presentation.

Guided practice preserves the current musical idea number and note
count instead of pretending that untimed Learn mode earns a timed
streak. Without MIDI input the challenge is explicitly labelled
**PREVIEW**, and no clean-pass credit is displayed. Real restarts,
automatic recovery, slowdowns and full-passage mastery rules are
unchanged. The interface still offers only **Retry, Play/Pause and
Listen** during normal playing.

### Settings drawer and screenshot regression

Settings now uses a properly anchored contextual drawer with a
full-width music-folder field, wrap-safe Browse/Save and piano-device
buttons, and a wrap-safe tempo row. Long option labels are shortened,
with their explanations still accessible as tooltips. This prevents
controls extending off the window at 1536×960 and smaller display
sizes. The Godot geometry test checks the actual fields and button
rectangles rather than merely verifying the outer drawer.

## Living sheet music (Phase 7.4)

The moving notation now gives a discreet **next-chord cue** directly on
its real engraved noteheads. During a timed count-in and active playback,
the upcoming note or all notes of an upcoming chord gain individual
teal outlines as their onset approaches. The cue is limited to 1.25
quarter-note beats ahead, disappears across long rests, and follows
the same score coordinates and signed tempo clock as the timing line.
The cue is a **visual preview**, not a second grading engine.

A missed or wrong pitch retains its own **red notehead marking**, while
the other notes of a chord remain individually correct/uncorrected.
Authoritative assessed notes take priority over the optional teal
upcoming outline. A genuinely incorrect physical pitch still appears
briefly on its actual staff position with its note name; that ghost
fades automatically, including when the music is paused. Correct
physical attacks receive their brief teal pulse, independently of
later duration grading.

For long pieces the source-note chord groups are indexed only when a
new score is engraved; during playback the next group is found with a
binary search. This avoids scanning every note at every animation frame.
Scores and note identities still come from the canonical importer and
Verovio, not a simplified visual simulation.

The existing **real Verovio-to-Godot score-strip tests** now check
that both hands in a chord receive separate notehead cues, a red
missed pitch does not suppress the other chord pitches, the position
exactly matches engraved ink, and no future notes are shown past the
end or prematurely over long rests. The Godot layout test also checks
that animated wrong-note ghosts expire on a stationary score.
Actual appearance and hardware response must still be checked on the
Kawai as part of Phase 8.

## Sampled grand piano for Listen (Phase 7.3)

Listen can now use real recorded **Salamander Grand Piano V3** samples from
a Yamaha C5 (Alexander Holm, 16 velocity layers, CC BY 3.0) rendered by
**FluidSynth** into local 16-bit stereo WAV files. The same canonical source
notes, rests, durations, selected BPM, and original MIDI attack velocities
drive the audio and scrolling score. The renderer uses bounded PCM chunks,
preserves exact phrase duration and writes its cache atomically. Different
notes, dynamics, tempos and sample-bank versions get different cache keys.
No streaming audio service or account is necessary.

**One-time optional setup on Arch Linux:**

```bash
sudo pacman -S --needed fluidsynth
cd ~/Projects/piano_teacher
source .venv/bin/activate
python scripts/install_piano_soundfont.py
./run.sh
```

The installer explicitly downloads the FreePats **296 MiB SF2 archive**
and extracts its bank to
`~/.local/share/piano-teacher/soundfonts/salamander-grand-piano.sf2`.
Allow sufficient disk space for the extracted samples. The download is
**never** started automatically in a practice session and the SoundFont
is not committed to Git. It includes an attribution notice for the original
recordings and their CC BY 3.0 licence. Source:
https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html

If you already have an SF2 piano bank, no download is necessary: point
`PIANO_TEACHER_SOUNDFONT` to its absolute file path before launching:

```bash
export PIANO_TEACHER_SOUNDFONT="$HOME/sounds/MyPiano.sf2"
./run.sh
```

A valid SF2 file and the FluidSynth library are required for sampled
rendering. Listen identifies the selected instrument on screen; without
a bank it explicitly reports **Basic piano sound** and retains the old
synthetic preview, so offline learning never fails solely because the
optional large download hasn't been installed. A corrupt bank or missing
FluidSynth dependency produces an actionable error instead of silently
claiming to play recorded piano samples. Installing a bank takes effect
on the next Listen request; the currently running app need not be rebuilt.

**Verification:** `python -m pytest -q tests/test_sampled_piano.py
tests/test_demo_audio.py tests/test_listen_perform.py`. Sampled tests
exercise frame-accurate stereo PCM output, velocity changes, sample
selection, cache invalidation and secure extraction. A real SF2 check runs
when a system SF2 bank and libfluidsynth are available.

Limitations: historical MusicXML sources that do not encode per-note
dynamics use a consistent default velocity. Source sustain pedal events
are not yet represented in the lesson engine, so the sampled renderer
cannot reproduce them. The active Listen demonstration uses source notes
but not the player's input; it is not an assessed performance.

## Piano-first controls (Phase 7.2)

The normal practice screen now has **three primary buttons**, always in
the same order: **Retry**, **Play/Pause**, and **Listen**. A completed
guided idea uses the same central button to continue; Listen switches to
**Practice** while a demonstration is active, so leaving the demonstration
doesn't require finding another mode menu. Returning from Listen waits at
Ready for the next physical piano note or Play; score rendering never
silently starts the new attempt. The mode selector, hand settings,
persistent hints, passage navigation and Stop live in the **Lesson Path**
drawer; keyboard shortcuts remain available: **Space** Play/Pause, **R**
Retry, **L** Listen/Practice, **S** Stop, and arrow keys Previous/Next.

An ordinary Pause leaves the notes, feedback and Resume control visible
instead of replacing the score with a large modal. Advanced pause controls
(for tempo, seek and hand change) are explicitly available from Lesson
Path or with **Shift+P**. This does not change source-note assessment or
MIDI timing.

With an actual MIDI piano connected, playing a **fresh key after the ready
state is visible** starts a count-in. A fresh key after a completed guided
idea continues it. After failed Practice feedback has appeared, a *new*
key retries that passage; an input that coincides with the transition
cannot instantly dismiss feedback. Automatic recoveries cannot be
overridden by this shortcut. During playing or in other drawers, ordinary
performance notes never trigger an unrelated transport action.

The existing Godot interaction regressions exercise the live transport,
optional pause sheet, three-button layout, reversible Listen action, and
fresh-key-only retry logic. Hardware-specific latency remains for Phase 8.
The acoustic grand-piano samples for Listen are planned for Phase 7.3;
the existing synthetic audio is not yet replaced.

## Game-like interface: Phase 7.1 (practice-first navigation)

The application starts directly on the practice stage, rather than
showing a separate Home menu. Until a piece is loaded, the score area
offers a large **Choose music** action. While a piece is open,
**Choose music**, **Lesson path** and **Settings** appear as an
in-context drawer over the existing sheet music. Clicking outside the
drawer, Close/Back, or returning to practice dismisses it.

Opening a drawer during playback requests **Pause**, not Stop. The
existing transport ID, score and progress remain intact; returning to
the stage does not silently restart it. A quick library selection made
during the asynchronous pause is queued rather than discarded.
Selecting a different imported piece still presents the existing
starting-measure selector. The legacy Home page is no longer in the
normal navigation route.

This subphase establishes the persistent playing surface. The reduced
transport and piano-key-first flow are Phase 7.2; sampled grand piano
audio for Listen is Phase 7.3. Existing scoring rules and MIDI input
timing remain unchanged. Verify the drawer at multiple window sizes via
`./scripts/check_godot.sh` and the actual interaction regression suite.

## End-to-end library verification (Phase 6)

The **Check files** button performs a quick *source import* audit. To verify
that each file actually opens, engraves, renders, maps notes to the moving
score, and navigates to later measures, run the full local diagnostic:

```bash
source .venv/bin/activate
python scripts/verify_library_pipeline.py \
  --music-dir "$HOME/Music/Piano Teacher" \
  --output /tmp/piano-phase6-report \
  --godot
```

It checks the first, middle, and last **playable** source measure of each
file. Each test uses the production `PracticeEngine`, real Verovio glyph
and timing data, actual PNG raster pages, and the real Godot score-strip
assembler. It checks count-in, the advancing timed-preview clock and
next/previous exercise navigation, without recording piano input or awarding
mastery. A failure does not stop subsequent files.

The result is `/tmp/piano-phase6-report/report.json`. For each numbered
file, the output directory contains a worker log, source-measure manifests,
PNG raster evidence, and a Godot log when enabled. Failures also include
a traceback. The command returns a nonzero exit code if any file fails or
times out. Its per-file deadline defaults to 180 seconds (`--timeout 300`
for particularly large arrangements). For a quick initial sample, use
`--limit 5`. The script reads your music and writes only to the chosen
output directory and temporary isolated application data.

This is a **headless rendering and geometry test**. A pixel-accurate check
of a visible desktop window and the USB piano's physical timing remain
separate tasks. The CI exercises this pipeline with a real source fixture
and Godot. The exact files in your personal collection can only be
verified when you run the command on that collection.

## Library Health - Phase 5

Open **Browse library → Check files** to inspect your MIDI and MusicXML
imports before choosing a piece. This check runs **in the background**;
the normal music library stays responsive, and no instrument is required.

Each personal music file receives a status after checking:

- **[OK]** - the canonical source importer accepted the score.
- **[REPAIRED]** - the source imported, but ignored recoverable anomalies
  (for example zero-length MIDI notes or unmatched releases).
- **[ERROR]** - the source importer rejected the file; hover over the entry
  to read the reason.

The status line shows how many files have been checked and the numbers in
each category. **Recheck files** can be used after adding or changing music.
Unchanged files reuse their in-process import result, while modified files are
checked again. Changing the music folder clears previous results. Source
files, learner progress and MIDI preferences are never modified by a check.
The ordinary library scan remains fast because checking is opt-in.

A successful import check means the source was parsed. It does **not** guarantee
Verovio layout, playback, or physical MIDI input; those are verified later
when an exercise is opened. The check does not count toward mastery.

Regression tests: `python -m pytest -q tests/test_library_health.py`;
`./scripts/check_godot.sh` verifies the library controls and status display.

## Post-attempt review and exact section retries (UI phase 4)

After an assessed Practice or Perform attempt, the score shows a summary of
correct notes, missed/wrong pitches, timing/release problems, and extra keys.
Choose **Review notes and repeat a section** to see problem measures grouped
into original two-bar source intervals. The review lists each required note's
pitch and error category; when an incorrect key was played instead, it shows
both the expected pitch and the actually played pitch. Extra unmatched
physical keys are listed separately. Results come from the existing
authoritative note assessor, not from a second approximation.

Each problem section has a **Repeat measures X–Y** control. It prepares a
bounded Practice attempt that begins and ends at those exact source measure
boundaries; it waits for the player to press Start. Repeating part of a
passage never grants whole-passage mastery. Failed full Practice attempts
remain on the review rather than auto-advancing before the player can inspect
the mistakes.

For a hardware-independent regression, run
`python -m pytest -q tests/test_attempt_review.py` and
`bash scripts/check_phase2_ui.sh`. The Godot smoke also checks a real review
popup with wrong-pitch details and a retry button. A connected MIDI piano
is still required for *actual* player assessment.

## Starting at any measure and hand progression (UI phase 4)

When you select a personal MIDI file in the library, a **starting-point
dialog** now opens before any guided lesson starts. Enter the exact source
measure or drag the measure slider, then select **Learn notes** (no rhythm
scoring) or **Practice rhythm**. For Learn notes, the short guided unit begins
at that measure. For Practice rhythm, the selected source measure is kept as
the timed start position, and playback waits until you press Start. If the
selected measure contains no attacks, the picker advances to the next
playable source measure. It uses imported time-signature/bar boundaries,
including changes of meter. The selection does not award clean runs, and
partial timed attempts cannot confer full-passage mastery.

Built-in warm-ups still open directly and use their existing Left → Right →
Together unlock sequence. Above the score a compact progression strip
distinguishes the current hand, completed stages and locked stages. Imported
teaching passages show their available hands using the same strip.

Regression checks: `python -m pytest -q tests/test_open_at_measure.py`
and `bash scripts/check_phase2_ui.sh`. The latter verifies the actual
modal and hand progression in the Godot interface at three window sizes.

## Missing notes, wrong staff pitches, adaptive retry (UI phase 3)

During a MIDI-connected practice attempt, the app distinguishes:

- **Missed note:** after the last acceptable late-onset time, only the
  missing required *notehead* turns red. In a chord where two of three
  notes are played, the unplayed third note turns red; the other two
  notes are not marked as missed.
- **Wrong pitch:** when a played key is near a real expected onset, a
  red/orange notehead showing the **pitch actually played** briefly
  appears on the correct musical staff. It is placed using a real
  Verovio notehead reference and the actual staff spacing, with ledger
  lines where needed. Wrong keys during rests only appear in the
  live keyboard, because there is no associated engraved note.
- **Late/early and held-duration errors:** the existing assessor still
  scores pitch, onset and release duration independently. The live
  visualizations do not award clean-pass credit.

Mistakes in a warm-up now participate in adaptive recovery: **two**
wrong/missed required pitches in a two-bar window trigger a
boundary-aligned restart at 90% of the previous BPM. Imported-piece
Practice still uses five errors. The slowdown banner names the missed
count, original/next tempo and retry measures. A clean partial retry
must still be followed by a whole clean passage; three clean target
speed performances are still required for advancement.

For a hardware acceptance check, connect the Kawai in Settings, then
try a left-hand chord exercise: intentionally omit one chord tone,
press one different pitch, and then complete a full correct chord.
Check that only omitted noteheads turn red, the incorrect pressed pitch
appears briefly at the correct staff height, and completed notes are
not colored red. Repeat two errors over a two-bar section to see
10% adaptive slowdown and measure-aligned retry. Silent previews
cannot trigger either mistakes or automatic progress.

## Practice display and pause sheet (UI phase 2)

The timed practice toolbar and bottom transport controls wrap complete buttons
instead of shrinking text into clipped labels. The current **source measure**
appears beside the active warm-up stage/hand while the score moves. Practice
feedback, tempo, progress, and stage text have larger typography, and the
notation takes the remaining screen area. The Hints toggle only appears during
untimed Learn mode.

The pause sheet now has large buttons and visible groups for Resume, Retry,
Listen, tempo adjustment, hand selection, starting measure, and Exit. A more
transparent backdrop keeps the score recognizable while paused. The dialog
scrolls if there is insufficient vertical space; keyboard navigation and Space
to resume still work. The actual piano requires selection in Settings to enable
live note feedback - a screenshot saying **No piano** is an ungraded preview.

Verify the real Godot layout, including a simulated paused screen, at three
window sizes:

```bash
./scripts/check_godot.sh  # includes the UI geometry checks
# Or only the layout checks:
bash scripts/check_phase2_ui.sh
```

Then open `./run.sh`, test Practice, Pause and Resume at your screen resolution,
and verify the same actions at 1024x768 using `./run.sh --windowed`.
This layout test checks actual controls and dimensions, not pixels or piano
hardware; an instrument session and screenshot review are still required.

## Live physical-key feedback (UI phase 1)

When a USB MIDI piano is connected, timed Practice and Perform show a keyboard
beneath the score. The next expected chord is highlighted, held physical keys
light up, and even brief released taps are visible for about 0.8 seconds.
The response distinguishes a received key, an expected pitch played near its
onset, an early/late attack, and an unexpected pitch. Matched attacks also
produce a short pulse around their exact engraved notehead. A key struck during
the count-in is shown as an input, not as a successful attack.

These immediate highlights are **provisional**. They do not grade release
length, pedal, or mastery. Final note classifications and clean-pass progress
still come from the regular authoritative assessor. The practice screen uses
50 ms local HTTP polling while a piano is connected; actual instrument-to-screen
latency remains to be measured on the Kawai.

To verify on the instrument: open Chord Changes, select the Kawai MIDI input,
play one key to start the count-in, release it, then play the left-hand notes.
Check that key presses illuminate immediately, matched score notes pulse, wrong
notes show a contrasting color, chords light multiple keys, and release removes
held-key highlighting. Repeat with an imported piece to see score pulses.

## Learn and practise

Opening a piece starts **Learn notes**. Find the highlighted note or chord on
your MIDI piano at your own pace. A wrong note or a hesitation reveals a small
keyboard with exact pitch names. Release repeated keys before playing them
again. **Next idea** prepares the following source measures; **Try rhythm**
brings the passage together in timed Practice. Your prepared ideas and trouble
spots are saved locally.

Use **Listen** to hear the active lesson's actual notes at the selected tempo.
With the optional Salamander samples installed, this is a stereo sampled
grand piano; otherwise it explicitly identifies the basic synthesized
fallback. Both preserve rests and held notes.
Your input is not graded during the example. **Perform passage** and
**Perform whole piece** continue through mistakes, then show a review and a
button to practise the weakest section. Perform does not earn Practice credit.

The lesson path offers saved trouble revisits, optional original-note placement
and explicit skips. Skipped or placed steps are labelled as unmastered. Required
Practice steps still need three clean full runs at the selected target tempo.

## Timed Practice

Press **Start**. A short, audible count-in begins immediately, with clefs, meter
and rests on the moving staff. The first note arrives at its musical
onset. Notation continues moving from right to left even when you play nothing.
Without an input device this is an ungraded timing preview, which finishes
without awarding mastery.

Python owns one signed musical clock: negative beats are count-in, zero is the
downbeat, and positive beats are playback. Godot extrapolates snapshots between
HTTP polls. The raster, real noteheads, feedback and timing line share one
projection. Engraved systems are preloaded as separate horizontal tiles, so a
line or page wrap does not need a new image during playback. Transparent and
opaque image margins are handled correctly. Slower tempos spread the notes
farther apart while preserving the symbols' size and shape. The count-in uses
the opening notes' spacing, so motion flows through the downbeat.

Preparation lasts at most one bar and approximately four seconds. Settings can
turn off practice metronome beats; the preparation count-in remains audible.
**Listen** is separate from student Practice and cannot award clean runs.

Pause opens Resume, Retry, Listen, tempo, hand and source-bar choices. Resume
keeps the same attempt; Retry and bar selection begin a fresh count-in. A
later-bar retry must be followed by the full passage before mastery is possible.
The pause sheet supports keyboard focus and fits the compact desktop layout.

Controls:

| Control | Action |
|---|---|
| Space | Start, pause, or resume |
| P | Pause or resume |
| R | Restart with a fresh count-in |
| S | Stop |
| Left / Right | Previous / next passage |
| Escape | Return to the library |
| F11 | Toggle fullscreen |

The practice screen shows the active hand, stage, tempo, clean repetition count
and note feedback. **Lesson path** explains the course and allows hand selection.
**Settings** contains the music folder, MIDI selection and actual input activity,
selected piece's target tempo, metronome and fullscreen control. Window layout
uses the actual available dimensions rather than shrinking a desktop canvas.
Opening Settings or Lesson path pauses an active attempt; return and press
Resume to continue from the same place. Stop or returning to the library ends
the attempt. Settings returns to the screen where you opened it.

## Adaptive teaching

Manageable adjoining material is consolidated into sections of up to eight bars.
Dense chords and fast or irregular figures retain focused two-bar exercises.
Hand-specific work introduces a skeleton, an optional meaningful chord outline,
and the original notes. Trivial material and negligible outline increments skip
redundant stages. Single-hand material is not taught again as a duplicate
both-hand lesson. Integration, boundary connections and final performance use
original notes. The final performance preserves introductory rests and held
endings as well as every source note.

The supplied Merry-Go-Round-of-Life MIDI produces **45 learning sections, 44
boundary connections and a complete original performance: 301 stages**, reduced
from 1,209. Eleven difficult two-bar units remain. These are deterministic
musical-density heuristics, not a general musical-phrase or student-skill model.

An attempt is assessed against exactly the generated notes being displayed:

- Five distinct wrong/missed required pitches in a recent two-bar window queue
  recovery at a musical boundary. Recovery rewinds roughly two bars, reduces
  tempo by 10%, and begins another short count-in.
- Clean performances restore speed toward the selected target. Three consecutive
  clean **full-exercise** performances at target tempo confer mastery.
- Silent previews, partial retries, manual Stop and navigation never confer
  mastery. A partial retry must be followed by the whole passage.
- Completed performances show feedback briefly, then repeat or advance
  automatically. Score revision acknowledgements prevent playing the next
  exercise against stale notation.

The selected target tempo survives hand and passage changes. Progress is saved
in `$XDG_DATA_HOME/piano-teacher/progress.db`, usually
`~/.local/share/piano-teacher/progress.db`. Preferences are in
`$XDG_CONFIG_HOME/piano-teacher/settings.json`, usually `~/.config/piano-teacher`.
The compact course migrates existing positions by musical span and stage, retains
legacy mastery, and resets a clean streak when its required notes changed.

## Verification

Close the application before checks using port 8765:

```bash
source .venv/bin/activate
python -m pytest -q
./scripts/check_godot.sh
python scripts/smoke_phase0.py
python scripts/smoke_godot.py
python scripts/smoke_adaptive_godot.py
python scripts/check_generated_lesson.py --output-dir /tmp/lesson-pngs "/path/to/music.mid"
python scripts/check_musical_fidelity_corpus.py --output /tmp/piano-musical-fidelity
```

The following checks require a graphical desktop and inspect **actual rendered
pixels**, not just increasing backend beats or camera log messages:

```bash
python scripts/check_visible_playback.py --output-dir /tmp/piano-visible
python scripts/check_desktop_ui.py "/path/to/music.mid" --output-dir /tmp/piano-ui
python scripts/smoke_student_journey.py --output-dir /tmp/piano-student
python scripts/smoke_learning_ui.py --output-dir /tmp/piano-learning-ui
```

The visible playback check captures the same note at 30, 40, 80 and 120 BPM,
checks local raster ink, leftward movement, fixed timing line, stable scale,
pause/resume, restart and a naturally completed ungraded preview. It writes PNGs,
JSON measurements and logs. `--bpms 40` selects a shorter probe; `--resolution
1024x768` selects a window size. The UI check runs **the normal `./run.sh`
launcher**, opens a real piece, exercises controls and captures all screens at
1536×960, 1024×768 and 800×600. Both use isolated progress/preferences, preserving
existing user data and source files.

The musical fidelity corpus checks 26 actual MIDI/MusicXML imports and four
unsupported inputs through source identity, generated exercises, real Verovio,
evaluation and feedback. It writes score PNGs and explicit attack/continuation
maps, including a six-page exercise. See [Phase 2A verification](docs/phase2a-musical-fidelity-verification.md)
for source timing, clef/key support, progress compatibility and limitations.

Automated Godot tests also exercise real engraving through multiple systems and
pages, transparent cropping, screen-space note projection, feedback and musical
joins. See [the teaching verification](docs/teaching-p5-verification.md) and
[methodology](docs/teaching-methodology.md) for results and remaining limitations;
[the earlier playback record](docs/verification-2026-10-15.md) preserves baseline evidence.

## Troubleshooting and implementation

A preparing/error panel reports engraving failures and offers **Retry score**.
For an isolated engraving check:

```bash
python scripts/check_engraving.py --output /tmp/piano-score.png "/path/to/music.mid"
```

Verovio's Bravura/Leipzig resources are loaded from its installed Python wheel.
If imports fail, reinstall `pip install -e '.[godot,test]'` in the checkout's
virtual environment. `aconnect -l` helps inspect ALSA MIDI ports. Launching from
a terminal preserves actionable errors; Mesa's `DRI_PRIME` notice is unrelated
to score geometry.

The loopback API binds only to `127.0.0.1:8765`. Principal endpoints are `/state`,
`/control`, `/library`, `/library/open`, `/settings`, `/devices`, `/device`,
`/lesson`, `/demo.wav?token=...`, `/score/layout`, `/score.png?page=0` and `/score.svg?page=0`. Settings
accept `music_dir`, `fullscreen`, `midi_device` and `metronome`. Layout contains
real notehead IDs/pitches, onset anchors, staff lines, system bounds and pages.

Python modules own importing, generated lessons, grading, recovery, curriculum,
guided recognition, local audio and SQLite persistence. Godot's `main.gd` owns navigation and API integration;
`score_strip.gd` owns tiled score coordinates and `practice_theme.gd` the shared
dark theme. The older Qt entrypoint remains available separately.

## Preview notation scale and continuous scrolling (Phase 7.6 follow-up)

The real grand staff now determines practice zoom, rather than the full
height of an SVG page containing large empty margins. A background staff
joins all preloaded system tiles at their precise vertical line positions;
the original engraved noteheads, clefs, accidentals and barlines are
unchanged. Normal MIDI practice continues to align each source attack
to the fixed playhead at its authoritative musical time. An **ungraded
preview with no keyboard** uses a constant visual pixel-per-beat scroll,
including through barlines and system joins. That preview mode prioritizes
smooth motion; intermediate engraved attack crossings can differ from
their real musical timestamps until fully time-proportional engraving
replaces the old layout. Scoring is disabled in this mode.

## Phase 7.7 - Resonance (visual polish)

Phase 7.7 is implemented on `main` in four layers:

- **7.7a, continuous score:** generated multi-system strips clear only isolated
  horizontal raster lines at tile seams. A measured column containing real
  musical ink (barline, tie, stem, note or other symbol) is preserved; the
  single underlying staff supplies the unbroken lines. The rail color now
  matches engraved notation. The long staff is redrawn only on resize or
  score change, rather than on every camera frame.
- **7.7b, note impacts:** actual assessed MIDI note-on events produce bright
  mint notehead outlines, a short bloom and twelve deterministic light
  particles per note. Early/late notes use amber, and unexpected notes
  produce shorter coral sparks; all effects expire within 450 ms. There
  are no particle nodes, and at most sixteen active hits render.
- **7.7c, ambient stage:** the score has a subtle breathing studio glow and
  fixed playhead illumination while the transport runs. The studio briefly
  brightens on judged piano input. Only physically received MIDI events
  create note impacts; no-piano preview and Listen receive ambient motion
  but no achievement or correct-note effect. Nearby *measured* staff
  lines briefly illuminate when an assessed MIDI note arrives.
- **7.7d, progress:** the existing three-clean-run indicators animate
  verified success, with a traveling highlight when the backend unlocks
  the next left/right/both-hand stage. The newly active hand label pulses
  once. The underlying score and saved progress logic are unchanged.

Local checks on Arch Linux:

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q tests/test_phase77_game_feel.py tests/test_score_strip.py
./scripts/check_godot.sh
./run.sh
```

For a useful visual check, open a multi-system warm-up and play without a
keyboard first, checking consistent motion and staff joins. Connect the Kawai
and play single notes, a chord, a wrong note, then three clean repetitions.
The two modes must be visually distinguishable. Genuinely engraved barlines
remain visible; tile-edge artifacts should not. Physical piano latency,
60 FPS on a full-screen long score and hand progression still require
desktop/instrument acceptance. Headless tests are not sufficient to prove
these visual outcomes.

## Phase 8 - Physical piano acceptance (first milestone)

Phase 8 adds an opt-in, bounded local MIDI diagnostic session. It observes
the **same callback** as the live Godot practice engine, with no additional
MIDI-port ownership and no change to grading, tempo or saved progress. Connect
the Kawai in **Settings → Piano input**, leave Practice stopped, and launch
the application normally. In another terminal run:

```bash
.venv/bin/python scripts/check_hardware_session.py --duration 25 \
    --output /tmp/piano-hardware-check.json
```

During recording play quiet/loud single notes, a three-note chord, repeated
attacks and sustain-pedal down/up. The report includes note-on/off counts,
velocity range, chord overlaps, pedal events, unmatched releases and held
notes; full timestamped note events are retained **in memory only while
requested**, at most 512 events or 90 seconds, unless you explicitly provide
an output path. Never share the optional report if you consider the notes
private. The backend provides a loopback-only `GET /diagnostics/hardware` and
`POST /diagnostics/hardware` with `{"action":"start"}` or `{"action":"stop"}`.
Changing/disconnecting the instrument stops the capture. Unplug/reconnect
tests and callback timing instrumentation are covered without hardware.

**Not yet measured:** physical key-to-MIDI delay, output speaker/audio delay,
full graded performance through the actual Kawai and corresponding screen
recording. These require an instrument-side test; callback timestamps cannot
establish physical or acoustic latency on their own.

## Phase 8B - Listen audio/score synchronization

The visible playhead and actual Listen WAV now use the same interpolated
backend transport beat at playback start. The previous snapshot-only start
could be late by one HTTP polling interval. Godot then checks the software
audio-mix position no more than five times per second; a correction is
permitted only after **three consecutive errors exceeding 200 ms**, with
at least 1.8 seconds between corrections and no corrective seeks near the
start or end. Pausing clears pending drift observations. Listen never writes
MIDI grades, auto-unlocks hands or changes source note timing.

The optional on-device log is:

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q \
    tests/test_note_reactions.py tests/test_phase77_game_feel.py \
    tests/test_listen_sync.py tests/test_demo_player.py
./scripts/check_godot.sh
./run.sh -- --listen-sync-diagnostics
```

During **Listen**, the terminal prints a
`PHASE8B_LISTEN_SOFTWARE_SYNC` record at most once per second, with
software-mix drift in seconds, largest observed software drift and the
number of corrective seeks. For useful acceptance evidence, collect the
log while listening to a passage, pause and resume twice, then repeat on
a long score. The frame-capture and actual Kawai audio setup can then
be compared separately.

**Important:** These values cannot measure physical key-to-MIDI latency,
operating-system speaker latency, acoustic loudspeaker delay or visual
display latency. They must not be presented as a measured piano latency
figure. Real Kawai playback and full graded warm-up validation remain
the subsequent Phase 8 acceptance tasks.

## Phase 8C - Passive graded piano-session capture

This milestone adds a local observer for the **real** connected instrument.
Unlike the static MIDI diagnostic, it runs alongside an active graded
Practice/Perform session and does not claim to solve grading itself.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
./run.sh
```

Choose a warm-up, connect the Kawai and leave the app ready. In a second
terminal, before starting the practice run:

```bash
cd ~/Projects/piano_teacher
.venv/bin/python scripts/check_grading_session.py \
    --duration 180 --takes 10 --output /tmp/piano-graded-session.json
```

Then play normally. The capture records backend-generated graded take
results, hand stage, clean streak, MIDI attack counts, actual visual-feedback
status counts and phase changes. Consecutive HTTP polls cannot duplicate a
note or take. The report contains **no per-note pitches, source IDs or
individual timestamps**; it is an aggregate of what the canonical engine
actually observed, capped at 512 unique visual events and 128 phase changes.
A preview cannot count as a graded take. Choose a larger `--takes` value
if you want to include mistakes and three clean runs in the same recording.
Capture stops at the specified maximum duration even if there is no result.

Verify with `.venv/bin/python -m pytest -q
tests/test_grading_session_capture.py`. On-machine keyboard and screen
acceptance are still required. Hardware input delay, acoustic output delay
and actual displayed FPS remain outside the loopback API's capabilities.

## Phase 8D - Frame interval acceptance

An optional Godot diagnostic samples actual process-frame intervals on the
visible Practice screen. It reports mean FPS, mean/p95/worst frame interval
in milliseconds, tile count and the backend phase, once per approximately
one second. This is frame scheduling evidence, **not** physical monitor
refresh or sound-to-screen latency.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q tests/test_frame_meter.py
./run.sh -- --frame-diagnostics
```

For simultaneous software audio and rendering checks, use
`./run.sh -- --frame-diagnostics --listen-sync-diagnostics`.
Capture the terminal output during a long multi-system preview, then
during actual Kawai practice. The checks never block playback, change
MIDI grading or create extra GUI controls. Hardware-side measurement is
still required to establish sound-to-screen and key-to-sound latencies.

## Remaining limitations

Physical speaker audibility/latency and a real USB piano session still need
validation with the student's instrument. Software desktop checks establish
visible motion and click scheduling, not physical timing quality.

General MIDI quantization, hand corrections, preserved source engraving/key
metadata, pedal scoring, fingering hints, and musical phrase inference remain
future work. Listen supports an optional sampled acoustic piano and retains a
basic harmonic fallback; both decode the completed WAV in Godot and currently
keep a disk cache without an eviction policy. Irregular supported durations are split into tied
notes/rests or explicit tuplets for engraving; original MIDI events remain the
assessment source. Very long pieces preload cropped score textures: memory use
grows with the piece, with additional transient raster memory.
Streaming only neighboring systems is future performance work.
