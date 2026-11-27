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
[test.sh](../scripts/test.sh). Since 2026-11-22, GitHub Tests runs only
when manually dispatched from Actions → Tests with `core` or `full` (`full`
also runs native-production). Pushes and pull requests do not start CI.
For same-HEAD local acceptance, run the core suite and strict native verifier
after development is complete; the last green run on an older SHA does not
verify subsequent source edits. The 2026-11-22 native binder, Python
full-bar Resume, terminal admission/Stop, lesson controls and embedded
fake-MIDI transition changes, plus warm-up unlock and required-snapshot
validation, were committed without local CI. Run the
same-HEAD core and full embedded verification together after source work
is finished; their results must be recorded in ROADMAP before closing V0–V6. CI requests informational Python coverage:

~~~bash
bash scripts/test.sh --coverage
bash scripts/test.sh --python-only
bash scripts/test.sh --python-only tests/test_note_feedback.py
bash scripts/verify-native-bridge.sh
bash scripts/verify-embedded-production-local.sh
~~~

The common command runs Python, production Godot parsing and five Godot
player-behavior checks. Arguments after runner options go to pytest.
Coverage produces ignored XML/JSON reports for GitHub. The coverage run
combines traces from the embedded engine tests and the real score subprocess.
Line and branch rates are reported separately and are informational. Godot
behavior and physical acceptance have their own checks.

The owner approved rebuilding the suite on 2026-11-20 around player behaviour.
The previous 35 Python modules/336 collected cases and 26 native scenario
invocations were initially replaced by ten Python modules/85 cases and four
native groups. The requested coverage extension brings Python to twelve modules
and 108 cases; the four native behaviour groups remain.
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
| [Score import](../tests/test_score_import.py) | Hands, attacks, velocity, overlapping unisons, native chords/tied tails/tuplets, meter, stale preloads and rejected non-piano input. |
| [Library/settings](../tests/test_library_and_settings.py) | Scoped imports, persistence/migration, malformed settings, health-check recovery and failed saves without cancelling practice. |
| [MIDI devices](../tests/test_midi_devices.py) | Unplug/reconnect, explicit disconnect, failed-open recovery, fresh attacks, calibration and configured physical-key shortcuts. |
| [Listen audio](../tests/test_listen_audio.py) | Real PCM timing/pitch/chords/tails, audio/score readiness, cancelled stale workers, failure recovery, fallback and count-in assets. |
| [Fingering](../tests/test_fingering.py) | Real installed model inference, impossible/unavailable results, manual corrections and corrupt derived-cache recovery. |
| [Alternate courses](../tests/test_alternate_courses.py) | Explicit source-progression/Coda selection, source-safe aids, manual controls, distinct generic release policy and every built-in warm-up. |
| [Learning history](../tests/test_learning_history.py) | Actual outcomes/signed timing, unknown detail, stable paging, redacted atomic export, scoped deletion, preserved reset history and captured mastery criteria. |
| [Desktop playback](../tests/test_desktop_playback.py) | Takes placed on the musical timeline: repeat after one eased count-in bar, display failure, Retry, paused count-in, ungraded Listen. |
| [MIDI journeys](../tests/test_midi_journeys.py) | Wrong, missing, extra and late notes; Free return at the floor; slower after two failures; mastery at target; a take Godot could not draw placed again; seeded long journeys with Pause/Retry/Stop never fail. |
| [Failure grading](../tests/test_failure_grading.py) | Five window kinds (right, left, both hands, two bars, MusicXML) and twenty kinds of mistake (missing chord notes, nothing played, random keys, wrong pitches, extra/doubled keys, early/late just outside and far outside the tolerance, a rushed take, count-in presses) graded note by note, counted in the history and followed by the same tempo; tolerance edges; hold grading on/off; two failures returning to Free or slowing down. |

[Test inputs](../tests/session_inputs.py) supply small actual MIDI files, one
injected input clock and external ports; the production engine decides grading
and progression. Tests inspect public commands, snapshots, feedback and saved
reopening. External I/O failures are controlled without duplicating application
rules. Engines, workers and ports are released after each session.

Native groups in [tests/godot/](../tests/godot/) exercise actual controls,
immutable score admission, a stationary score during Pause, and forward
movement after Resume/Retry,
source/take-bound note feedback including future ties, and score readiness/
failure/retry. [Syntax checking](../scripts/check-godot-syntax.sh) and
[executed behaviour](../scripts/test-godot-behavior.sh) have separate log markers.
Expected negative asset fixtures print diagnostics; declared failure counters
and wrapper exit status still determine success.

Only genuinely absent optional audio/model runtimes skip, with a stated
reason; installed-but-broken runtimes fail. Required CI dependencies do not
become optional. The expanded run has 107 passed/one absent-system-SF2
skip, 69.5% Python line coverage and 49.4% branch coverage. These percentages
are an inventory of execution, not a completeness claim.

