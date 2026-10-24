# Piano Teacher

An offline Linux piano teacher built with Godot 4 and Python. Import your own
MIDI or MusicXML, learn simplified passages, restore the original notes, then
connect the passages into a complete performance. All progress stays local.

Native notation uses a continuous score timeline and a fixed playhead.
The established Verovio-versus-native framebuffer comparison runs **locally**.
GitHub CI runs only fast fixture regressions and Godot script validation;
**a green CI run does not certify the complete MIDI library**.

Install Godot and Xvfb once on Arch Linux (`sudo pacman -S --needed
godot xorg-server-xvfb xorg-xauth`). With `.[godot,test]` installed,
verify the entire project using **one command** from the repository root:

```bash
./scripts/verify-notation.sh
```

The command first runs the fast Python regression fixtures and Godot parsing
checks. If those pass, it automatically works through all 24 batches of the
existing Verovio/native framebuffer comparison: all bundled MIDI sources,
every original measure and hand, learning variants, and supported MusicXML
fixtures. Failed batches do not prevent later batches from being checked.
A complete pass requires all batches to succeed. This exhaustive check can
take a long time and is intentionally **local**, not a GitHub Actions job.

Progress, failure messages and captured evidence are written to
`notation-check-results/` (gitignored). Rerunning the command starts the
checks again; `PIANO_VERIFY_REUSE=1` can reuse valid unchanged captures
for detector development. Seven Godot capture workers are used by default (seven parallel processes).

GitHub CI calls the same script with its internal `--ci` flag, which runs
only the short regressions and Godot validation. A green CI check or tagged
release does **not** establish a passing full-library notation audit.

The interface follows `moodboard.png`: forest, pine and charcoal surfaces,
serif music titles, white active staves, a restrained teal timing line and a
five-part progress rail. Library, Lesson Path and Settings share a dedicated
sidebar layout. The library uses real file metadata, with two columns on wide
windows and a single column on smaller screens. Lesson stages reflect the
levels available for the current passage and hand. Python owns the musical
clock and assessment throughout navigation.

## Install and launch

On Arch Linux:

```bash
sudo pacman -S godot python python-pip alsa-utils
python -m venv .venv
source .venv/bin/activate
pip install -e '.[godot,test]'
./run.sh
```

## One-command playtesting (recommended for piano sessions)

