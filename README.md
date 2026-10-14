## Phase 0 - real integration smoke

The automated Phase 0 check generates a short two-hand MIDI and exercises the
actual music21 -> Verovio -> CairoSVG -> PNG renderer and HTTP practice service.
It verifies library import, note coordinates, decoded PNG, count-in and a timed
preview without false mastery. It runs in an Arch Linux GitHub Actions container
with the Godot binary installed, so the GDScript check cannot silently skip.

After a pull and `pip install -e '.[godot,test]'`, run:

```bash
python -m pytest -q
./scripts/check_godot.sh
python scripts/smoke_phase0.py
python scripts/smoke_godot.py
python scripts/smoke_phase0.py --file "$HOME/Music/Piano Teacher/your-piece.midi"
./run.sh
```

The smoke checks rendering and API semantics but does not prove that audio,
score animation, or USB MIDI hardware work in a visible Godot session. This
still requires on-machine testing before Phase 0 can be declared complete.
The launcher now stops if port 8765 is already occupied by an older backend.

## Validate Godot before running the application

Python tests alone cannot detect GDScript parse errors such as undeclared
variables. On a Linux machine with Godot installed, the Python test suite now
also checks the Godot script with the real headless parser:

```bash
python -m pytest -q
./scripts/check_godot.sh
./run.sh
```

The last two commands are separate deliberately: the parser test should fail
before the fullscreen application is launched when there is a GDScript error.
This is independent of the `DRI_PRIME` Mesa device-selection warning.

## Audible count-in, moving notation and live MIDI feedback

Start begins your **own MIDI-piano practice performance**. It does not play
the imported MIDI file. The app now plays a clearly audible count-in, then
beats while you perform. The display counts down, flashes PLAY at the start,
and reports incoming USB MIDI note-ons so input problems are visible.

The score is cropped to its engraved content, enlarged and moves horizontally
beneath the timed playhead. The complete inactive staff, including ledger lines
and stems, becomes faint during one-hand exercises. Imported tempo markings
are removed from individual short lessons; the selected BPM remains in the UI.

The Listen button remains disabled pending a proper piano-sound demonstration
player. Actual device and sound synchronization still need on-machine testing.

## Diagnose sheet-music rendering

The Python Verovio wheel bundles Bravura and Leipzig music-font resources. Piano Teacher
loads these from the installed Python package rather than relying on Verovio's
original build-time default path, which can be invalid on Arch Linux.

After updating, verify engraving **without Godot** using a MIDI or MusicXML file:

```bash
cd ~/Projects/piano_teacher
source .venv/bin/activate
python scripts/check_engraving.py "/path/to/your/file.midi"
```

This exercises the actual import, music-font loading, engraving, SVG geometry
and note timing map. It should report `ENGRAVING OK` with page and anchor counts.
If the installed wheel lacks fonts, it will report the missing resource path and
the precise reinstall command. After the standalone check passes, run `./run.sh`.
The Mesa `DRI_PRIME` warning is unrelated to score rendering.

# Piano Teacher

A native Linux piano tutor with a minimal **Godot 4** interface and Python practice engine. Load your own MIDI or MusicXML files. The score is engraved as **traditional piano sheet music** with treble and bass clefs by music21 + Verovio (no piano roll).

## Fullscreen music library and settings

The application now launches into a **fullscreen home menu** (press **F11** to switch between fullscreen and windowed). Select **Browse library** to see a searchable list of pieces. There is no need to open MIDI files one by one: Piano Teacher indexes all `.mid`, `.midi`, `.musicxml`, `.xml`, and `.mxl` files in your configured directory **and subfolders** automatically. The list refreshes approximately every five seconds while the home or library screen is visible. Folder scanning reads filenames only; full scores are parsed when you select a piece.

By default, the folder is `~/Music/Piano Teacher` (created on first launch). Use **Settings > Music library > Browse...** to select any existing folder on Linux. The choice, fullscreen setting, MIDI device and last successfully loaded score are saved locally in `~/.config/piano-teacher/settings.json` or `$XDG_CONFIG_HOME/piano-teacher/settings.json`. The **Continue** button on the main menu opens the last score and the existing SQLite mastery database restores its learning position. If the file has been removed, the button is disabled. Music files are never moved or rewritten.

The main menu includes **Browse library**, **Continue**, **Settings** and **Quit**. Settings is a separate screen for choosing a folder, selecting or refreshing the USB MIDI device and toggling fullscreen. The practice view retains only **Previous, Start/Stop, Next** and a disabled **Listen** control. Press **Escape** while practicing to return to the library, **Space** to start/stop, and **Left/Right** to navigate exercises. The engine stops an active attempt when leaving practice.

## Practice screen and sheet-music display

