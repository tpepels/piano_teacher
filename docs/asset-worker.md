# Score generation and publication

The embedded practice engine owns MIDI, grading, progression and the musical
timeline. It derives the selected practice timeline from authored bar boundaries,
meter and sounding releases. Notation consumes that same timing. Grading and Free
publish canonical source-note IDs; Godot resolves those IDs against the installed
score revision and its tied heads.

The native asset lane supervises one persistent Linux CPython subprocess.
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
  and SIGKILL cover both idle and uninterruptible Verovio work. Signals use
  a Linux process descriptor (`pidfd`, Linux 5.3 or newer). The supervisor
  waits for the child to exit before installing a replacement and accepts an
  exit already reaped by the host.
- **Recovery.** EOF, I/O and framing faults, and wrong response identities
  retire the worker. The supervisor replays the same logical request once
  on a fresh channel within its original deadline. A hang expires the
  request and the next Retry starts a new child. A valid preparation error
  reaches the score error panel. If detached Godot validation rejects a
  result, Godot advances the generation and requests one replay. The
  supervisor retires the worker only if the rejected binding still matches
  its last bundle reply. A second invalid result reaches the error panel.
- **Shutdown.** The mailbox stops accepting requests and discards unpublished
  work. The bridge joins the timing driver and the native asset lane. The
  asset lane cancels or closes the channel and reaps the child before the
  bridge closes the practice engine.

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
checks deadlines between chunks. It retains only the last encoded source
for an exact retry. A same-revision fingering correction replaces that source
value and invalidates the reuse. The lane verifies framing, response identity, size
and checksum before the engine rechecks the current selection under its lock.
Large reply bytes transfer directly to detached Godot storage. Godot decodes
the bundle, validates its original-note IDs, model and layout, and prepares
CPU images, viewport geometry and source attack groups in the existing
worker. The main thread checks request generation and viewport again before
uploading textures in budgeted slices and installing retained ink. A pending
bundle has 45 seconds for detached preparation and upload. Visible retained
ink compilation has its own 45-second deadline. Playback acknowledgement
and placement measurements apply to the matching score revision.

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

- **Source loading and fingering.** Opening Moonlight took about 457 ms
  before source installation in the original paired Godot run. Import took
  23 ms, curriculum and progress restore took 120 ms, and the parallel
  LumiKey call took 424 ms. The command lane still waits for source
  preparation. The native timing driver can tick while source and fingering
  work runs outside the session lock. Full UI snapshots still read learner
  progress and project the current course. MIDI and clock-driven Free
  updates use the current phase directly.
- **Listen.** One audio thread renders the active Listen request with one
  latest pending request. Stop or a new selection cancels PCM generation
  at chunk boundaries. SoundFont loading itself is indivisible. The basic
  synthesizer shares the embedded interpreter. A WAV read can still occupy
  the serial command lane, and Godot decodes the audio on the main thread.
- **Godot.** Detached rasterization took about 601 ms of the original
  opening-window preparation. A resize before upload reuses the rasterized
  CPU atlas. A resize during upload discards the outdated fit and rebuilds
  it on the worker. Texture creation and retained drawing remain on main.
  An individual texture upload can exceed the 2 ms slice. First use at a
  new display scale can still resize and upload a display texture during
  drawing. This work and retained ink compilation contribute to frame tails.

The automated journeys use a synthetic MIDI device at the driver boundary.
Actual piano, audio and display acceptance remains pending.

### Post-migration audit measurements

The paired audit compared `7459582a` with the current worker on the same
host and CPU affinity. Both runs started with an empty cache, used the real
LumiKey provider and reached the final Moonlight selection. MIDI entered
through the embedded driver callback. The frame measurements used Godot
4.7.2 under Xvfb with Mesa llvmpipe. The three lesson transitions each
selected lesson 3 from a freshly opened first lesson and ended when the new
notation passed retained readiness. Frame entries report the median of
three per-run statistics.

| Measurement | Threaded baseline | Audited subprocess |
| --- | ---: | ---: |
| Whole-piece selection | 956 ms | 157 ms |
| Cold whole-piece bundle | 57.16 s | 13.84 s |
| Warm whole-piece bundle | 58.7 ms | 28.5 ms |
| MIDI callback p95 / max | 15.96 / 33.72 ms | 0.30 / 0.47 ms |
| Engine tick p95 / max | 26.13 / 88.24 ms | 0.27 / 0.29 ms |
| Embedded process peak RSS | 152.3 MiB | 69.5 MiB |
| Sampled concurrent RSS, engine plus worker | 149.1 MiB | 181.1 MiB |
| Opening-window frame p95 / max | 16.29 / 174.33 ms | 16.91 / 158.49 ms |
| Main-thread atlas upload CPU / final installation | 55.12 / 3.29 ms | 58.57 / 2.14 ms |
| Lesson selection to retained notation | 502.14 ms | 510.26 ms |
| During lesson transition, frame p95 / max | 19.87 / 30.92 ms | 18.84 / 24.62 ms |

The warm exchange carried 576 KB in and 3.66 MB out. It took 27.96 ms
round trip, with 22.53 ms in the worker. The 5.43 ms difference includes
both ends of the transfer and framing checks. Warm requests reuse the
parent's encoded source and the child's prepared artifacts. The total RSS
sum counts shared pages once per process. Opening frames still have large
spikes during retained drawing. Lesson transition durations ranged from
482 to 518 ms before and 488 to 525 ms after. The ranges overlap.
