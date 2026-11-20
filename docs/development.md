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

### Test-suite replacement design — approved 2026-11-20

Status: approved; implementation in progress. The owner prioritizes CI tests
for player behaviour and explicitly rejects architecture/implementation checks
that constrain refactoring. Coverage reports are informational, without a
percentage gate or a required test for every internal branch.
The owner requested a ground-up rebuild because tests may encode irrelevant or
superseded behaviour. This request authorizes replacement tests; physical
acceptance remains separate. This design stays in the existing guide to keep
the documentation tree at four Markdown files.

The unchanged baseline at `16a064e2` collects 336 Python cases: 335 pass and one
optional system SF2/libfluidsynth case skips. The fast Godot runner parses
production scripts and executes 26 component/UI scenario invocations. It does
not execute the full embedded workflow. The audit found these concrete gaps:

- Some cases assert shaders, node names, container hierarchy, exact captions,
  private aliases, reducer enumeration or generated-contract parity.
- Learner-state fixtures force the older split-unit policy. Other tests use
  source-progression without naming it, making that supported alternate route
  look like the default practice course.
- No existing native case ingests graded events to check wrong/future-note
  colouring, source/take isolation, timed tied continuations or ungraded Listen.
- The full repertoire verifier explicitly selects Coda/Fukuda. Its successful
  journeys do not establish complete default Practice Flow coverage.

**Approach.** Rebuild from the current learner contract, replacing each area
with its smaller behavioural counterpart before removing old scaffolding.
This implements the requested rebuild while preserving useful failure/recovery
coverage throughout. Merely renaming or pruning cases leaves the default-flow
gaps. Deleting everything before replacement removes existing protection for
progress migration, source fidelity and MIDI recovery. The chosen migration
order preserves useful coverage during the approved rebuild.

Every retained case must identify a learner-visible contract or a failure that
would lose progress, play/grade the wrong source, prevent practice or fabricate
credit. Passing counts and coverage percentages are not acceptance criteria.

| Behaviour area | Replacement evidence |
| --- | --- |
| Default course | Open actual MIDI through the engine; start at the first measure's Listen. Complete the entire selected Free window before Tempo. Verify Right → Left → Together, empty-hand skipping, independent backward-growing windows capped at four bars and the separate whole-piece final. |
| Tempo and aids | Verify original-target 50% entry, 10% steps, same-tempo first retry, two-failure slowdown/floor return, broken clean streak and two target successes. Persist the exact window/hand's second Free return, announce a genuine aid, return to original Free without mastery, and retain original Free when no aid exists. |
| Resume and progress | Reopen the saved window/hand and final test at complete-window Free, then 50%. Preserve supported persistent migrations, isolate pieces/hands/windows, and prevent interrupted or twice-delivered completion from awarding credit. |
| Musical time | Verify an authored count-in bar ending at the first playable attack, local/mixed meter, preserved release tails and the exact one-bar automatic repeat. Pause/Resume freezes musical elapsed time while keeping the world axis forward. Listen again adds no mastery. First entry may require safe physical clearance; automatic repeats retain their stricter deadline. |
| Performance feedback | Drive real MIDI ingress/Recorder and compare live and settled source assignments. Cover repeated pitches, chords, wrong/missed/extra notes, accepted early/late boundaries, independent release evidence and the default two-colour policy. A later same-pitch note or another take remains neutral. |
| Authentic notation | Real MIDI import retains attacks, hand identity, meter, tuplets and complete releases. Active performance IDs remain distinct from dim neighbours/other-hand/carry-in ink. Native source heads and timed ties receive only their own take's feedback; wrong-key ghosts retain the played pitch. No pixel or aesthetic assertions. |
| Device and user data | Simulate only external MIDI/device failures and filesystem failure boundaries. Verify unplug/reconnect cancellation, fresh physical attacks, explicit disconnect, calibration application, settings/library recovery and scoped saved-data operations. These establish software reactions, not hardware acceptance. |
| Listen and fingering | Verify actual source-timed PCM preparation, current audio/score readiness, cancellation/failure recovery, offline fallback and sustained endings. Retain real-model smoke, manual correction persistence and honest unavailable/impossible fingering results. Avoid frozen waveform or model-choice snapshots. |
| Supported alternatives | Explicitly select source-progression/Coda/Fukuda for compact feature coverage. Their manual tempo, short guided-unit and detailed generic release grading rules must not become default Practice Flow expectations. |

