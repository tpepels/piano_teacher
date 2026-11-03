# MIDI-native architecture audit — 2026-11-03

## Production boundaries checked

- One Godot process, with one embedded Python command worker. No HTTP
  listener/server or socket-based score delivery. Godot uses the
  in-process request adapter and the revisioned native layout/model
  publication. Direct-file-load, SVG/PNG page and non-native layout
  commands have been removed from the active bridge.
- `LearningPlan` consumes immutable `LessonPlanDefinition` and
  `ExerciseStage` values. `PracticeEngine` does not dispatch on named
  Coda/Fukuda techniques. Native notation, Listen, grading, feedback
  and progress derive their selection from the same source-backed stage.
- Whole-piece algorithms implement `generate(piece)`; optional
  `with_feedback` receives source-note error families, while
  `with_mistakes` remains available for source-ID-only algorithms.
  `ComposedLessonGenerator` merges compatible complete courses.
- Adaptive composers require `passage_stages(piece, original, kind=...)`;
  `AdaptiveComposedLessonGenerator` compiles a source-safe catalog once
  and selects meaningful note reductions, timing changes or tempo
  changes. The named Coda+Fukuda preset supplies two replaceable
  participants. `register_composed_lesson_generator(..., adaptive=True)`
  registers future combinations without editing the application roots.
- A stage's `origin`, `technique`, `display_name`, and tempo policy
  travel as explicit metadata. Shared selection and presentation never
  infer algorithm family from level-name prefixes. The unchanged original
  remains the terminal stage, checked by immutable definition validators.
- Course versions and complete stage signatures isolate history.
  Source-measure migrations do not transfer obsolete mastered stages
  or BPM streaks. The user's saved choice remains explicit.

## Removed obsolete runtime surfaces

| Removed | Replacement |
|---|---|
| `POST /load` arbitrary file path | `POST /library/open` against the configured MIDI library |
| `GET /score.svg` and `GET /score.png` | Native atlas/layout plus source-semantic model |
| `GET /score/layout?native=0` | Native-only `GET /score/layout` |
| HTTPRequest lifecycle names in score publication | In-process command slots and command-status diagnostics |
| Stage-name-prefix decisions in central selector | Producer-owned technique/provenance metadata |
| Hard-coded Coda/Fukuda stage-builder imports in adaptive catalog | Participant `passage_stages` protocol |
| Generic composer dropping graded error families | `with_feedback` fan-out with ID-only fallback |

## Still present, deliberately outside legacy runtime compatibility

1. `piano_teacher/rendering/legacy/` contains actual Verovio page
   engraving and source geometry currently used to derive genuine native
   atlas artwork; removing these modules without replacing their
   algorithms would break score fidelity. The directory name is
   historical, but the dependency is live. Consolidating it under a
   better named canonical source-engraving package would require a
   repository-wide import/test migration and actual native-frame proof.
2. `piano_teacher/score.py`, `score_geometry.py`, and `raster.py`
   are compatibility re-exports used by offline tooling and legacy
   research tests. They are not alternate application services and
   are not exposed as in-process rendering routes. Deletion requires
   a verified audit of *all* downstream test/tool imports.
3. `HeuristicLessonGenerator` and `LegacyStrategy` retain explicit
   historical/baseline comparison paths behind the same generator and
   score contracts. They do not create a second runtime/backend.
4. `piano_teacher/server.py` and `godot/main.gd` remain substantial
   application coordination roots. Both delegate to service/presentation
   collaborators, but their size and remaining orchestration are not
   proof of full separation. This is still maintainability debt.
5. The in-memory command protocol still carries GET/POST method names,
   path-like route identifiers, numeric status codes and response slots
   resembling the former HTTP interface. It makes no network calls and
   does not start a server, but it has not yet been redesigned as a
   fully typed IPC message schema. The native C++/Godot/Python protocol
   must be migrated together before claiming complete removal of
   HTTP-shaped protocol semantics.

## Bounded acceptance

Run `bash scripts/verify-hybrid-workflow.sh --focused`, then
`bash scripts/verify-hybrid-workflow.sh --corpus` separately when needed.
The focused suite now covers stage metadata, arbitrary contributor
registration, generic source-local error repairs, composed feedback,
source timing and semantic model projection, removed in-process routes, a genuine native-score/model
request, and Godot's settings/step-picker/READY test.

This document is a source audit, not a claim of a completed local run.
New commits are not yet certified by the developer's Godot installation.
Long-form native framebuffer density, Bluetooth/USB latency, and live
closed-loop teaching still require their own acceptance evidence.
