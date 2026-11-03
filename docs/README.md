# Documentation index

**Only [ROADMAP.md](../ROADMAP.md) defines the current development phases, open blockers, priorities, and exit gates.** Update that file when work changes. Do not create another active plan or handoff document.

## Current technical contracts (reference, not roadmaps)

| Area | Canonical document |
| --- | --- |
| Application and ownership | [Architecture](architecture/system.md) |
| Typed embedded protocol, startup and packaging | [Native runtime](inprocess-runtime.md) |
| Generator interface, Coda/Fukuda adaptive composition | [Composed MIDI generators](architecture/composed-midi-generators.md) |
| Real keyboard acceptance procedure | [Physical MIDI checklist](verification/coda-fukuda-physical-midi-checklist.md) |
| Notation/transcription specification | [MIDI transcription rules](midi-transcription-rules.md) |
| Fingering data and inference | [Piano fingering](piano-fingering.md) |
| Teaching behavior and mastery criteria | [Teaching methodology](teaching-methodology.md) |

## Verified historical or research evidence (not development instructions)

- [Phase 3 Coda MIDI-domain completion](coda-midi-phase3-completion-2026-11-02.md).
- [Phase 4 Fukuda MIDI-domain implementation](fukuda-midi-phase4-2026-11-02.md).
- `docs/research-*.md`, `docs/coda-*.md` and dated notation reports are experiments, comparisons or implementation evidence. Their time-relative claims must not override ROADMAP.
- `docs/evidence/` contains captured images, logs, corpus ledgers and provenance.
- [Archived plans and superseded architecture](archive/development/README.md) preserve old material without an active implementation track.
- Godot MCP under godot/addons/godot_mcp_toolkit/ is optional editor tooling, excluded from the production runtime and standalone package.

## Rules

1. User input stays MIDI-only. Generated MusicXML is internal notation output.
2. There is one production runtime: Godot + embedded CPython + typed native IPC.
3. No old file-import facades, parallel Qt UI, HTTP service, external server, second transport clock, or compatibility backend may be reintroduced.
4. Every phase status needs its stated test evidence. The latest code is not certified by an earlier green test run.
5. New findings change `ROADMAP.md` and, when necessary, the matching technical contract; do not add a competing `phase-plan.md`.