Instead of launching separate MIDI, grading, FPS and Listen audits, run **one
file** from the repository root:

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python playtest.py
```

The regular fullscreen app opens. Play as usual: check your USB piano in
Settings, try a few soft/loud notes and chords with sustain soon after
connecting, complete some graded attempts (left, right and both hands if
available), and use Listen for a passage. You do **not** need to keep
switching to the terminal while playing. Close the app to finish.

The launcher automatically captures the first up-to-90-second hardware
MIDI probe while the piano is connected and practice is stopped, then
passively observes grading for the remainder of the session. It also
collects real on-device frame interval/texture and Listen software
synchronization logs. It **never** opens a second MIDI input, interferes
with practice, changes mastery, or claims to measure physical latency.

One shareable output file is created at
`playtest-results/<session-time>/playtest.zip`, alongside a readable
`report.md` and the complete local `godot.log`. The ZIP contains the
aggregate report, graded practice summary, MIDI counts (no raw note
pitches or velocities) and concise frame/audio diagnostic lines. The
unfiltered local Godot log is intentionally **not** included in the ZIP.
Missing measurements are reported as missing, never as a pass.

To run focused UI, MIDI, score and synchronization tests automatically
**before** the session, still use the same single launcher:

```bash
.venv/bin/python playtest.py --preflight
```

Optional: `--midi-seconds 0` disables the raw hardware probe if you
only want graded practice and performance observations.
`--output-dir /tmp/piano-session` chooses where to save the report.
On early app closure the last observed aggregate hardware snapshot is
retained when the backend is no longer available.

The launcher validates Godot's script, starts the local Python service, waits
for it to become ready, and stops it when Godot closes. Port 8765 must be free;
it will refuse to connect a new window to an older backend. Optional Godot
arguments can be passed through, for example `./run.sh --windowed`.

Use **Music** to choose music from `~/Music/Piano Teacher`. Settings
can select another folder; its subfolders are scanned automatically. Supported
formats are `.mid`, `.midi`, `.musicxml`, `.xml` and `.mxl`. The library displays
real filename and format metadata; files are never moved or rewritten.

Select your actual piano in **Settings → Piano input**. A virtual MIDI Through
port is not automatically treated as a connected instrument. Play a note to
verify actual input activity. A saved available device reconnects automatically.

## Built-in warm-ups

**Music → Built-in warm-ups** includes six original beginner studies.
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
locally. Two wrong/missed required notes within a two-bar warm-up chunk trigger
a boundary retry at 90% tempo. A failed full-study review stays available for
the learner's next choice. Count-in, moving notation, Listen, manual Restart
and hands-free MIDI start still work. Without a piano, a timing preview cannot
earn mastery.

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

Python's sampled musical clock is projected at the requested BPM. The frontend
calibrates its process-clock offset from low-latency idle responses and freezes
that calibration while notes move. It does not adjust camera tempo to chase
polling jitter. Retry, pause, resume, score changes and actual seeks reset the
projection synchronously. This supersedes the earlier phase-error filter and
2% tempo correction. See the [regression report](docs/regression-recovery-2026-10-17.md).

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

### Settings layout and screenshot regression

Settings groups MIDI input, the music folder, tempo, Listen volume and display
preferences in a dedicated view. Folder controls align horizontally on wide
windows and stack on smaller ones. The content scrolls on short displays;
the navigation rail remains available. Godot checks the actual field and button
bounds at 1536×960, 1280×800, 1024×768 and 800×600.

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
view; keyboard shortcuts remain available: **Space** Play/Pause, **R**
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

## Practice-first navigation

The application starts on the practice stage. Until a piece is loaded,
**Choose music** opens the library. **Music**, **Path** and **Settings** open
dedicated views with a shared navigation rail; **Practice** or Escape returns
to the score. The score stays mounted behind these views.

Opening another view during playback requests Pause. The existing transport
ID, score and progress remain intact, and returning does not silently restart
the attempt. A library selection made during the asynchronous pause is queued.
Selecting a different imported piece presents the starting-measure selector.

Verify all window sizes with `./scripts/check_godot.sh`, and use the desktop
checks to inspect rendered screens and actual notation movement.

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

Open **Music → Check files** to inspect your MIDI and MusicXML
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
Practice uses five errors in a rolling two-bar window. The captions name the
original/next tempo and retry measures without covering notes. A clean partial retry
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

The visible playback check starts the ordinary `./run.sh` launcher with no MIDI
device, presses the real Play/Pause/Resume controls, and captures the same note
at 30, 40, 80 and 120 BPM. It
checks local raster ink, leftward movement, fixed timing line, stable scale,
constant pixels per beat through the downbeat, pause/resume, restart and a
naturally completed ungraded preview. It writes PNGs,
JSON measurements and logs. `--bpms 40` selects a shorter probe; `--resolution
1024x768` selects a window size. The UI check runs **the normal `./run.sh`
launcher**, opens a real piece, exercises controls and captures all screens at
1536×960, 1024×768 and 800×600. Both use isolated progress/preferences, preserving
existing user data and source files.

The [17 October handoff verification](docs/handoff-verification-2026-10-17.md)
records the subsequent fixes for phase-dependent zoom, clipped notation,
expressive MIDI rest/tie clutter, rolling recovery and interrupted clean streaks.

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

## Starting-point picker and fullscreen layout

Selecting a MIDI file now closes the Music drawer and opens a responsive,
centered in-app starting-point panel, rather than a malformed narrow native
subwindow. The panel keeps source-measure selection, Learn vs Practice mode,
explicit Cancel and Open actions, and Escape/Enter keyboard support. The
dialog's content is sized independently of screen aspect ratio; layout tests
exercise the modal at desktop and smaller windows.

## Semantic button hierarchy

Actions now have reusable visual roles rather than identical rectangle
skins. Mint-filled **primary actions** advance into practice; amber **review
and retry** controls communicate repetition; blue **settings and listening**
actions suggest audio/configuration; neutral ghost **navigation and utilities**
stay subdued; coral **stop/quit** actions read as interruptions; lesson-hand
**choices** show their selected state. Library entries display a dedicated
music-note glyph and read as selectable rows rather than competing call-to-
action buttons. The three tactile transport keys remain the largest and keep
their own Play, Retry and Listen iconography. Hover, pressed, disabled and
keyboard focus are styled for every role, and standard buttons continue to
use their original callback and accessibility text.

## Unified visual system

All views reuse `godot/practice_theme.gd`: the moodboard's forest, pine,
charcoal, sage, slate and stone palette, serif titles, sans-serif controls,
small rounded borders and one teal action accent. Retry and Listen share a
neutral surface; Play is emphasized. White active staves and muted inactive
hands remain legible against the dark score. The backdrop is a flat forest
surface, with no decorative light bursts around the music.

## Note feedback

Fresh, graded MIDI attacks produce small fading notehead contours and brief
coaching text. Preview and Listen remain ungraded. The five-part progress rail
shows actual backend progress with muted remaining segments. The timing line
uses the same backend clock as the moving notation.

## Rhythm-game response, moodboard animation pass

The dark, high-contrast practice stage keeps the engraved score dominant.
Visual beat ripples follow the existing backend-driven musical clock at
the fixed playhead; they cannot shift score timing or grant note success.
Transport keys respond with stronger, short press/hover light and then
sleep when idle. MIDI-triggered coaching cards enter with a small overshoot
and note-colored token rather than a web-style rectangular toast. Earned
progress leaves a short light trail below the staff, while ungraded preview
retains its distinct blue treatment. All effects are drawn on existing
Godot controls, with no GPU particle emitters or fullscreen postprocessing.

## Music selection and start-point usability

The library shows clickable music tiles in two columns on wide windows and
one column on smaller windows. Serif titles sit above real format, tempo and
folder metadata; full details remain in tooltips. Recently opened music comes
first, then personal files and built-in warm-ups. Search supports **Ctrl+F**
or **/**. Starting a MIDI file offers Beginning, Middle and End jumps alongside
the exact measure spinner and slider. Enter confirms once; Escape returns to
the library, and an open mode menu retains Enter.

## Performance pass - stable notation and lightweight animation

Searching a music library also coalesces rapid text edits for 120 ms,
avoiding repeated reconstruction of hundreds of buttons on each keystroke.
Idle, paused and drawer views now target 30 FPS, automatically returning
to 60 FPS for active practice. The score strip indexes note IDs to their
engraved system at assembly time, removing repeated full-score scans
when the backend reports feedback. Score spacing is now evaluated with
a monotone binary lookup rather than
scanning every stored control point for each note. During playback the actual
score/camera still updates at up to 60 FPS, while the translucent notehead
effects have a 30 FPS visual redraw limit. Ambient lighting uses its original
20 FPS cadence rather than repainting on every fractional beat update; a
meter or beat-boundary change still forces an immediate update. Expired
particles clear immediately. These changes only affect display scheduling,
not audio playback, MIDI timing, grading, or tempo.

## Phase 7.8 - CPU and camera stability

For high-refresh-rate Linux laptops, the display is capped at 60 visual
frames per second (the musical transport and MIDI assessment are not capped).
Camera anchor lookups use binary search, and static score bounds are cached
by score revision instead of rescanned each frame. The ambient stage now
uses a single opaque background and a small number of light passes, avoiding
overdraw from large translucent gradients. The count-in drawing no longer
uses an opaque rectangular background over the moving staff. HiDPI
engraving remains vector sourced, but requests are bounded to 5200px
and 10 megapixels per source page to reduce decode and raster cost.
The note burst now uses eight clean foreground comet trails and a light
double ripple, instead of sixteen equally bright radar-like spokes; the
original notehead and accidental remain unobscured. Frame interval
statistics can be enabled with `--frame-diagnostics`.

## HiDPI score readability

The notation now scales with the *available score-stage height* instead of
stopping at a fixed 27px staff gap. It keeps the complete two-hand grand staff
on screen with space for ledger notes, and reserves more window height for the
actual score. The Godot client measures the engraver's staff-line proportions
and requests a higher-resolution PNG for the entire exercise
(`/score.png?page=0&width=N`), subject to an 18-million-pixel working
budget and a 7200px width ceiling. CairoSVG renders the underlying **SVG
vectors at the requested resolution**; Godot does not upscale the previous
2000px PNG. Old clients continue to receive the standard 2000px images, and
the server caches only one raster resolution per page. The score revision
uses one consistent density across all pages, so texture and overlay
coordinates, metronome timing and tile residency remain unchanged.

## Preview notation scale and continuous scrolling (Phase 7.6 follow-up)

The grand staff determines zoom, and one continuous staff layer
joins the engraved systems. For **generated piano practice exercises** with
unchanging notation, the strip now applies a **tempo-proportional spacing
pass** after Verovio resolves note collisions: every source-beat interval
(including printed system joins) is assigned the same horizontal length.
The score camera consequently moves at an unchanging pixels-per-second rate
at the selected BPM, and noteheads still cross the playhead exactly on the
audible metronome beat. The spacing pass stretches only intervals between
protected notehead/accidental zones, never the notehead itself. Printed-system
tiles remain bounded in size, and the long-score deferred upload path is
preserved. Imported scores with changing clefs, meter or key keep their
native notation, rather than risking damaged glyphs in this first version.
Preview/Listen have blue-white, ungraded note-arrival bursts; graded MIDI
success is mint/coral. This display work never changes assessment timing.

## Phase 7.7 - Resonance (visual polish)

Phase 7.7 is implemented on `main` in four layers:

- **7.7a, continuous score:** generated multi-system strips now replace
  isolated horizontal raster staff rules throughout *each entire tile*,
  not merely nine pixels at its edges. A column containing any musical ink
  outside the staff-line bands (barline, tie, stem, note, clef, etc.) is
  preserved without modification. One continuous staff underlay provides
  identical line weight through every seam. Genuine printed measure
  barlines remain musical and are not removed. The rail redraws only after
  a score or viewport size change, not on every camera frame.
- **7.7b, Resonance note impacts:** physically assessed correct MIDI
  attacks produce a layered, additive glow, sixteen deterministic sparks
  extending several staff spaces, luminous staff-line resonance, and a
  prominent bright outline *above* the engraved notehead. Correct chords
  naturally accumulate light from their individual notes. Early/late hits
  use amber; unexpected notes use restrained coral ticks without a
  success flash. MIDI hits suppress the warm upcoming-note cue for that
  note so colors do not collide between backend polls. Animations last
  at most 450 ms and render at most sixteen concurrent hits; there are
  no allocated particle nodes, random timers or grading changes. Listen
  and keyboard-free preview cannot produce a correct-note burst; entering
  those modes also clears any lingering effects from a graded take.
- **7.7c, ambient stage:** the score has a breathing studio glow and
  fixed playhead illumination. Assessed MIDI input produces green or coral
  note impacts and strengthens stage lighting. In keyboard-free Preview and
  Listen, actual source onsets produce **blue-white, explicitly ungraded**
  particle bursts and stage pulses so the effects can be inspected without
  a keyboard. Those effects never generate grades, achievements or hand
  progression. Bright sparks draw above the opaque engraved image while
  their soft halo remains behind it, preserving readable noteheads.
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

## Phase 8E - Bounded local Listen-audio storage

Generated Listen WAVs now have explicit default retention limits:
**512 MiB** total and **32** completed cached files. Cleanup runs
after a cache hit or successful render. It keeps the most recently
requested WAV and every currently rendering key, including overlapping
background renders. If the currently needed WAV itself exceeds the
limit, it is preserved rather than deleting the active example.

Eviction affects only SHA-256-named `.wav` files inside Piano Teacher's
own demo-audio directory. Partial `.tmp` renderings, original
recordings, SoundFonts and unrelated files are never removed.
Generated clips retain reproducible cache keys and unchanged
modification timestamps on cache hits.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q \
    tests/test_demo_cache_bounds.py tests/test_demo_audio.py \
    tests/test_listen_perform.py
```

