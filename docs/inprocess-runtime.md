# In-process desktop transport (work in progress)

The supported design is **one Godot process with embedded CPython**. A
Godot 4.7 GDExtension implements one bounded-in-memory request/response
queue on a worker thread. The original Python `PracticeEngine` remains
authoritative for MIDI capture, timing and grading; its code is not
duplicated in Godot or C++. The extension calls
`piano_teacher.inprocess.EngineCommands`, which dispatches the same
semantic commands that the old HTTP adapter used. It returns JSON bytes
for ordinary results and raw bytes for Listen WAV files. No listener,
socket, port, interprocess pipe or network client is used.

A separate in-memory ring receives provisional MIDI note-on events
directly from the engine callback; Godot reads them on the main frame
without requesting a full /state snapshot. This implementation retains
the earlier stable source clock and native score rendering.

## Build-time versus runtime requirements

The **release builder** needs a C++ compiler, SCons, godot-cpp 10.0.0,
CPython development headers and a Godot 4.7 executable. It performs
the native compilation, installation of Python wheels and bundling. The
end user should receive one directory/archive containing:

- Godot executable, project resources and the compiled GDExtension
- a matched private CPython runtime, including its standard library
- installed `piano_teacher` runtime dependencies (MIDI, Verovio, etc.)
- a matching private Node runtime for the offline fingering inference

The resulting package requires no installed Python, Node, pip, git,
SCons, C++ compiler or running HTTP service. A host still necessarily
provides an OS kernel, GPU/display drivers, Bluetooth/ALSA MIDI drivers
and its standard low-level ABI. There is no way to use a physical MIDI
keyboard without some host device interface.

## Status and validation

This change **adds the actual dispatcher, GDExtension source, queue,
Godot request adapter and package build scripts**. The existing
`./run.sh` launcher deliberately remains unchanged until a compiled
GDExtension passes a real Godot startup and keyboard test. The native
path is **experimental**, invoked by `./run-inprocess.sh` after
building the extension. It is *not yet a precompiled standalone release*.

Developer workflow on a compatible Linux build machine:

```bash
bash scripts/build-inprocess.sh
./run-inprocess.sh
```

The build script compiles the extension and generates the manifest only
after a successful native compile. The existing Godot project will not
attempt to load an absent binary.

Release assembly requires a self-contained Python distribution with
all project runtime wheels installed, a matching Godot binary and Node
binary:

```bash
PIANO_BUNDLED_PYTHON_HOME=/path/to/python-standalone \
PIANO_GODOT_BINARY=/path/to/godot-4.7 \
PIANO_BUNDLED_NODE=/path/to/node \
bash scripts/package-inprocess.sh
```

This produces a tarball whose `PianoTeacher` launcher sets private
runtime paths and starts only Godot. The build must validate the bundled
CPython ABI matches the linked GDExtension; this has not been run on the
target keyboard/GPU.

Python contract tests verify the dispatcher and protect against
accidentally reintroducing sockets in the native queue. They **cannot**
prove C++ compilation, a successful Godot GDExtension load, end-to-end
MIDI timing or a truly portable release. Those remain gating items
before switching the default launcher or deleting the legacy HTTP
path.

## Compiling Python

The Python code already executes as compiled bytecode in CPython.
Bundling CPython or producing .pyc files does **not** make MIDI
callbacks substantially faster. The observed delays were mostly
transport round trips, state serialization and rendering.
Compiling selectively with mypyc/Cython or Nuitka can be considered
*after* the in-process measurements identify a CPU-bound Python
function. No unmeasured AOT toolchain is added to runtime startup or
required of users.
