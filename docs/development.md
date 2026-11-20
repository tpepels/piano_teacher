# Development and acceptance

Start with [Practice flow](practice-flow.md), the [architecture](architecture.md)
and [repository instructions](../AGENTS.md). [ROADMAP](../ROADMAP.md) is the
product/phase record. Work on main, preserve unrelated changes and do not push
without authorization. The desktop has one embedded runtime; starting
`python -m piano_teacher.server` is not an application launch route.

## Build and run

The current Linux development setup uses Godot 4.7.2, Python 3.14, a C++ compiler
and SCons. Python packaging metadata permits older versions for core code; the
native extension must match the actual interpreter ABI. On Arch Linux:

```bash
sudo pacman -S --needed godot python base-devel scons git
python -m venv .venv
.venv/bin/python -m pip install -e '.[godot,test]'
bash scripts/build-inprocess.sh
./run.sh
```

For local automatic fingering, install Node.js 20+ and npm, then run:

```bash
bash scripts/setup-fingering.sh
```

Setup installs the pinned CPU runtime locally, verifies both model hashes and
runs real inference for both hands. Inference never downloads models during
practice. See [fingering provenance](reference.md#fingering).

[build-inprocess.sh](../scripts/build-inprocess.sh) builds an isolated output
then installs it by atomic replacement, preserving any old library inode mapped
by an editor. It generates the native GDExtension and imports Godot resources.
The linked `libpython` is promoted to global symbol scope before importing
Python extensions such as rtmidi and Verovio. A changed ABI requires a rebuild.

The build and launcher run [native startup verification](../scripts/verify-native-bridge.sh)
when required: `PianoNative` must register, embedded Python must import and
`library.catalog` must return its typed result. Failure prevents normal startup.
`PIANO_PYTHON` and `GODOT_BIN` select explicit developer runtimes where supported
by the scripts. Use the actual Godot project in [godot/](../godot/).

## Existing checks

```bash
bash scripts/test.sh
bash scripts/test.sh --python-only
bash scripts/verify-native-bridge.sh
bash scripts/verify-embedded-production-local.sh --without-package
```

The first command is also the [GitHub workflow](../.github/workflows/ci.yml):
core Python tests followed by Godot parser and existing component/UI scenarios.
The suite is deliberately small. Add a regression only after the owner confirms
the behaviour at the piano. Do not add abstract infrastructure, parity or pixel
tests; do not encode superseded behaviour to force production workarounds.
Notation is judged on screen. Existing negative fixtures deliberately print
diagnostics; their declared failure counters and wrapper exit status determine
the result.

The native smoke executes embedded startup and typed IPC. The existing production
workflow executes real application scenes and repertoire journeys. Full mode
also builds and boots a relocated package. These are different checks; parsing
a production fixture does not mean its application journey ran. Serialize Godot
imports/checks against a shared project and retain source revision plus logs.

## Standalone Linux package

[package-inprocess.sh](../scripts/package-inprocess.sh) assembles Godot, the
compiled GDExtension, CPython and runtime wheels, private Node, pinned fingering
models and count-in assets. Required builder inputs are:

```bash
export PIANO_BUNDLED_PYTHON_HOME=/absolute/path/to/private-python-prefix
export PIANO_GODOT_BINARY=/absolute/path/to/godot
export PIANO_BUNDLED_NODE=/absolute/path/to/node
bash scripts/package-inprocess.sh
```

The Python prefix must include shared libpython and the runtime dependencies;
the native extension must use its matching ABI. Output is
`dist/piano-teacher-linux-x86_64/` with a `PianoTeacher` launcher and a tar archive.
The packager verifies imports through the assembled prefix and prepares actual
Godot imported count-in bytes. It excludes developer repertoire, test smoke
scenes and MCP editor tooling. Existing source audits run against both the
checkout and assembled runtime through
[verify-phase5-architecture.py](../scripts/verify-phase5-architecture.py).

End users do not need a compiler, pip, system Python or a separate Godot install
for that assembled package. The host still supplies compatible OS/ELF runtime,
MIDI/ALSA and graphics/display drivers. A successful assembly/import audit is
not proof of second-machine portability or a published release.

Run the existing full [production verifier](../scripts/verify-embedded-production-local.sh)
to exercise the strict relocated build/boot path. Preserve the distinction
between clean HOME/environment on the developer host and a clean target machine.
Do not claim reproducible archives, offline package inference or another Linux
distribution unless the exact artifact actually passed those checks.

## Verification and acceptance

Results apply to the recorded source revision and environment. Historical logs
and superseded plans live in Git; they do not establish current acceptance.
[ROADMAP](../ROADMAP.md) records current software outcomes and unresolved gates.

| Evidence | What it establishes | What remains separate |
| --- | --- | --- |
| Core tests and headless Godot scenarios | Their existing source, grading, persistence and UI contracts | Physical MIDI/audio, display appearance and arbitrary repertoire coverage |
| Native smoke | Actual GDExtension registration, embedded import and typed operation | Real-device timing and a complete practice session |
| Production/repertoire journey | The exercised built application routes and named sources | Unexercised sources, real performance and audible output with Dummy audio |
| Strict relocated package boot | The tested archive runs in the stated isolated same-host environment | Clean-machine desktop, different OS/driver closure and instrument acceptance |
| Owner at the piano | The observed keyboard/audio/rendering behaviour on the named setup | General teaching efficacy or hardware combinations not observed |

The owner checks a physical Kawai CA49 over USB and Bluetooth separately:

- Open a new MIDI file; verify the first window, Listen → Free → Tempo,
  right/left/both progression and complete sustained notes.
- Hear Listen, clicks/spoken count-in and actual speaker output. Check MIDI
  calibration and both press/release timing without claiming acoustic duration
  from key release alone.
- Check generous short-note spacing, green/red note feedback, wrong-key ghosts,
  Listen lighting, dimmed other-hand/context ink and wrong-note-only keyboard.
- Repeat, speed up/slow down, pause/resume and use physical shortcuts at low
  tempos, pickups, long rests, sustained sparse music and changing meter. Score
  movement and handoffs must stay forward, without overlapping or missing ink.
- Exercise reconnection/interruption, save/reopen at Free, simplified aid return
  to original notes and the final examination. Verify compact and desktop sizes.
- Run a real long session and a clean-machine desktop package. Record actual
  latency/resource conditions and every unobserved item explicitly.

A headless process cannot certify these observations. Research claims require
the separate human comparison in [reference](reference.md#research-and-evaluation).

## Diagnostics and editor tooling

Use the existing typed `performance.diagnostics` reports for bounded tick,
MIDI-callback and snapshot latency. Those measurements exclude physical driver,
speaker and display latency. Historical benchmark numbers are not guarantees
for a later build.

The optional [Godot MCP toolkit](../godot/addons/godot_mcp_toolkit/) is editor
tooling and is stripped from the standalone package. Its project path and working
directory must be `<checkout>/godot`; a graphical editor is needed to launch
playtests. Keep its WebSocket service disabled during network-free runtime checks.
Godot cache [`.godot/`](../godot/) data are ignored. Existing tracked `.gd.uid`
files remain versioned; newly generated IDs are ignored unless a stable
cross-checkout resource reference requires them. Do not delete user data or
shut down an existing editor to clear a diagnostic without authorization.
