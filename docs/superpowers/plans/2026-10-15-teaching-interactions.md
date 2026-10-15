# Teaching Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Teach imported MIDI through untimed guided learning, timed adaptive practice, audible demonstration and uninterrupted performance, without a supplied catalogue.

**Architecture:** A pure Python TeachingController recognizes guided targets from the existing active variant. PracticeEngine owns MIDI receipt, mode transitions, score revisions, transport and persistence. Godot renders backend state through the existing score viewport, a contextual HintKeyboard and focused teaching controls; it never supplies student answers or owns a second musical clock.

**Tech Stack:** Existing Python/Mido/SQLite, music21/Verovio/CairoSVG, Godot 4.7 and local synthesis.

**Spec:** [User handoff](../../teaching-interaction-handoff.md), [gap analysis](../../teaching-interaction-gap-analysis.md), existing ROADMAP.md and moodboard.png.

## Global constraints

- Preserve fixed timing line, moving engraved score, tempo-dependent spacing, short count-in capped near four seconds, source-note coverage and dark forest/charcoal/stone palette.
- Five distinct wrong/missed required notes trigger a retry only after the current two-bar boundary; slow by 10%, restore toward the selected target.
- Only three clean, full, unassisted target-speed student attempts master a required stage. Guided work, demonstrations, previews and partial retries never confer mastery.
- Use imported music and the existing active variant. No songs, courses, artwork or exercise catalogue is added.
- Commit each completed milestone after real verification; physical MIDI/speaker acceptance remains explicitly pending.

## Review focus

- Held/repeated keys and rolled chords must not silently satisfy future targets; test physical releases, chord expiry and duplicated note-on.
- Obsolete input, score acknowledgements and HTTP responses must not advance a changed lesson; test revision/session invalidation and fast navigation.
- Device loss, preview and audible demonstration must never count as student success; test each through the ordinary backend input seam.
- Sparse rests, ties and mixed meters must preserve source time and full-song notes; test generated phrases and actual imported MIDI.
- Hint keyboard/pause UI must retain readable notation at 800×600; test real Godot controls and actual rendered pixels.

## P0 — Baseline and preservation gate

Files: `docs/teaching-p0-baseline.md`, verification artifacts under `/tmp/piano-teaching-p0/`.

- [x] Fetch main and create isolated feature worktree at current HEAD.
- [x] Run all existing tests, parser and three smoke scripts before product changes.
- [x] Capture desktop motion at supported tempos and explicit 40 BPM lead-in/onset/rest/mid/end frames, plus normal launcher screens on the actual MIDI.
- [x] Inspect moodboard consistency, record manual hardware repro instructions and commit baseline/spec/plan.

## P1 — Guided Learn and contextual hints

Files: new `piano_teacher/teaching.py`, `godot/hint_keyboard.gd`; integrate `server.py`, `main.gd`, `score_overlay.gd`; new controller, backend journey and Godot interaction tests.

Interfaces: `TeachingConfig(chord_window_seconds=.25, stall_seconds=3.0, persistent_hints=False)` and `TeachingController.bind(stage_key, revision, variant, fragment_start, fragment_end, now, connected)`, `start/receive/tick/pause/resume/stop/set_connected/snapshot`. Input times come from the MIDI callback. Stable IDs combine stage identity and active-variant source index. Snapshot includes phase, revision, expected notes, heard pitches, hint visibility, target progress, correct/assisted/wrong feedback and `mastery_eligible=False`.

- [ ] Write failing recognition tests for order, chords/window expiry/early release, repetition/held notes, noise, pause, device loss, wrong-then-correct, stall/persistent hints and no mastery.
- [ ] Implement the pure controller, verify its tests and review its contract.
- [ ] Write failing backend tests feeding actual Mido messages through `_receive`; add explicit `learn`, `learn_retry`, `practice` and hint actions while preserving legacy timed `start()` semantics.
- [ ] Use a source-measure-based one/two-bar display fragment from the active variant; bind score geometry and target feedback to its current revision. A stale score ack cannot start a different guided session.
- [ ] Implement a static expected-note score path and contextual piano keyboard showing expected/heard keys with pitch names; dark UI, no advancing wall clock in Learn.
- [ ] Add real Godot learner tests for automatic Learn after UI import, wrong note → hint → correction → next target → guided completion → timed Practice. Check 800×600 and larger windows, run full suite and commit P1.

