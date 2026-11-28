# Transition and rendering consolidation audit

## Evidence and scope

The visual captures before this change showed isolated initial frame stalls, otherwise stable lightweight pacing, and full-capture failures involving transition timing, MIDI witness classification and incomplete policy coverage. They do not establish a single measured CPU bottleneck.

Reviewed the preceding timing, pacing, recovery, audio preparation and feedback changes between 61992b6 and b5931d2, excluding unrelated adaptive-difficulty research from runtime changes.

## Ownership

- Python owns musical time, lesson decisions and attempt settlement. Resume cuts its timeline once.
- The score stream queue owns visibility-safe withdrawal planning and application; admission owns occupied geometry. Timed replacement and guided recovery apply the plan actually inspected, rather than computing a second withdrawal policy during commit.
- The score preparation worker owns CPU asset preparation and stable model hashing. The existing budgeted upload pipeline owns texture publication. Score-ready publication does not run a second status warmup.
- Frame pacing and MIDI witness detection each have one shared verifier. Image inspection remains an optional extra witness, not a different timing policy.

## Remaining verification

The Python-to-Godot clearance measurement is still a scalar snapshot; the renderer validates current geometry again when admission arrives. This is not a new distributed atomic reservation protocol. Do not remove that safety check to eliminate legitimate revalidation.

Initial stalls have not been attributed to a specific operation by a new native run. The duplicate warmup and main-thread model hash were unnecessary work; shader initialization, lazy composite textures, synchronous journal durability and native response dispatch remain possible costs. The presentation owner emits a phase breakdown only for expensive frames when timing diagnostics are enabled. Do not move journal durability off-thread without preserving commit ordering.

The previous asynchronous Listen PCM preparation remains isolated and removes genuine blocking work, but its contribution to startup hitches was not established. Public compatibility methods and unreferenced-looking helper scripts have not been deleted solely on the basis of unavailable repository-wide search.

Run the complete regression, embedded production verification, full visual capture and lightweight 60 FPS capture before claiming the native acceptance gate has passed. Keep thresholds unchanged. Compare both capture types and use the phase breakdown to identify any remaining real stalls before making further changes.

## Follow-up

Composite source masks and their display-sized textures now use the detached CPU preparation and existing upload budget. A stale withdrawal plan is rejected before the first journal write, including when its clip has become exposed. A placement that already conflicts with retained source or peer ink is refused before any withdrawal. Automatic display recovery can receive a fresh revision-bound clearance after failed-take identity validation. This does not convert the asynchronous backend/render protocol into a cross-process transaction; safety still depends on live renderer revalidation and the existing authorized-failure boundary. Native verification and frame timing remain required.

Local acceptance is now `bash scripts/verify.sh`; see [local-testing.md](local-testing.md).

## Follow-up to the 59885ba acceptance archive

The regression archive had three failed tests: preferred MIDI device loss, Free travel duration, and an obsolete speculative repeat. The Free duration target of 1.5 s applies when it fits the existing 80 BPM anti-sprint cap; at 20 BPM a three-beat move takes 2.25 s, not an artificial 120 BPM sprint. Automatic discovery now selects an unambiguous keyboard only before a preference exists. MIDI visual probes resolve the active canonical source note at the authorized opening using `midi_pitch`; the actual painted head is still required as separate evidence.

Retry and Resume use one measured clearance, splitting retained source ink from trailing silence. The new count-in can overlap the latter only while leaving room for the opening header; neither exposed ink nor count-in beats may be discarded. Peer ink stays conservative and actual admission revalidates geometry. Ordinary nominal notation textures now share the existing detached sizing and upload pipeline with composite status masks. Dynamic-size cache misses still use authentic resampling and are logged when expensive. Lightweight hitch reports additionally retain pre/post-draw boundary times to distinguish time between draws from time inside draw; these are diagnostic, not proof of GPU duration. No pacing threshold changed. The next native acceptance run must measure the remaining five hitches and Moonlight Retry again; their elimination is not established by this patch alone.
