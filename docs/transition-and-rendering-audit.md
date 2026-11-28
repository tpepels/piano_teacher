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