**Test boundaries.** Keep pytest and native Godot; add no framework or service.
Prefer public engine/typed commands and snapshots, published source/deadline
facts, feedback events and saved reopen. Small direct musical algorithms may
be tested where the output itself is the player contract. Assertions must not
require private owner fields, object identity, implementation names, exact
dataclass/JSON dumps or source-code text searches.

Use a controllable injected clock and real small MIDI fixtures in temporary
directories. These supply input; they must not implement a second grader,
progression machine, queue or clock policy. Fake only external ports, controlled
I/O failures and absent optional runtimes. Release engines/threads/ports in
fixture cleanup and never touch actual learner progress or attached hardware.
Preserve installed-but-broken optional-runtime failures; only genuinely absent
optional dependencies may skip, with an explicit reason.

**Native checks.** Replace widget/layout implementation cases with four small
groups: normal controls/Free hints, immutable score admission and Pause/Resume/
Retry, source/take-bound feedback including future ties, and score readiness/
failure/recovery. Exercise the production owners and authentic notation facts.
Keep native bridge/standalone validation and real repertoire journeys; add
explicit default-course execution rather than relabelling alternate journeys.

**Runner and integration.** Keep `bash scripts/test.sh` as the common local/CI
entry point and preserve `--python-only` and pytest argument forwarding. Separate
parser checks from executed Godot behaviour so logs state what actually ran.
Keep full embedded/relocated packaging as the existing explicit production
gate. Update CI commands only where needed for the reorganized suite, without
lowering failures, weakening assertions or making required dependencies skip.

Replace the old test files and helpers rather than leave duplicate suites or
an archived legacy suite in the checkout; Git retains history. Group the new
tests by the behaviour areas above, with shared fixtures limited to test input
and cleanup. Production features and policies stay unchanged. If replacement
tests uncover an actual production defect or a contract ambiguity, diagnose
and report it separately instead of adjusting an assertion to match a bug.

**Completion evidence.** Record a before/after map of retained, replaced and
removed coverage here. Run the complete replacement Python/native suite and
the full embedded workflow, including all named repertoire and strict relocated
package build/boot. Record source commit, results and optional skips in ROADMAP.
Keep physical CA49 USB/Bluetooth, sound, display, latency and clean-machine
acceptance explicitly unverified. Work directly on main in coherent commits;
do not push, create branches/worktrees or expand the four-file docs tree.

#### CI test rebuild implementation plan

**Goal:** A compact CI suite that catches broken lessons, feedback and saved
progress while allowing the architecture and visual implementation to change.
**Architecture:** Real engine inputs and outputs for the course; focused musical
and external-I/O contracts; native checks for visible feedback and score lifetime.
**Tech stack:** pytest, Godot and optional informational Python coverage.
**Spec:** This design and [Practice flow](practice-flow.md).

Global constraints: main only; no push; four docs; no architecture/parity/pixel
tests; no simulated application rules; physical acceptance remains separate.
The latest owner instruction authorizes replacement tests for current contracts.

Review focus: future same-pitch notes, partial four-bar Free, reopened final,
second floor-return aid and interruption during a pending completion.

- [ ] Replace Python course/state/teaching scaffolding with default-course,
  resume/aid, timeline and feedback scenarios. Use actual MIDI imports and one
  injected input clock; inspect commands/snapshots/events and reopened progress.
  Assert the full-window and two-target-clean rules, first-attack count-in,
  exact repeat deadline, held tails and advisory releases.
- [ ] Consolidate import, device, library/settings, audio and fingering cases
  into focused feature files. Preserve real fault/recovery cases and explicit
  supported alternate routes; remove source-text, object-shape and parity checks.
- [ ] Replace native widget/layout/ownership cases with controls, immutable
  admission, feedback and readiness/failure cases. Assert outcomes rather than
  node names, shaders, exact captions or container dimensions.
- [ ] Separate syntax parsing from executed behaviour in the runners; keep
  `scripts/test.sh`, `--python-only` and pytest argument forwarding. Make default
  Practice Flow explicit in production verification while retaining repertoire
  and relocated package acceptance. Add informational coverage without a gate.
- [ ] Run each changed group, verify meaningful negative/boundary cases, review
  the integrated diff, then run full CI and embedded/package checks. Record the
  coverage map and measured results, remove superseded helpers, and commit each
  coherent step. Production fixes require actual defect evidence and are
  recorded separately; assertions are not relaxed to make a bug pass.

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