The practice view now separates the navigation bar from the title, tempo and hand
labels, so text cannot wrap vertically and take up the full screen.

Verovio still engraves the notes and supplies timing/position metadata, but
Python now rasterizes the SVG pages through CairoSVG before Godot displays them.
The backend caches the PNG per score revision and checks that there is visible
ink. A failed conversion or blank page is reported rather than presented as a
white score. The original SVG remains available for troubleshooting.

After updating the code, reinstall the Godot extras to include CairoSVG:

```bash
cd ~/Projects/piano_teacher
git pull --ff-only
source .venv/bin/activate
python -m pip install -e '.[godot,test]'
python -m pytest -q
./run.sh
```

To verify actual Verovio engraving **and** PNG rendering without Godot:

```bash
python scripts/check_engraving.py --output /tmp/piano-score.png "$HOME/Music/Piano Teacher/your-file.midi"
```

The first page should be saved as `/tmp/piano-score.png`. Open it with an image
viewer. The backend endpoints are `GET /score.png?page=0` for the application,
`GET /score.svg?page=0` for examining the original engraving, and
`GET /score/layout` for timing and notehead coordinates.

## Install and launch on Arch Linux

```bash
sudo pacman -S godot python python-pip alsa-utils
python -m venv .venv
source .venv/bin/activate
pip install -e '.[godot,test]'
python -m pytest -q
./run.sh
```

`run.sh` starts a loopback-only Python backend and opens the Godot application. Drop MIDI or MusicXML scores into your music folder, choose one from the library, connect your USB MIDI piano through Settings (single available devices are auto-selected), then use **Start**, **Previous** and **Next**, or Space/arrow keys. There is no account or network service; all processing is local. `aconnect -l` helps diagnose a missing ALSA MIDI connection.

## Implemented in this first Godot iteration

- Godot 4 fullscreen, light-coloured interface with a home screen, automatically indexed music library, settings and a separate distraction-free practice screen. The SVG score comes from Verovio, with a full-page score panel and overlaid playhead.
- Python backend preserves accurate MIDI event timestamps independently from screen rendering.
- Mido/Music21 import paths and hand identification, plus score engraving for the current exercise.
- Two-measure learning with automatic overlapping connections: **1–2 → 3–4 → 1–4 → 5–6 → 3–6**, followed by full-piece practice.
- Right hand then left hand then both for learning exercises (skips hands without notes). Connections assess both hands.
- Starts at **40%** original tempo; adjusts speed after consecutive clean performances, with progressive smaller increments and slowdown after repeated failures.
- Pitch, ±100 ms onset timing, and ±20% duration scoring (with a 55 ms minimum duration tolerance); wrong pitches are distinguished from missed and extra notes.
- After every attempt, noteheads on the engraved score receive small coloured feedback markers for correct, wrong, early, late, too-short, too-long and missed notes. Unrequested extra notes are marked above the system at their timed x-position, labelled by pitch (not falsely assigned to an engraved notehead). If MIDI-to-engraving alignment fails for a note, the feedback reports it as unpositioned.
- Completed attempts remain on the original score for 2.5 seconds before automatic tempo, hand or exercise progression. The feedback remains correctly associated with its source score.
- Automatic retry and progression, manual passage navigation, progress saved locally in SQLite under `$XDG_DATA_HOME/piano-teacher` (usually `~/.local/share/piano-teacher`).

## Recover from an interrupted Git update (local `run.sh` changes)

If `git pull --ff-only` says that local changes in `run.sh` would be overwritten, **preserve** your local changes before updating:

```bash
cd ~/Projects/piano_teacher
git stash push -m "local run.sh before piano teacher update" -- run.sh
git pull --ff-only
source .venv/bin/activate
python -m pip install -e '.[godot,test]'
python -m pytest -q
./run.sh
```

The stash preserves your previous `run.sh` changes; see them with `git stash list` or `git stash show -p stash@{0}`. Do not blindly apply the old launcher over the new one. If other files have local modifications, inspect `git status` before attempting the pull again.

`run.sh` uses the checkout's `.venv/bin/python` where available, exports the repository root on `PYTHONPATH`, checks that `piano_teacher.server` imports, and waits for its `/state` endpoint before starting Godot. The Godot interface now handles empty, invalid or unavailable HTTP responses without emitting JSON parse errors. If the Python backend cannot start, check the terminal message; an unrelated `DRI_PRIME` warning from Mesa is not a backend failure.

## Current limitations - important

