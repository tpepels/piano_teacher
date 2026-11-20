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

## CI coverage

The local and [GitHub CI](../.github/workflows/ci.yml) entry point is
[test.sh](../scripts/test.sh). CI requests informational Python coverage:

~~~bash
bash scripts/test.sh --coverage
bash scripts/test.sh --python-only
bash scripts/test.sh --python-only tests/test_note_feedback.py
bash scripts/verify-native-bridge.sh
bash scripts/verify-embedded-production-local.sh
~~~

The common command runs Python, production Godot parsing and four executed
Godot behaviour groups. Arguments after runner options go to pytest.
Coverage produces ignored XML/JSON reports, uploaded by GitHub; line and branch
percentages are reported separately, without a minimum percentage gate.
They measure Python execution, not Godot or physical acceptance.

The owner approved rebuilding the suite on 2026-11-20 around player behaviour.
The previous 35 Python modules/336 collected cases and 26 native scenario
invocations are replaced by ten Python modules/85 cases and four native groups.
Git retains the old suite. Architecture/source-text checks, contract parity,
private aliases, exhaustive reducer combinations, exact captions, container
hierarchy, shader choices and pixel/layout assertions were removed. Package
validation checks required runtime contents and import closure rather than
banning historical module names.

| Python coverage | Player-visible contracts |
| --- | --- |
| [Practice course](../tests/test_practice_course.py) | Actual MIDI opening, complete-window Free, backward growth up to four bars, hands, clean tempo ladder, failures and automatic final entry. |
| [Resume](../tests/test_practice_resume.py) | Reopened windows/final, interrupted input, progress migration, genuine persisted second-return aid and return to original Free without mastery. |
| [Timeline](../tests/test_practice_timeline.py) | Authored/first-attack count-in, exact repeat deadlines, full held endings, Pause/Resume, Listen again, published feedback and disconnect before completion. |
| [Note feedback](../tests/test_note_feedback.py) | Real MIDI ingress and Recorder, shared live/final grading, onset boundaries, repeated pitches, chords, wrong/extra/missing notes, releases and neutral future notes. |
| [Score import](../tests/test_score_import.py) | Hands, attacks, velocity, overlapping unisons, intact tails, meter, tuplets and rejected non-piano input. |
| [Library/settings](../tests/test_library_and_settings.py) | Scoped imports, persistence/migration, malformed settings and failed-save recovery without cancelling practice. |
| [MIDI devices](../tests/test_midi_devices.py) | Unplug/reconnect, explicit disconnect, failed-open recovery, fresh attacks and calibration timestamps. |
| [Listen audio](../tests/test_listen_audio.py) | Real PCM timing/pitch/chords/tails, audio/score readiness, cancelled stale workers, failure recovery, fallback and count-in assets. |
| [Fingering](../tests/test_fingering.py) | Real installed model inference, impossible/unavailable results, manual corrections and corrupt derived-cache recovery. |
| [Alternate courses](../tests/test_alternate_courses.py) | Explicit source-progression/Coda selection, source-safe aids, manual controls and their distinct generic release policy. |

[Test inputs](../tests/session_inputs.py) supply small actual MIDI files, one
injected input clock and external ports; the production engine decides grading
and progression. Tests inspect public commands, snapshots, feedback and saved
reopening. External I/O failures are controlled without duplicating application
rules. Engines, workers and ports are released after each session.

Native groups in [tests/godot/](../tests/godot/) exercise actual controls,
immutable score admission and forward movement through Pause/Resume/Retry,
source/take-bound note feedback including future ties, and score readiness/
failure/retry. [Syntax checking](../scripts/check-godot-syntax.sh) and
[executed behaviour](../scripts/test-godot-behavior.sh) have separate log markers.
Expected negative asset fixtures print diagnostics; declared failure counters
and wrapper exit status still determine success.

Only genuinely absent optional audio/model runtimes skip, with a stated
reason; installed-but-broken runtimes fail. Required CI dependencies do not
become optional. The latest measured run has 84 passed/one absent-system-SF2
skip, 58.9% Python line coverage and 38.3% branch coverage. These percentages
are an inventory of execution, not a completeness claim.

Future regression additions follow the [repository policy](../AGENTS.md):
owner-confirmed player behaviour, without abstract infrastructure, parity or
pixel tests. The requested suite rebuild was an explicit exception to the
prior restriction on adding tests. Notation appearance is judged on screen.

The full [production verifier](../scripts/verify-embedded-production-local.sh)
runs embedded startup, a real default Practice Flow fixture, and Moonlight,
Peace Piece and Chopin journeys with explicitly selected Coda/Fukuda.
Full mode also builds and boots the relocated standalone package. These checks
exercise built application routes, separately from the fast suite. Serialize
Godot imports/checks against a shared project and retain source revision and
logs. Parsing a production fixture does not establish that its journey ran.

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
scenes and MCP editor tooling. Package-content audits run against checkout and the
assembled runtime through
[verify-package-contents.py](../scripts/verify-package-contents.py). This checks
actual import closure and required runtime assets, not historical module names
or architecture shape.

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