Future regression additions follow the [repository policy](../AGENTS.md):
owner-confirmed player behaviour, without abstract infrastructure, parity or
pixel tests. The requested suite rebuild was an explicit exception to the
prior restriction on adding tests. Notation appearance is judged on screen.

The full [production verifier](../scripts/verify-embedded-production-local.sh)
can also check the original Pathétique II failure against a local MIDI that is
not in the versioned corpus. Pass `PIANO_PATHETIQUE_II_MIDI=/absolute/path/to/source.mid`
when running it. The script imports that source into an isolated temporary
test HOME, runs the actual embedded Godot admission journey, and deletes the
copy on completion. Without this setting it prints a **PENDING** marker rather
than implying that Pathétique has been tested; this source-specific gate
does not replace physical piano/audio acceptance.

The synthetic-MIDI journey (4/4 and 2/4) plays the real scene: a wrong key
in Free, Pause/Resume in Free and Tempo, a failed take, a second failure at
50% returning to Free, Free again, a clean take that gets faster, repeats
scrolling in from the right, and a deliberate 14 s frame stall after Resume
that the take must survive (placed again, no failure).
The verifier runs embedded startup, a real default Practice Flow fixture, and Moonlight,
Peace Piece and Chopin journeys with explicitly selected Coda/Fukuda.
Full mode also builds and boots the relocated standalone package. These checks
exercise built application routes, separately from the fast suite. Serialize
Godot imports/checks against a shared project and retain source revision and
logs. Parsing a production fixture does not establish that its journey ran.