This is an **initial playable vertical slice, not a finished teaching app**. Godot and the Verovio/music21 score pipeline have **not been run together on physical Linux hardware in this environment**. The playhead now uses quarter-beat timestamps linked to actual Verovio SVG notehead positions, rather than assuming uniform horizontal spacing. It handles score line and page changes. **It has not been verified end-to-end with a local Verovio/Godot runtime or physical MIDI hardware.** The cursor currently interpolates between engraved note/rest *onsets*, holds after the last positioned event and may not reach the exact barline during long final rests. Tempo/passage grading remains independent of rendering. The score service explicitly reports missing geometry instead of silently using inaccurate percentage-based positioning.

MIDI-to-score quantization and multi-staff inference depend on music21 and are not reliably correct for all performance MIDI files; manual hand reassignment and note/finger-number overlays are not implemented. MusicXML ties spanning multiple notes require a stronger canonical note merger. The inactive-hand greying currently works only for conventional two-part scores. The **Listen** button is intentionally disabled until on-demand synthesis is implemented. MIDI sustain pedal events are not yet scored. The legacy Qt piano-roll app remains in `piano_teacher/ui.py` but is not part of the new Godot entrypoint.

## Engraving geometry API

After loading a piece, the backend offers `GET /score/layout` (quarter-beat anchors, system/page identifiers, normalized notehead coordinates), and `GET /score.svg?page=0` (zero-based page index). The state endpoint includes `beat` and `duration_beats`. Godot interpolates the cursor in beat space between server samples and transforms normalized coordinates into the *aspect-fitted SVG image area* to prevent offsets from letterboxing. The API reports an error when no graphical timing correspondence is available. The backend caches the layout by score revision. The layout now also includes positioned noteheads with Verovio IDs, sounding MIDI pitches and quarter-beat onsets. At the end of an attempt `GET /state` provides `feedback_marks` (note ID, page, x, y, status) and `feedback_unmapped` during the feedback interval. For pitches, the engine queries Verovio's MIDI output rather than guessing sharps/flats from the visual notehead position.

## Additional backend API

- `GET /library` - recursively list supported local scores, metadata, recent ID and missing-folder diagnostics.
- `POST /library/open` with `{ "id": "subfolder/score.mid" }` - open a validated score inside the configured folder, then record it as recent.
- `GET /settings` - read stored preferences.
- `POST /settings` - save one or more of `music_dir` (existing directory), `fullscreen` (boolean), or `midi_device` (name). Music folder changes reset the recent score.

No additional web server is exposed: all endpoints remain on `127.0.0.1`.

## Backend-only testing

```bash
python -m pytest -q
python -m piano_teacher.server --no-midi
# In another terminal:
curl http://127.0.0.1:8765/state
```

If `ModuleNotFoundError: piano_teacher` appears, make sure you are in the repository root and use `./run.sh`: the launcher now explicitly sets the source directory on `PYTHONPATH`, selects the project's `.venv/bin/python` when present, validates its import, and waits for a ready backend before opening Godot. Pytest also sets the project root on its import path. The `DRI_PRIME` warning reported by Mesa is independent of this backend import failure.

The Python backend deliberately binds only to `127.0.0.1`. The geometry and wrap handling are verified with synthetic Verovio-shaped SVG/timemap tests; these do not substitute for testing a real score engraving. To inspect Godot without a MIDI keyboard, start the server with `--no-midi` and then `godot --path godot` (but practice cannot be meaningfully graded without real MIDI input).

## Next milestones

1. Run a real Godot/Verovio integration smoke test on Arch; verify that Verovio 5.7 returns note MIDI values for all rendered notes, that actual SVG pages open in Godot, and that each result marker aligns to its notehead.
2. Canonical MusicXML/MIDI reconstruction: clef/staff accuracy, ties, quantization, hand corrections, note/finger overlays.
3. End-to-end physical MIDI and latency tests, on-demand Listen synthesis, stronger scoring for pedal/legato, and contextual hand/tempo controls.
4. Linux release packaging and visual usability polish.

## Troubleshooting blank scores and fullscreen layout

The Godot interface reflows the Home cards and Music Folder controls to fit
smaller or scaled laptop displays. Long file names are truncated instead of
forcing content beyond the right edge; Home and Settings can scroll vertically.
F11 switches between fullscreen and windowed display.

After opening a song, the score panel displays **Preparing sheet music** while
the Python service imports and engraves the score. First-time MIDI engraving
may take longer than five seconds, so the frontend now waits for completion.
If MusicXML conversion, Verovio engraving, or SVG decoding fails, the score
panel shows the **actual error and a Retry score button** rather than leaving
an indefinite *Choose a piece* placeholder. Errors when opening an item from
the library remain visible on the library screen even after the periodic
folder scan.

If the score still fails, run `./run.sh` from a terminal and report the error
shown **inside the score panel** together with the terminal output. A Python
test run alone cannot validate real Godot SVG rendering; the frontend needs
interactive testing on your display.
