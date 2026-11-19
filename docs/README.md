# Documentation index

[ROADMAP.md](../ROADMAP.md) records development phases and decisions. The
learner-facing behaviour is specified in [Practice flow](practice-flow.md);
where another document disagrees, the practice flow wins.

## Current technical contracts (reference, not roadmaps)

| Area | Canonical document |
| --- | --- |
| Practice flow for one piece (owner decisions) | [Practice flow](practice-flow.md) |
| Practice state machine and timeline (plan, steps 1-3) | [Practice state machine](architecture/practice-state-machine.md) |
| Active playback authorization and ownership | [Playback coordinator](architecture/playback-coordinator.md) and [ADR-0001](architecture/decisions/ADR-0001-single-authority.md) |
| Architectural remediation and incomplete gates | [Ownership and progression tracker](architecture/ownership-and-practice-progression-remediation.md) |
| Historical subsystem inventory (superseded) | [System architecture, 4 November](architecture/system.md) |
| Typed embedded protocol, startup and packaging | [Native runtime](inprocess-runtime.md) |
| Generator interface, Coda/Fukuda adaptive composition | [Composed MIDI generators](architecture/composed-midi-generators.md) |
| Fingering data and inference | [Piano fingering](piano-fingering.md) |
| Teaching behavior and mastery criteria | [Teaching methodology](teaching-methodology.md) |
| Fixed retry contracts, adaptive proposal and evaluation | [Mistake-response policies](mistake-response-policies.md) |
| Durable measurement and read-only analytics | [Local learning evidence contract](learning-measurement.md) |

The superseded transport/voice and November 4 ownership descriptions are
historical only. Older reports, audits, screenshots and plans remain
available in git history. Neither historical document overrides the
current playback/score ownership or moving-window teaching contracts.

## Rules

1. User input stays MIDI-only. Generated MusicXML is internal notation output.
2. There is one production runtime: Godot + embedded CPython + typed native IPC.
3. No old file-import facades, parallel Qt UI, HTTP service, external server,
   second transport clock, or compatibility backend may be reintroduced.
4. Godot MCP under godot/addons/godot_mcp_toolkit/ is optional editor tooling,
   excluded from the production runtime and standalone package.
