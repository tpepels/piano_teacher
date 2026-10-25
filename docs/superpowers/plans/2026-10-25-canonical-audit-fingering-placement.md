# Canonical audit recovery and conventional fingering placement

> **For agentic workers:** Use systematic-debugging, test-driven-development and verification-before-completion; independent runner and canonical-boundary changes run in parallel.

**Goal:** Reliable failure packaging, an explicit annotation-free canonical audit, and close, readable native finger placement.

**Architecture:** Keep the Lumikey provider and whole-piece assignments unchanged. Canonical capture explicitly disables the native fingering layer and removes only authored MusicXML fingering from reference preparation. Presentation metadata and notehead-aware layout stay in the existing native compositor.

**Spec:** `/home/tom/.codex/attachments/503439fc-1fa6-45e5-b87d-c3c6fba5c09e/Pasted text.txt`.

## Constraints and review focus

- No full 24-shard run; preserve successful captures/checkpoints, watchdogs and limits.
- Preserve actual failure statuses, user XDG overrides, timed events and canonical source IDs.
- No global digit masks, relaxed thresholds, suppressed symbol categories or provider changes.
- Preserve tuplets/time signatures and unrelated technical markup during normalization.
- Capture mode belongs to provenance/cache identity; incompatible captures cannot be reused.
- Stable placement anchored to individual notes/voices, including shared keys, close chord tones and ties.
- Avoid silent label loss; expose genuinely unsatisfiable placement.
- Preserve historical archives and bundle; commit/push main and finish clean.

## Implementation tasks

- [x] Runner: reproduce direct-file packaging import failure; compare Bash bytes/history and syntax; test actual subprocess failure/recovery/wrapper paths; preserve exit status and package once.
- [x] Canonical boundary: `piano_teacher/notation/audit_annotations.py` exports `CANONICAL_CAPTURE_CONFIG`, `canonical_musicxml(xml)` and `canonical_piece(piece)`. The coordinator uses canonical_piece before lesson/reference creation and embeds the configuration in fixture/manifest/checkpoint identity. `tests/godot/native_verovio_overlay.gd` requires the explicit mode and disables the view annotation layer.
- [x] Native presentation: add `set_fingering_annotations_enabled(enabled:bool)` (default true) and central paint/editor guards; replace distant lanes with compact glyph-ink-aware note/chord/voice candidates and local collision resolution. Add source MusicXML presentation hints to projection without reinference or override writes.
- [x] Strict framebuffer tests: digit ownership, head attachment, distances/collisions, scrolling, corrections, authored hints, simplified/original passages and deliberate musical/digit corruption. Inspect real Hanon, Chopin and Bill Evans frames through Godot MCP.
- [x] Focused tests, bash syntax, fast CI, retained-evidence diagnosis, before/after evidence, independent review, commit/push and worktree/status inspection.

## Ownership and interfaces

Runner worker owns coordinator, packager, Bash wrapper and runner tests. Canonical worker owns audit normalization module, canonical Godot capture harness and isolation tests; coordinates coordinator integration with runner worker. Main owns native view/main UI, placement metadata/projection/backend seams, presentation tests and evidence.

The native view setter controls only fingering paint and editing. `drawn_fingerings` remains dedicated annotation evidence. The model event `fingering` dictionary keeps `source_id`, `finger`, `hand`, `origin`; optional `placement` adds source-authored presentation hints. No timed model event or grading state changes.
