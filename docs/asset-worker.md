# Native score asset worker

The native bridge has two independent command lanes: the musical owner and
a single read-only asset consumer. The rendering thread submits values and
drains results; neither background lane can invoke Godot scene objects.

## Lifecycle

The asset mailbox owns queued, active and completed work under one mutex.
Its capacity (eight total commands/results) prevents unbounded asset
backlogs. A full mailbox rejects submission rather than blocking the UI.
Cancellation removes pending and completed work immediately and suppresses
the active reply. State-changing commands are never cancelled through
this port. Stop changes the wait predicate while holding the mailbox
mutex, wakes the consumer and discards unpublished work. The native
musical thread joins the asset consumer before closing CPython's engine.

The source revision, fingerprint, stage and hand travel with the actual
bundle request. Python validates them before starting work and checks the
current selection and artifact generation again after completion. Changing
the source retires the entire artifact instance, without acquiring its
engraving lock under the musical session lock. Each worker retains its
own old instance until it finishes; no old layout can overwrite the new
generation. A new selection gets a new artifact instance on its first
locked read, including ordinary lesson navigation. Retired instances stop
at checkpoints between Verovio engraving, layout and atlas extraction
phases. Durable source-keyed caches remain reusable. A warm state snapshot
reads the atomically published source model without acquiring the model
lock held by the background semantic/fingering projection.

The Godot asset session cancels the request on replacement, Retry, close,
failure and shutdown. Its separate CPU engraving/texture-upload path
checks a mutex-protected cancellation flag between CPU preparation
phases and checks generation and viewport before installation. Shutdown
is terminal and joins the task before releasing its result. Only the
rendering thread uploads textures and installs retained ink.

## Limits and verification

Cancellation does not interrupt an active native Verovio call or forcibly
terminate a thread holding the GIL. It discards the reply, prevents stale
queued work from starting, and retires obsolete source generations at
cooperative checkpoints. A slow active engraving can still delay its
successor on the asset lane until its next checkpoint; CPython GIL
contention can still affect timing.
The separate C++ mailbox test runs in core CI without Godot dependencies.
Python tests deliberately hold the old engraving lock during navigation.
Full embedded production and physical MIDI latency tests remain necessary.