## P2 — Instructional timed practice and recovery

Files: `server.py`, teaching integration/presentation, focused recovery tests and learner journey.

Interfaces: existing transport/assessment/recovery remain authoritative; add explicit mode, concise `next_action`, retry range, recurring-trouble state and a bounded guided-remediation return context.

- [ ] Write failing whole-learner tests for five mistakes → completed boundary → correct range/10% slowdown → optional repeated-pitch guidance → unchanged timed clock → clean partial recovery → full target-speed mastery.
- [ ] Implement instructional transitions and repeated-trouble routing; no assisted/partial false mastery.
- [ ] Verify jitter/grace at 30/40/80/120 BPM, mixed meters, rests and multiple systems; inspect actual moving frames; run full suite and commit P2.

## P3 — Audible Listen and uninterrupted Perform

Files: new focused synthesis/demonstration module; `server.py`, Godot audio and controls, audio/performance journey tests.

Interfaces: demonstration consumes the active generated note set and selected BPM, with independent mode/phase metadata and no student recorder. Perform uses existing clock/assessment, disables automatic rewind and yields a summary with accuracy/timing/missed pitches/weakest bars.

- [ ] Write failing tests for audible sample content/pitch/duration, shared source identity, rests/held endings and zero assessment/mastery credit.
- [ ] Implement local bounded-memory audible synthesis and Listen transport, with real sound-producing playback and an honest loading/error state.
- [ ] Write failing Perform tests: misses continue through endpoint; original whole-song stage retains every source note; summary can select weakest section.
- [ ] Implement Perform and real rendered/audio software checks; run full learner journey and suite, commit P3.

## P4 — Dark learning UI and navigation

Files: focused Godot controls/views and interaction/capture tests; avoid gratuitous main.gd restructuring.

- [ ] Write failing learner-control tests for mode clarity, pause sheet Resume/Retry/Listen/tempo/hand/Exit, keyboard focus and responsive hint visibility.
- [ ] Replace prominent numeric stage metadata with instruction/next transition, clear current/target BPM and connection status; use color plus text/shape indicators.
- [ ] Implement reliable paused bar selection only if it can preserve source boundaries, revision safety and no partial mastery.
- [ ] Verify every control at fullscreen, 1536×960, 1024×768 and 800×600 with Godot-produced frames; run full suite and commit P4.

## P5 — Natural progression and saved learner state

Files: focused learner-progress module/SQLite migration, `learning.py` and server/UI integration, representative generated fixture journeys.

- [ ] Write failing tests for saved trouble spots, resumable musical units, optional placement/skip with distinct non-mastered status, documented redundant-stage criteria and target-tempo continuity.
- [ ] Implement meaningful progression using the consolidated course; preserve three-clean mastery and exact source coverage. Teach successive short ideas before combining hands/phrases.
- [ ] Test easy melody, mixed-meter two-hand music, sparse rests, dense fast section, repeated chord, absent MIDI and complete 237-bar source.
- [ ] Run the whole simulated learner journey from import through Learn, hints, timed recovery/restoration/mastery, next stage, Listen and Perform. Run all preservation checks and final independent review, commit P5 and report exact results/remaining limitations.

## Execution ledger

- Baseline: `7670eb5`; root main and origin/main matched after fetch.
- Worktree: `/home/tom/Projects/piano_teacher_teaching`, branch `feat/teaching-interactions`.
- Ruling: proceed from the user's detailed handoff as the approved design and execution instruction; do not add another approval round.
- Ruling: preserve direct legacy timed API calls; UI-import completion explicitly enters Learn. This avoids silently changing existing transport integrations while making the student path guided by default.

- P0 complete: 244 tests, parser, three smoke scripts, source alignment and 58 actual desktop frames pass; report `docs/teaching-p0-baseline.md`. Hardware gate remains open.