This bounds *long-term disk usage*, not memory needed to decode an
individual long recording.

## Phase 8F - Long-score draw-call reduction

For a scrolling piece with many systems, Godot now draws only the
engraved system tiles intersecting the score viewport plus a generous
offscreen safety margin. All textures and authoritative positions remain
in memory for instant seek, pause and resume. A hidden system reappears
immediately as it enters the viewport; the real playhead must always
have its underlying engraved tile. Measured staff continuity, source
note identities, clefs, accidental ink and timing are unchanged.

The atmospheric lighting layer is capped at 30 redraws/second during
ordinary playback; actual MIDI hits still produce immediate impact
frames. The opt-in `--frame-diagnostics` log now reports both total and
*visible* system tiles, so it is possible to verify culling on an
actual long piece. This reduces drawing work, **not** the RAM/VRAM
held by preloaded image textures.

Regression checks:

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q tests/test_score_strip.py \
    tests/test_phase77_game_feel.py tests/test_frame_meter.py
./scripts/check_godot.sh
./run.sh -- --frame-diagnostics
```

Test normal practice and a seek across multiple printed systems. FPS
must be measured on the actual laptop; the presence of tile culling
is not evidence of a particular achieved frame rate.

## Phase 8G - Camera update complexity for long scores

The virtual score keeps the same original Verovio image tiles and scroll
transform. During normal playback, tile-local position and size are now
cached: only a zoom/score change rebuilds these values. The moving
camera changes one parent coordinate, and two binary searches identify the
small contiguous interval of tiles actually needed at that moment.
Visibility updates touch only tiles that enter or leave this interval.
A large seek can touch many nodes once; steady motion no longer loops
over every printed system to reposition or check each texture every frame.

The viewport uses the same generous offscreen margin as Phase 8F. The
visible tile count reported by `--frame-diagnostics` is taken from the
cached interval. Godot regression fixtures verify that range selection
agrees with the original per-tile predicate through scrolls and zooms,
and that the real engraved tile under the playhead stays visible.
This optimization does not alter the MIDI clock, audio stream, sound
samples, assessment or the original texture residency in memory.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q tests/test_score_strip.py
./scripts/check_godot.sh
./run.sh -- --frame-diagnostics
```

