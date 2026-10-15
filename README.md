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

## Practice

Press **Start**. A short, audible count-in begins immediately and blank staff
space moves toward the fixed timing line. The first note arrives at its musical
onset. Notation continues moving from right to left even when you play nothing.
Without an input device this is an ungraded timing preview, which finishes
without awarding mastery.

Python owns one signed musical clock: negative beats are count-in, zero is the
downbeat, and positive beats are playback. Godot extrapolates snapshots between
HTTP polls. The raster, real noteheads, feedback and timing line share one
projection. Engraved systems are preloaded as separate horizontal tiles, so a
line or page wrap does not need a new image during playback. Transparent and
opaque image margins are handled correctly. Notation size remains stable.

Preparation lasts at most one bar and approximately four seconds. Settings can
turn off practice metronome beats; the preparation count-in remains audible.
Start does not synthesize the imported song. Piano-sound demonstration is not
yet implemented and there is no inactive Listen button.

Controls:

| Control | Action |
|---|---|
| Space | Start, stop, or resume |
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
```

The following checks require a graphical desktop and inspect **actual rendered
pixels**, not just increasing backend beats or camera log messages:

```bash
python scripts/check_visible_playback.py --output-dir /tmp/piano-visible
python scripts/check_desktop_ui.py "/path/to/music.mid" --output-dir /tmp/piano-ui
```

The visible playback check captures the same note at 30, 40, 80 and 120 BPM,
checks local raster ink, leftward movement, fixed timing line, stable scale,
pause/resume, restart and a naturally completed ungraded preview. It writes PNGs,
JSON measurements and logs. `--bpms 40` selects a shorter probe; `--resolution
1024x768` selects a window size. The UI check runs **the normal `./run.sh`
launcher**, opens a real piece, exercises controls and captures all screens at
1536×960, 1024×768 and 800×600. Both use isolated progress/preferences, preserving
existing user data and source files.

Automated Godot tests also exercise real engraving through multiple systems and
pages, transparent cropping, screen-space note projection, feedback and musical
joins. See [the local verification record](docs/verification-2026-10-15.md) for
results and the remaining physical acceptance work.

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
`/lesson`, `/score/layout`, `/score.png?page=0` and `/score.svg?page=0`. Settings
accept `music_dir`, `fullscreen`, `midi_device` and `metronome`. Layout contains
real notehead IDs/pitches, onset anchors, staff lines, system bounds and pages.

Python modules own importing, generated lessons, grading, recovery, curriculum
and SQLite persistence. Godot's `main.gd` owns navigation and API integration;
`score_strip.gd` owns tiled score coordinates and `practice_theme.gd` the shared
dark theme. The older Qt entrypoint remains available separately.

## Remaining limitations

Physical speaker audibility/latency and a real USB piano session still need
validation with the student's instrument. Software desktop checks establish
visible motion and click scheduling, not physical timing quality.

General MIDI quantization, hand corrections, preserved source engraving/key
metadata, pedal scoring, fingering hints, musical phrase inference and piano
synthesis remain future work. Irregular supported durations are split into tied
notes/rests or explicit tuplets for engraving; original MIDI events remain the
assessment source. Very long pieces preload cropped score textures: memory use
grows with the piece, with additional transient raster memory.
Streaming only neighboring systems is future performance work.
