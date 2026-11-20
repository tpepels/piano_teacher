# Documentation index

[ROADMAP.md](../ROADMAP.md) records development phases and decisions. The
learner-facing behaviour is specified in [Practice flow](practice-flow.md);
where another document disagrees, the practice flow wins.
The [current application architecture](architecture/system.md) is the single
overview of actual owners; the tracker records review and acceptance gaps.

## Current technical contracts (reference, not roadmaps)

| Area | Canonical document |
| --- | --- |
| Practice flow for one piece (owner decisions) | [Practice flow](practice-flow.md) |
| Current application owner map | [Application architecture](architecture/system.md) |
| Practice state machine and authorized timeline | [Practice state machine](architecture/practice-state-machine.md) |
| Active playback authorization and ownership | [Playback coordinator](architecture/playback-coordinator.md) and [ADR-0001](architecture/decisions/ADR-0001-single-authority.md) |
| Architectural remediation and incomplete gates | [Ownership and progression tracker](architecture/ownership-and-practice-progression-remediation.md) |
| Typed embedded protocol, startup and packaging | [Native runtime](inprocess-runtime.md) |
| Generator interface, Coda/Fukuda adaptive composition | [Composed MIDI generators](architecture/composed-midi-generators.md) |
| Fingering data and inference | [Piano fingering](piano-fingering.md) |
| Teaching behavior and mastery criteria | [Teaching methodology](teaching-methodology.md) |
| Fixed retry contracts, adaptive proposal and evaluation | [Mistake-response policies](mistake-response-policies.md) |
| Durable measurement and read-only analytics | [Local learning evidence contract](learning-measurement.md) |

## Historical references

The [4 November subsystem inventory](architecture/historical/system-2026-11-04.md)
and superseded [transport/voice contract](architecture/transport-and-voice-contract.md)
preserve earlier implementations. They do not override the current owner map,
playback/score ownership or moving-window teaching contracts. Older reports,
screenshots and plans remain available in git history.

Phase 5 is complete in source: independent ownership review and existing
core/native checks pass. Phase 6 software gates pass at `9654d2a3`, including
the strict relocated standalone build/boot. Phase 6 remains incomplete for
physical MIDI, speakers, latency, real playing and clean-machine desktop
acceptance; see the tracker for the verified/unverified matrix.

## Rules

1. User input stays MIDI-only. Generated MusicXML is internal notation output.
2. There is one production runtime: Godot + embedded CPython + typed native IPC.
3. No old file-import facades, parallel Qt UI, HTTP service, external server,
   second transport clock, or compatibility backend may be reintroduced.
4. Godot MCP under godot/addons/godot_mcp_toolkit/ is optional editor tooling,
   excluded from the production runtime and standalone package.