Long-score and multi-system seeks still need visual examination on the
actual desktop. FPS and VRAM improvements cannot be inferred from
source-level complexity alone; report on-device measurements.

## Phase 8H - Compact score-tile uploads

All Verovio engraving tiles now use a two-channel `Image.FORMAT_LA8`
luminance/alpha image before creating their Godot texture. The source
PNG scores are monochrome with anti-aliased transparency; source
position, exact notehead shape, image dimensions and glyph opacity
remain unchanged. Staff joins and MIDI feedback are processed before
tile conversion. For the same raster dimensions, raw tile image data
requires **two bytes/pixel**, rather than the previous RGBA8
**four bytes/pixel**. Actual VRAM residency is driver-dependent and
must be checked on the hardware.

The opt-in `--frame-diagnostics` log now reports
`tile_upload_mib` together with score tile counts, geometry rebuild
counts and frame intervals. It measures the sum of raw submitted image
bytes, not the OpenGL/Vulkan driver's allocated GPU memory.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q tests/test_score_strip.py
./scripts/check_godot.sh
./run.sh -- --frame-diagnostics
```

Open a short warm-up and a long imported piano piece. Verify that
treble/bass ink, accidentals and the final barlines look identical to
the earlier version, including at system joins. No difference in
scoring, MIDI timing, navigation, audio or exercise selection is
intended.

## Phase 8I - Bounded GPU residency for long scores

Short lessons (fewer than 8 engraved systems) still upload their
complete score immediately. Longer lessons keep each Verovio system
as a reversible, lossless FastLZ-compressed LA8 image buffer, without
creating an initial GPU texture. On-screen systems plus two neighbouring
systems to either side are uploaded on demand. Camera movement only
restores arriving textures and releases the `TextureRect.texture`
reference for departing textures. A seek restores all required score
ink *before* committing the new visibility window. If unpacking fails,
the app displays a score error rather than pretending a musical note
was rendered.

The hidden full-page score texture is also gone: a tiny marker now
represents completed score readiness, while the engraved system tiles
remain the only source of visible notation. Score overlay and MIDI
reactions continue using original note IDs and the same measured
coordinate transforms. Previous full-page source images are released
once all tiles have been built.

Frame logs from `./run.sh -- --frame-diagnostics` distinguish
`tile_upload_mib` (all raw tiles if eagerly uploaded),
`resident_tile_mib` (raw size of currently uploaded tiles) and
`packed_tile_mib` (sum of compressed CPU-side tile buffers).
These are source-pixel estimates, not measured GPU driver VRAM.
Also check `resident_tiles` and `tile_restores` after seeking
through a long piece. On the desktop, first seeking and fast jumps
might still require noticeable synchronous decompression; hardware
acceptance must rule out audible/visible interruptions.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q \
    tests/test_score_strip.py tests/test_score_motion_render.py \
    tests/test_godot_practice_smoke.py tests/test_raster_pipeline.py
./scripts/check_godot.sh
./run.sh -- --frame-diagnostics
```