The expanded suite and all seven full production/package cases pass on source
`70f7b459`. [ROADMAP](../ROADMAP.md#coverage-extension-2026-11-20) records the
logs, reporting correction, optional skip and outstanding physical acceptance.

### Coverage extension 2026-11-20

The extension uses the uncovered-line report to choose useful scenarios,
keeping the same source scope and no percentage gate. Existing musical/device
scenarios are extended, with focused history and desktop-playback groups;
architecture and object-shape tests remain absent.

The 23 added scenarios cover real-take statistics, bounded reads, explicit
exports and scoped reset/deletion; desktop admission, stale/failing presentation
and continuation through public commands; configured piano keys, library-health
recovery, all built-in warm-ups and richer imported notation. The count-in and
source/take checks use musical facts rather than visual layout or source parity.

The mastery scenarios exposed an outdated three-pass count in snapshots,
statistics and transition messages. Those projections now consume the active
course's actual rule and record it with new attempts. Practice Flow stays at
two target successes; warm-ups and other courses retain their configured rule.
Older history retains its recorded criteria. The owner explicitly requested
these additional CI tests; physical acceptance remains separate.

### Final architecture software acceptance — 2026-11-21

The exact code revision `daf466e6` passed GitHub
[run 44907200749](https://github.com/tpepels/piano_teacher/actions/runs/44907200749),
including core and opt-in native-production jobs. Python reports **103
passed, four optional skips**, coverage 73.6% lines / 53.3% branches;
Godot parsing and four executed behaviour groups report no failures.
Embedded CPython 3.14 registration, native source preparation, repertoire
journeys and strict relocated standalone package build/boot also passed.
Two checkout/package-content inspections reported
`PACKAGE_CONTENTS_OK` and the verifier ended with
`PASS LOCAL EMBEDDED PRODUCTION CONTROL`. No tests were added during
this architectural extraction. A separate physical instrument, visual/audio
judgment and independent clean machine are still required.

### Architecture refactor core acceptance — 2026-11-21

At source `55e31dd2`, GitHub [core run 44906137747](https://github.com/tpepels/piano_teacher/actions/runs/44906137747)
passed **103 Python tests (4 skipped)**, with 73.5% line/53.3%
branch coverage. Godot syntax and all four executed existing behaviour
groups passed, each with zero failures. These are source and native
behaviour checks only. The opt-in full embedded Python 3.14, real Godot
repertoire journeys, strict standalone bundle and relocated boot remain
a **separate gate** for this revision. No new tests or simulated
application engine were introduced.

### Pause/Resume and selected-window software acceptance — 2026-11-21

The post-S7 Pause repair freezes the authored score in an acknowledged
Pause, preserves Free's stationary target and restricts visible notation to
the current one-to-four-measure practice window with its ending barline and
full sounding tails. The native presentation still owns exactly one visual
timeline and source/admission ledger. The backend remains paused while an
explicit Resume intent is reserved; the visual hold must be released for
that pending intent so graphical deadline inversion can complete.

The first native run on `b37e7693` failed because the two existing
integration scripts still required movement during Pause. The subsequent
run on `1948651a` exposed an actual `admitting` stall during Resume.
These were corrected without adding new tests. Final source `81ae006f`
passed [full core and native-production run
44925026112](https://github.com/tpepels/piano_teacher/actions/runs/44925026112):
**103 Python passed, four skipped**, all four native behavior groups and
Godot syntax passed, embedded Python/real-score preparation succeeded,
production Pause/Resume and Moonlight/Peace Piece/Chopin journeys passed,
the relocated standalone package contents and boot passed, and the
native-production log contained **zero `SCRIPT ERROR` lines**.

The next acceptance is physical: verify stationary Free targets, immediate
Pause/Resume, no new source admission while paused, exact one-to-four-bar
visible windows, preserved long ties and barlines, speakers/count-in and
actual piano input. Headless software acceptance does not certify those.

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

- Test **Grade how long I hold notes** both off (default) and on. With it off,
  correct note attacks must remain green/clean despite early, late or missing
  releases, while measured releases remain available in local history. With it
  on, release errors must affect grading with fixed and variable tempos. Check
  persistence across restart and cancellation when switching during a take.

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

### Investigating scrolling frame pacing

Run `./run.sh --frame-diagnostics 2>&1 | tee frame-results.log` and play a dense passage for at least 30 seconds. The `PHASE8D_FRAME_INTERVALS` records report process FPS, mean, p95 and worst delivered frame intervals; these are not physical display latency measurements. Compare to the display's refresh interval. V-sync stays enabled and practice uses native-refresh pacing. The visual timeline caches the exact-time projection per publication and indexes take starts; fully visible retained notation strips update translation without repeatedly resizing the clip.

Frame diagnostics now include actual monotonic intervals (`wall_fps`, `wall_p95_ms`, `wall_worst_ms`) and the projected score displacement and speed ranges in pixels (`world_step_min_px`, `world_step_max_px`, `world_speed_min_px_s`, `world_speed_max_px_s`). Stationary frames are counted; phase, transport, revision and density changes are excluded from these motion ranges. Holds and tempo changes can legitimately vary speed. These values are CPU-side projection measurements, not GPU presentation timestamps. Use constant-tempo playing passages for comparison. The shared visual clock now receives fractional milliseconds from Godot's monotonic microsecond clock, without changing backend grading time, and adopts the new timeline before evaluating the source beat. Pixel snapping is explicitly disabled.

The 2026-11-26 follow-up log showed constant projected velocity during all 47 timed-playing reporting windows, with actual process cadence near 60 Hz. Navigation had been restoring a software 60 FPS cap on every accepted snapshot. NavigationSession now exclusively controls runtime pacing: no software cap or low-power sleep during practice/active calibration; the idle drawer retains 30 FPS. Diagnostics additionally report `engine_max_fps`, `display_refresh_hz`, `display_backend`, `vsync_mode` and `low_processor_usage`. Refresh is the display server's reported rate, not a measurement of physical scanout. A separate ~446 ms source-loading stall remains to be profiled.

The moving-meter grid now computes the actual visible repetition indices before/after the authored grid, including after long idle periods. Ambient barline coverage projects only the visible prefix of the ordered printed-strip ledger once per frame. Count-in no longer allocates a map of all take openings just to mark one owner sounded. With `--frame-diagnostics` (or `PIANO_TEACHER_TIMING_DIAGNOSTICS=1`), `SCORE_BUNDLE_MAIN_THREAD` separates JSON decode, identity validation, native atlas loading, semantic model/retained setup and layout publication. `SCORE_RETAINED_READY` reports elapsed retained compilation wait and synchronous ready callbacks including glyph warmup. These CPU-side measurements identify the stage responsible for a loading stall; they are not physical presentation timestamps.

The [score subprocess](asset-worker.md) compiles notation and extracts Verovio assets. Godot's detached WorkerThreadPool job decodes and validates the bundle, rasterizes SVG/PNG assets into CPU images, and fits score geometry to the viewport. Main joins the completed job, checks its generation and viewport, uploads textures in approximately 2 ms slices and installs retained notation. Shutdown may join a still-running job. `SCORE_WORKER_GENERATION` and `SCORE_IPC` report subprocess generation and round-trip times. `SCORE_BUNDLE_WORKER`, `SCORE_BUNDLE_MAIN_THREAD` and `SCORE_RETAINED_READY` track detached preparation, upload, installation and retained draw readiness. Individual uploads and draw commands may exceed the slice budget.

Notehead interior masks are now derived from the original CPU Images on the score worker, cached per font and uploaded with the atlas. The retained display resampler reads CPU image metadata rather than forcing a GPU readback for the authentic source textures. GPU warmup and size-dependent resampling still run on main as needed; expired display-texture cache entries are pruned at readiness.

Core CI runs on every push to main again, with Python and Godot verification reported separately even if the Python tests fail; real CPU ONNX fingering has a dedicated job. Full embedded/package verification remains available through manual dispatch. The Godot readiness scenario now generates an authentic Verovio score bundle and drives the actual worker, upload and retained draw lifecycle, superseding a pending job and retrying the selected source.

The automatic workflow runs Python, Godot, and fingering checks in independent jobs, so a failing or long Python suite cannot hide notation failures. A separate least-privilege reporter records all three exact-commit outcomes through GitHub commit statuses, including links to the Actions run. All Godot player scenarios run even when an earlier scenario fails.
