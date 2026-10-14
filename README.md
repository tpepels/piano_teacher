# Piano Teacher

A native Linux piano tutor with a minimal **Godot 4** interface and Python practice engine. Load your own MIDI or MusicXML files. The score is engraved as **traditional piano sheet music** with treble and bass clefs by music21 + Verovio (no piano roll).

## Install and launch on Arch Linux

```bash
sudo pacman -S godot python python-pip alsa-utils
python -m venv .venv
source .venv/bin/activate
pip install -e '.[godot]'
./run.sh
```

`run.sh` starts a loopback-only Python backend and opens the Godot application. Connect your USB MIDI piano, press **Piano** to select its MIDI input (single devices are auto-selected), then **Open file** to load `.mid`, `.midi`, `.musicxml`, `.xml`, or `.mxl`. Use **Start**, **Previous** and **Next**, or Space/arrow keys. There is no account or network service; all processing is local. `aconnect -l` helps diagnose a missing ALSA MIDI connection.

## Implemented in this first Godot iteration

- Godot 4 minimal, light-coloured interface with SVG score from Verovio, full-page score panel and overlaid playhead.
- Python backend preserves accurate MIDI event timestamps independently from screen rendering.
- Mido/Music21 import paths and hand identification, plus score engraving for the current exercise.
- Two-measure learning with automatic overlapping connections: **1–2 → 3–4 → 1–4 → 5–6 → 3–6**, followed by full-piece practice.
- Right hand then left hand then both for learning exercises (skips hands without notes). Connections assess both hands.
- Starts at **40%** original tempo; adjusts speed after consecutive clean performances, with progressive smaller increments and slowdown after repeated failures.
- Pitch, ±100 ms onset timing, and ±20% duration scoring (with a 55 ms minimum duration tolerance); extra notes and missed notes count as errors.
- Automatic retry and progression, manual passage navigation, progress saved locally in SQLite under `$XDG_DATA_HOME/piano-teacher` (usually `~/.local/share/piano-teacher`).

## Current limitations - important

This is an **initial playable vertical slice, not a finished teaching app**. Godot and the Verovio/music21 score pipeline have **not been run together on physical Linux hardware in this environment**. The playhead's horizontal movement currently follows the passage duration linearly across the page rather than the engraved horizontal positions of individual notes. This is especially inaccurate for multi-system four-measure scores. **Do not treat the graphic playhead as precisely aligned with notes yet.** Backend grading uses the actual passage time, independently.

MIDI-to-score quantization and multi-staff inference depend on music21 and are not reliably correct for all performance MIDI files; manual hand reassignment and note/finger-number overlays are not implemented. MusicXML ties spanning multiple notes require a stronger canonical note merger. The inactive-hand greying currently works only for conventional two-part scores. The **Listen** button is intentionally disabled until on-demand synthesis is implemented. MIDI sustain pedal events are not yet scored. The legacy Qt piano-roll app remains in `piano_teacher/ui.py` but is not part of the new Godot entrypoint.

## Backend-only testing

```bash
python -m pytest -q
python -m piano_teacher.server --no-midi
# In another terminal:
curl http://127.0.0.1:8765/state
```

The Python backend deliberately binds only to `127.0.0.1`. To inspect Godot without a MIDI keyboard, start the server with `--no-midi` and then `godot --path godot` (but practice cannot be meaningfully graded without real MIDI input).

## Next milestones

1. Align playhead and highlight individual engraved notes using Verovio element geometry/timing data; handle multi-system scores.
2. Canonical MusicXML/MIDI reconstruction: clef/staff accuracy, ties, quantization, hand corrections, note/finger overlays.
3. End-to-end physical MIDI and latency tests, on-demand Listen synthesis, stronger scoring for pedal/legato, and contextual hand/tempo controls.
4. Linux release packaging and visual usability polish.