## Phase 8J - Consolidated real-hardware acceptance evidence

The full device acceptance evidence is now collected by the **single
`playtest.py` launcher** described above. That entrypoint replaces the
previous multi-terminal instructions to start the hardware capture,
grade capture, Godot logging and separate acceptance summarizer.

It uses the same authoritative Python backend events and the original
Phase 8 diagnostic parsers. The final report includes attacks/releases,
pedal counts, clean takes, hand progression, frame timing, texture
residency and software Listen drift. Physical input/output/display
latency still requires separate hardware instrumentation.

## Phase 8K - Automatic reconnect of selected USB MIDI piano

The backend now remembers the piano explicitly selected in Settings and
tries that *exact* MIDI input again when it returns after USB unplug/replug
or a backend restart. Background discovery is performed at most once every three seconds,
and failed reopen attempts are rate-limited to one every four seconds.
This avoids spinning while ALSA releases a USB device.

Background state polling limits MIDI input enumeration to once every
three seconds; opening the Settings device list still explicitly refreshes
the available inputs on demand. Failed reopen attempts are never faster
than once per four seconds. Disconnection cancels the current attempt
and any pending clean result, clears transient note input, and stops
hardware diagnostics.
When the original port returns, the app reports that the piano
reconnected and requires the learner to press **Start**. It does not
automatically resume playback, fabricate notes or award progress.
It never substitutes a different available MIDI input. Explicit
disconnect in Settings clears the saved preference and disables
automatic reconnect. If the operating system renames a MIDI device on
replug, select the correct new name once in Settings.

