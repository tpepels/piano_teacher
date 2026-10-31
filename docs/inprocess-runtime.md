# Embedded runtime

Piano Teacher is a **single Godot process** using a CPython interpreter
inside a C++ Godot 4.7 GDExtension. There is no alternate application
runtime, HTTP service, UDP listener or port binding.

## Ownership

- Godot owns score painting, user actions, animation, metronome and Listen
  audio. Static Verovio beam texture slices, slur polygons, tie contours,
  chord order, note positions and expression/endings spans are prepared when
  the score/viewport changes. Frames only translate these prepared structures
  and draw visible marks. Source notation and automatic silence now live
  in retained `CanvasItem` command buffers. Repeated copies reuse pooled
  source/rest nodes positioned by transforms; recovery creates precompiled
  source/rest variants when its authored context changes. Fingering and
  transport effects remain on separate overlays. Score publication waits
  until all ordinary retained source/rest buffers have compiled. Current
  segments cover whole passages, so unusually long scores may still need
  finer spatial tiling and GPU/frame-time benchmarking.
  `source_pass_painter.gd` owns one-time authored composition;
  `retained_note_projection.gd` owns visible notehead indexing, and
  `view.gd` owns scene lifecycle and camera transforms. The source-copy pool
  is sized from the viewport and semantic stride rather than a fixed clone
  count. Fingering labels are sorted during layout and binary-searched by
  their visible source-space interval each frame.
- `PianoNative` owns one worker thread and an in-memory command/response
  queue, with completion callbacks delivered on Godot's main thread.
  Its condition-variable wait has a bounded monotonic wakeup: the same worker
  calls `EngineCommands.tick()` to advance automatic attempts, recovery and
  other musical deadlines even when the UI does not request `/state`.
  Writes re-evaluate the wakeup cadence immediately. No second clock or
  Python scheduler thread is created.
- `piano_teacher.inprocess.EngineCommands` dispatches typed engine
  operations. `PracticeEngine` remains authoritative for musical time,
  grading, adaptive lessons, library state and MIDI input.
- Provisional physical MIDI note-on feedback is appended to a bounded
  `LiveEventRing` during the hardware callback, then read by Godot on
  the next frame without blocking on state serialization.
- The Python GIL is held only while invoking Python; the C++ queue
  uses a condition variable rather than an extra polling thread.

Godot uses one `inprocess_request.gd` adapter for commands and one
`score_asset_queue.gd` adapter for score layout and model requests.
No source code should instantiate `HTTPRequest` or `PacketPeerUDP`.

## Building

Arch developer machine:

```bash
sudo pacman -S --needed godot python base-devel scons git
python -m venv .venv
.venv/bin/python -m pip install -e '.[godot,test]'
bash scripts/build-inprocess.sh
./run.sh
```

The build generates `godot/native/piano_bridge.gdextension` and a
versioned `libpiano_bridge.*.so`. The GDExtension is linked to the
same CPython ABI as the developer's interpreter.

The build imports the Godot resource index and runs
`scripts/verify-native-bridge.sh`: the class must register, embedded
Python must load, and a command for `/library` must return a JSON
catalogue. A broken extension must prevent the app from opening.

Godot loads native extensions with local symbol scope. The extension
promotes its linked `libpython` to `RTLD_GLOBAL` before importing
CPython extension modules such as `math`, `python-rtmidi` and
`verovio`.

## Release packaging

`scripts/package-inprocess.sh` bundles Godot, the compiled extension,
CPython and all runtime wheels, and a private Node runtime for offline
fingering inference. The resulting Linux application starts one
process and asks the host only for the OS, MIDI/ALSA drivers, GPU/display
drivers, and standard runtime libraries.

The package build must still be checked on a clean target machine.
Developer compilation and Python contract checks alone do not certify
a portable release or physical Bluetooth latency.

## Tests and performance

Run `bash scripts/ci-smoke.sh` and
`bash scripts/check-godot-syntax.sh`; both are short. The targeted
native smoke runs on the developer machine at build/start and in the
bounded GitHub native workflow.

Use the in-process `/diagnostics/performance` command for MIDI
callback and state-projection processing times. The bounded local checks
`tests/test_inprocess_scheduler.py` and
`tests/test_prepared_sprite_plans.py` cover poll-independent loop progression
and immutable authored-ink geometry.
`tests/test_retained_score_pipeline.py` checks the retained frame contract
and exercises transform-only movement under headless Godot. Actual visual
parity, full-score GPU performance, and physical MIDI synchronization still
require a local runtime run. Compiling Python
bytecode or adding multiprocessing is not useful without measured
CPU-bound bottlenecks. The primary optimization is the eliminated
network/service boundary and the pre-indexed active passage.
