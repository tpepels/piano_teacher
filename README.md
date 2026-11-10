# Piano Teacher

**[Current development roadmap](ROADMAP.md) · [Documentation index](docs/README.md)**

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
- New installations default to the adaptive **Coda + Fukuda MIDI** lesson
  route; existing saved strategies remain selected. The UI identifies the
  active generator and real note/rhythm/tempo transformation. Pure desktop
  Coda uses bounded passages; direct author-style Coda generation is retained
  for research parity.
- Onset spacing and tempo adapt to fast passages. The score, playhead,
  recovery and metronome share one presentation timeline.
- Incoming MIDI key-down and key-up events immediately enter one
  acknowledged feedback log, so a played note turns mint (or an early
  key-up lavender) before settlement; the authoritative assessment, published
  continuously during playback, then overrides it note by note.
- Wrong/missed/extra pitches are failures; yellow warnings cause a retry
  when at least half of distinct attacks are yellow.
- MIDI calibration uses a visible breathing beat, one initial four-beat
  count-in, and five uninterrupted eight-tap rounds. Robust outlier filtering
  requires at least four consistent rounds; the measured offset is saved only
  after explicit application. The same correction feeds live MIDI feedback
  and final assessment.
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

`scripts/ci-smoke.sh` is the push gate (fast, cheap contracts).
`scripts/ci-full.sh` is the release gate: the whole Python suite (25-45
minutes, run it before a release; run it on an otherwise idle machine, wall-clock budget tests are `flaky:` entries otherwise; pass `--durations=60 --junitxml=...` through to pytest). Known-red tests are listed with a reason
in `tests/quarantine.txt` and run as strict xfails: a quarantined test that
starts passing fails the gate until its line is removed, and a line naming a
test that no longer exists aborts the run.

The fast checks include a calibration-to-grading MIDI callback regression
and a tracked-file hygiene audit. They do not substitute for physical MIDI,
rendering or audio verification. Run exhaustive notation diagnostics locally using
`bash scripts/verify-notation.sh` when explicitly needed; they are not
part of short CI.

Local learning history is stored with progress in SQLite. Settings provides
detail retention (365 days / 256 MiB by default), local JSON export with optional
note detail, and confirmed deletion of piece or learner history and learning
progress. Reset Lesson preserves history. Exports omit source paths and device
names; exported copies remain outside the app's deletion control. See the
[learning evidence contract](docs/learning-measurement.md).

## Packaging

`scripts/package-inprocess.sh` assembles the distributable desktop
directory with Godot, GDExtension, CPython and offline inference runtime.
No compiler, SCons, system Python, pip or localhost service is required
for end users. Developer MIDI repertoire and MCP editor configuration are
excluded from the distributable. Linux hardware drivers are supplied by the operating
system. See [native runtime and packaging](docs/inprocess-runtime.md).

For reference specifications, verification and archived research evidence,
use the [documentation index](docs/README.md). The [roadmap](ROADMAP.md)
is the only active phase plan.

## Development-only editor tools

The vendored Godot MCP toolkit under godot/addons/godot_mcp_toolkit/ is
optional editor tooling. It is **not** part of the application architecture
and is stripped from release packages. Do not enable its editor WebSocket
service when testing network-free runtime behavior. Godot-generated .godot/
caches are ignored, whereas source .gd.uid identifiers are committed.