Automatic discovery also runs when the app is open without a keyboard;
a saved preferred piano that becomes available later is attached without
repeated visits to Settings. Transient discovery errors do not break the
score state API or close a known healthy port.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q tests/test_midi_reconnect.py
./scripts/check_godot.sh
./run.sh
```

**Real piano acceptance:** connect the Kawai, begin a graded warm-up,
unplug it while playing, and verify the attempt cancels without
mastery. Reconnect it and confirm the same input reappears and does not
play or grade until Start is pressed. Repeat after restarting the app,
then test explicit Disconnect. No real USB event has been simulated as
proof of hardware acceptance.

## Phase 7.8 - Score-stage visual polish

The practice screen is now more instrument-like without introducing any
new routine control. The stage lights breathe softly at the real
playhead (42% across the notation viewport), and a tiny metrical pulse
shows the backend's current beat. MIDI-free preview and Listen use a
restrained neutral colour, never a fake clean-note response. During
graded practice, real assessed MIDI note-on events generate a short,
bright, differently coloured burst for on-time, early/late and
unexpected input. The glow fades naturally while the original
Verovio noteheads and feedback remain fully visible above it.

Count-in has a readable numeric 3-2-1 (or whatever number of
preparation beats the backend supplies) beside the existing small
meter lights. Both disappear precisely at the first playable beat;
pausing freezes the stage and hides the countdown. These effects use
the very same extrapolated **Python-owned musical clock** as the moving
score, not local timing or a second metronome. The compact phase cue
has clearer type, and the left/right/both learning ribbon has a
subtle illuminated active-state edge instead of large website cards.

Verify the real UI modules and unchanged transport interactions:

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q \
    tests/test_phase78_stage.py tests/test_phase77_game_feel.py \
    tests/test_practice_interactions.py tests/test_score_motion_render.py
./scripts/check_godot.sh
./run.sh
```

