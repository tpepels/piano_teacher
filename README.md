# Piano Teacher

A small, native Linux piano practice app. Load your own `.mid`/`.midi`, connect a USB MIDI piano, and play the notes under the moving vertical bar. No accounts, web browser, or bundled songs.

## Run on Linux (including Arch)

Install Python 3.10+ and your usual USB MIDI/ALSA support. In this directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m piano_teacher
```

Alternatively run `piano-teacher /path/to/song.mid`. On Arch, if your Python installation needs system packages to build `python-rtmidi`, install `alsa-lib` and `pkgconf`. The RtMidi/Mido backend uses ALSA MIDI ports on Linux. To diagnose MIDI connectivity use `aconnect -l` (package `alsa-utils`). Your instrument needs a **MIDI** USB connection, rather than just an audio connection.

## What it does

1. Select a MIDI file, then a connected MIDI input device.
2. The piece is divided into **two-measure passages** (uses the MIDI time signature). Rests are kept; silent passages are skipped.
3. Practice **right hand**, then **left hand**, then **both**. Named left/right MIDI tracks are respected; two pitched tracks are treated as lower/upper hands; a single unlabelled track is split at middle C (C4). Percussion channel 10 is ignored.
4. Start at approximately **60% of the file's initial tempo**, up to 72 BPM. A visual count-in runs before each attempt.
5. The app measures **which notes**, **when you start them**, and **how long you hold each key**. Two perfect attempts at one speed increase tempo by about 12% (minimum 4 BPM). A mistake repeats the same passage and tempo. After passing original tempo, it advances to the next hand or passage.
6. The background grid shows quarter-note beats, with horizontal note lengths and note names. Completed attempts show correct notes in green and errors/misses in red.

Use **Space** to start/stop, **left/right arrows** to move between passages. Set hand/tempo manually if needed. Playback/progression is automatic once started; stop it with Space. MIDI notes only count after the visual count-in.

## Deliberate limitations of this first version

- This reads MIDI data, **not microphone audio**. You need a MIDI-enabled keyboard; analog-only audio cannot be scored.
- The practice timeline is normalized to one tempo. MIDI tempo changes and expressive rubato are not reproduced as variations in the practice tempo.
- A single unlabelled track uses a C4 hand split, which will not fit every arrangement. For more reliable hand separation, export separate left/right tracks or label them `Left Hand` / `Right Hand`.
- Notes sustaining past a passage boundary are visually clipped and judged up to the boundary; carry-over notes are not separately requested at the next passage.
- No audio accompaniment/metronome sound yet: count-in and beats are visual. Keep the keyboard's local sound on so you can hear yourself.
- MIDI pedal (CC64) is not scored; key release durations are.

## Tests

```bash
pip install -e '.[test]'
pytest -q
```

The parser, phrase segmentation, grading and curriculum can be tested without Qt or MIDI hardware.

