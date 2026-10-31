# Piano Teacher

Offline desktop piano practice, built with Godot 4.7 and embedded CPython.
**One process, one runtime, one transport: in-memory command and MIDI event
queues.** No HTTP server, localhost port, UDP bridge or separate Python process.

## Running on a development machine

Arch Linux development requirements: Godot 4.7.2, Python 3.14, a C++ compiler,
SCons and the Python packages for this project.

```bash
sudo pacman -S --needed godot python base-devel scons git
python -m venv .venv
.venv/bin/python -m pip install -e '.[godot,test]'
bash scripts/build-inprocess.sh
./run.sh
```

The native build links a Godot GDExtension against CPython. The build
script runs a headless native startup smoke test: Godot must register
`PianoNative`, import the private Python practice engine and successfully
retrieve the user's MIDI library through the queue. The launcher also runs
this check if the native binary/manifest has changed. If the native bridge
cannot initialize, the app exits with a diagnostic; it never opens a
nonfunctional library screen.

Do not start `python -m piano_teacher.server`. The backend is part of
the desktop process and has no separate CLI or network listener.

## Product behavior

- Import `.mid` / `.midi` music, restore the last practiced score, and
  maintain independent lesson progress for hands and practice steps.
- Coda-inspired practice is the production default. Original Coda parity
  remains a separate research issue.
- Onset spacing and tempo adapt to fast passages. The score, playhead,
  recovery and metronome share one presentation timeline.
- Incoming MIDI note-on events immediately enter a bounded memory ring,
  allowing a provisional mint playhead pulse before final hold grading.
- Wrong/missed/extra pitches are failures; yellow warnings cause a retry
  when at least half of distinct attacks are yellow.
- MIDI calibration uses a visible breathing beat and three rounds, each
  with a count-in; measured offsets require explicit application.
- Overlapping MIDI voices retain their independent sounding durations and
  separate opposing stems in internally generated MusicXML for engraving.
- Offline fingering inference uses the included adapter. For a developer
  installation, run `bash scripts/setup-fingering.sh` once. The eventual
  binary package bundles its offline inference runtime.

The source is MIDI-only for the desktop product. MusicXML is an internal
engraving interchange format; features not recoverable from MIDI
(authored expression marks, detailed notation) are not fabricated.

## Tests

```bash
bash scripts/ci-smoke.sh
bash scripts/check-godot-syntax.sh
bash scripts/verify-native-bridge.sh
godot --headless --path godot --script "$PWD/tests/godot/visual_transport_clock.gd"
```

The fast checks do not substitute for physical MIDI, rendering or audio
verification. Run exhaustive notation diagnostics locally using
`bash scripts/verify-notation.sh` when explicitly needed; they are not
part of short CI.

## Packaging

`scripts/package-inprocess.sh` assembles the distributable desktop
directory with Godot, GDExtension, CPython and offline inference runtime.
No compiler, SCons, system Python, pip or localhost service is required
for end users. Linux hardware drivers are supplied by the operating
system. See [native runtime and packaging](docs/inprocess-runtime.md).

For further technical references see
[offline fingering](docs/piano-fingering.md) and the notation audit
reports in `docs/`.