During an actual warm-up check the moving count-in, neutral
preview, live green/orange/red note reactions, paused score and
an uninterrupted three-clean-run progression. Scores, grading, lesson
unlocks and source notes are not modified by this visual phase.

## Phase 7.9 - Instrument feedback and clean-pass transitions

The practice heading now contains a compact **MIDI CONNECTED / NO PIANO**
status light next to tempo and the active hand. It briefly pulses when
the backend reports a new physical MIDI note-on. An old event count
from app startup cannot fabricate a fresh attack, and disconnect
immediately extinguishes the light. Ungraded preview is explicitly
labelled `PREVIEW`, not a successful or scored performance.

A completed graded take now sends a short, subtle light wave across the
performance stage. Clean passes are teal; retries are coral. The wave
starts only when a new backend-confirmed take result arrives and never
restarts on ordinary `/state` polls or on a pause/resume. Preview
and Listen do not trigger a graded result celebration. The complete
sheet-music raster remains above this stage lighting, so no notes,
accidentals or staff endings are painted over.

The three-clean-run indicator is now a legible, charged three-segment
instrument rather than tiny outlined dots. Its filled segments still
come exclusively from the backend streak; MIDI-free preview can never
light one up. Real hand-unlock transitions retain their animated sweep.

Upcoming source notes/chords also use a larger, softly animated warm-gold
ring. This distinguishes **what to play next** (gold) from **what you
actually played correctly** (teal), timing discrepancies (amber), and
unexpected notes (coral). It remains a thin outline around the exact
Verovio notehead rather than a new pitch glyph or an opaque mark.

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
.venv/bin/python -m pytest -q \
    tests/test_phase79_status.py tests/test_phase78_stage.py \
    tests/test_phase77_game_feel.py tests/test_practice_interactions.py
./scripts/check_godot.sh
./run.sh
```

The Godot fixtures cover input activity, status cycling, once-per-take
celebration, exhausted animations, disabled preview scoring and the
real practice UI hierarchy. Check the brightness and score readability
on the actual desktop before regarding the art direction as final.

## Remaining limitations

Physical speaker audibility/latency and a real USB piano session still need
validation with the student's instrument. Software desktop checks establish
visible motion and click scheduling, not physical timing quality.

General MIDI quantization, hand corrections, preserved source engraving/key
metadata, pedal scoring, fingering hints, and musical phrase inference remain
future work. Listen supports an optional sampled acoustic piano and retains a
basic harmonic fallback; both decode the completed WAV in Godot and have a
bounded disk cache. Irregular supported durations are split into tied
notes/rests or explicit tuplets for engraving; original MIDI events remain the
assessment source. Very long pieces preload cropped score textures: memory use
grows with the piece, with additional transient raster memory.
Streaming only neighboring systems is future performance work.
