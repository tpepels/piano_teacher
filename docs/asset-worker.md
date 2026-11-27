# Score generation and publication

The embedded practice engine owns MIDI, grading, progression and the musical
timeline. It derives the selected practice timeline from authored bar boundaries,
meter and sounding releases. Notation consumes that same timing. Grading and Free
publish canonical source-note IDs; Godot resolves those IDs against the installed
score revision and its tied heads.

The native asset mailbox supervises one persistent Linux CPython subprocess.
The child owns notation compilation, Verovio, asset extraction and the selected
artifact cache. It receives a value snapshot with the original source notes,
selected phrase, timing and fingering assignments. It has no practice engine,
device, clock authority or Godot objects. The child writes its own
`score-preprocessed` cache with atomic replacements. Import and learner caches
stay with the application.

## Lifecycle

- **Idle.** The supervisor starts the child on demand with `posix_spawn`. The
  developer and package launchers select their exact Python executable. The
  child uses the application and runtime module paths and disables site startup
  hooks. It exits if its parent dies. The asset lane polls for idle exits and
  reaps the child. A later request starts a replacement.
- **Queued.** The mailbox bounds pending, active and completed work to eight
  entries and refuses excess submissions immediately. It takes the newest
  pending entry first. Godot cancels the previous request as it navigates or
  retries. Stop invalidates the current generation and allows a fresh request
  for the idle score after acknowledgement.
- **Running.** The 85-second monotonic deadline includes queueing, source
  capture, transfer and publication. The asset lane polls cancellation between
  socket operations at most 25 ms apart while waiting for bytes. Cancellation
  discards pending or completed replies and retires the active child when it
  holds obsolete work. Closing the channel, SIGTERM, a 50 ms grace interval
  and SIGKILL cover both idle and uninterruptible Verovio work. The supervisor
  waits for the child to exit before installing a replacement.
- **Recovery.** EOF, I/O and framing faults, and wrong response identities
  retire the worker. The supervisor replays the same logical request once
  on a fresh channel within its original deadline. A hang expires the
  request and the next Retry starts a new child. A valid preparation error
  reaches the score error panel. If detached Godot validation rejects a
  result, Godot advances the generation and requests one replay. The
  supervisor retires the worker only if the rejected binding still matches
  its last bundle reply. A second invalid result reaches the error panel.
- **Shutdown.** The mailbox stops accepting requests and discards unpublished
  work. The native asset thread cancels or closes the channel and reaps
  the child before the bridge closes the practice engine.

## IPC and publication

An inherited Unix socket pair carries binary-framed UTF-8 JSON. Each frame
has a four-byte unsigned big-endian length. Every request and reply consists
of a metadata frame followed by a document frame. The protocol permits a
single exchange in flight. Limits are 8 KiB for metadata and errors, 32 MiB for
source documents and 64 MiB for successful replies.

Request metadata contains `version=1`, a monotonically increasing logical
`id`, `generation`, `operation`, `fingerprint`, `revision`, `stage_key`
and `hand`. Responses echo every field and add `status` and a SHA-256 of the
document frame. Status 0 carries the requested document, 1 a source or input
error, and 3 a preparation failure. Requests carry the complete values needed
for generation. The child can reuse an identical selected document. A replay
uses the same logical ID on a separate channel.

The asset lane encodes the source after it releases the session lock and
checks deadlines between chunks. It verifies framing, response identity, size
and checksum before the engine rechecks the current selection under its lock.
Large reply bytes transfer directly to detached Godot storage. Godot decodes
the bundle, validates its original-note IDs, model and layout, and prepares
CPU images and viewport geometry in the existing worker. The main thread
checks request generation and viewport again before uploading textures in
budgeted slices and installing retained ink. Playback acknowledgement follows
retained readiness for the current revision.

Length-prefixed JSON retains the existing Godot bundle format and avoids a
second document encoding or base64 wrapper around the full bundle. The
measured bundle payloads and cost of format changes are recorded below.

## Local comparison

Baseline `7459582a` and the subprocess build ran on the same Linux host,
CPython 3.14 and Godot 4.7.2. Each side used a new cache and the installed
LumiKey provider. The whole-piece Moonlight Sonata test submitted a cold
score bundle while feeding note-on and note-off through the real engine
callback and running engine ticks. The table uses the last 256 samples
for each callback and tick statistic. The frame test opened the first
practice window in Godot under Xvfb with software OpenGL and recorded
monotonic frame intervals through retained score readiness.

| Measurement | Threaded baseline | Subprocess |
| --- | ---: | ---: |
| Whole-piece selection | 1,002 ms | 180 ms |
| Whole-piece bundle available | 56.67 s | 15.58 s |
| MIDI callback p95 / max | 29.14 / 80.67 ms | 12.23 / 17.80 ms |
| Engine tick p95 / max | 56.62 / 70.08 ms | 22.23 / 35.36 ms |
| Engine process peak RSS | 149.5 MiB | 55.7 MiB |
| Sampled concurrent RSS, engine plus score worker | 146.6 MiB | 171.5 MiB |
| Opening-window frame p95 / max | 12.03 / 129.50 ms | 11.91 / 144.46 ms |
| Opening-window detached Godot preparation | 665.98 ms | 662.87 ms |
| Opening-window main-thread upload CPU / install and publish | 52.44 / 2.36 ms | 55.79 / 2.50 ms |

The cold subprocess exchange carried a 576 KB source document and a
3.66 MB bundle. The round trip took 15.54 s, of which 15.44 s was reported
inside the child for decoding, generation and JSON encoding. The
approximately 94 ms difference includes interpreter startup and transfer.
The opening-window exchange carried 380 KB in and 222 KB out, with
75 ms outside the child. Its cold bundle generation remained close to
three seconds on both revisions. The RSS sum counts shared pages in each
process. These single-run samples describe local software behavior under
the chosen workload.

A warm whole-piece request reused the running child's artifacts. It took
60 ms end to end, with 27 ms round trip and 22 ms in the child. Compressing
the 3.66 MB reply with zlib level 1 reduced it to 1.28 MB and added about
53 ms to compress and 10 ms to decompress. The measured warm transfer
cost was about 5 ms, so this protocol keeps the raw UTF-8 payload.

### Remaining latency sources

- **Source loading and fingering.** Opening Moonlight still occupied
  about 457 ms before source installation in the paired Godot runs. In
  the subprocess run the importer took about 23 ms, the curriculum and
  progress restore took about 120 ms, and the parallel LumiKey call took
  424 ms. The native command lane waits for source preparation, so an open
  can defer its next tick. The MIDI lock is released during import and
  inference. Snapshot publication uses source-note assignments and memoized
  fingering summaries. Context fingering travels with the notation bundle.
- **Listen.** Each render uses the existing audio thread and publishes
  through a source token. The basic synthesizer runs a Python PCM loop
  and shares the embedded interpreter. The sampled path spends synthesis
  time in FluidSynth. Superseded renders can still finish their audio
  cache work.
- **Godot.** Detached rasterization dominated the opening-window CPU job
  at about 601 ms in the subprocess run. Texture creation and retained
  installation stay on main. One upload can overrun the 2 ms budget
  because each texture creation is indivisible. The frame maximum rose
  in this sample even as callback and tick tail latency fell under the
  whole-piece workload.

The automated journeys use a synthetic MIDI device at the driver boundary.
Actual piano, audio and display acceptance remains pending.
