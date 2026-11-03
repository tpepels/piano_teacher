# Continuous repetition and engraved preparation measures

> Use systematic debugging, TDD and verification before completion. Work directly on main as explicitly requested; use bounded parallel work with separate file ownership.

**Goal:** One continuous native grand staff across attempts, with contextually correct signatures, a real timed rest measure and reliable source-bound interactions.

**Architecture:** Keep source notes, source notation and grading immutable. Add a separate semantic practice timeline derived from the score's measure context. Backend scheduling and the existing native compositor consume that same definition; no new renderer or raster strips.

**Spec:** `/home/tom/.codex/attachments/9e5a8122-a3dd-47f7-ac74-4ddef433ade6/Pasted text.txt`.

## Decisions

- Preparation uses the upcoming source/target measure's full meter, not a pickup or shortened terminal duration. Required final-to-initial clef/key/meter restoration occurs at the preparation measure's beginning. Internal changes remain unchanged.
- Model root `practice_timeline` is separate from `notes` and `notation_events`; its preparation events are rests with null source identity, no attacks and no grading. It supplies source duration, gap duration, stride and rest measure context.
- Forward repetitions consume one full preparation measure with no extra count-in, feedback hold or model reload. Rewind recovery keeps its adaptive target and reverse motion, then explicitly traverses a preparation rest before that target.
- Per-pass local notehead maps remain available to expressions/grace placement; an aggregate instance list records event ID, original source ID, pass index and screen position for all visible copies. Clicks always resolve to the original source.
- Only text was present in the attachment directory. Reproduce the specified Ala measures locally and preserve actual before/after frames.

## Constraints and review focus

- No full 24-shard audit; targeted framebuffer tests and fast CI only.
- Preserve canonical annotation-free audit mode, source bindings, MIDI grading, inference plans, manual XDG overrides, intentional archives and preservation bundle.
- Test pickups and shortened final bars; genuine changing keys, clefs and meters; visible source rests; both/inactive hands; simultaneous visible copies and clicks on earlier copies.
- Test preview, clean repeat, failed attempt, backward recovery and manual Retry; pause/resume within silence; delayed polls and BPM changes without hidden extra beats or geometry changes.
- Deliberate negatives remove a rest/boundary, add a redundant clef, shift the next source copy or corrupt the gap duration. Independent pixel checks must reject them.

## Tasks

- [x] Add failing semantic/timing regressions and real native before captures for Ala 30 left, Ala 32 both, Ala 29–32, changing context and existing rests.
- [x] Implement `piano_teacher/notation/practice_timeline.py` and model/backend integration: a validated, BPM-independent practice descriptor shared by transport and view, with explicit non-graded recovery preparation.
- [x] Update shared view state and native compositor: preserve context, engrave authentic whole-measure rests and full-staff barlines, retain real changes, accumulate pass-aware interaction geometry.
- [x] Add independent framebuffer oracles, corruptions and actual source-bound click checks; retain representative screenshots including playhead inside rest; exercise production app through Godot MCP.
- [x] Run targeted tests and fast CI, inspect diff and independent review, preserve generated editor caches/overrides, commit/push main, inspect status/worktrees and prune.

## Progress ledger

- Baseline main `5d193bf`; clean checkout. Existing continuous-loop tests: 10 passed. Godot MCP connected to Piano Teacher.
- Confirmed per-pass context reset and notehead-map clearing. Renderer and backend each use terminal measure length independently; preparation silence has no semantic rest event.
- Shared implementation and initial independent pixels exposed a real clef/cancellation-natural collision; reserve the complete key-change block. Static forward and actual backend flow captures: 95 passed, including exact pause/resume PNG equality.
- Independent review exposed recovery context suppression and overlapping previous-pass music/gaps. Global absolute preparation intervals and strict predecessor context fix both. Three additional real framebuffer cases plus image corruptions: 10 passed, 2 conditional skips.
- Review also found a dropped MIDI attack between the musical restart deadline and the next state poll. Due handoffs now settle before input routing, including an unobserved source ending; hardware timestamps and deadline anchors are retained. Perform Retry preserves its original count-in.
- Focused backend lifecycle, grading, Listen/Perform and adaptive recovery checks: 151 passed. Camera occurrence sampling: 3 passed; barline/ending semantics: 18 passed. Final fast CI: 494 passed, 6 conditional skips, Godot parse validation passed; no corpus shard was started.
- Real before/after and MCP production-app captures are retained in `docs/evidence/continuous-repetition-2026-10-26/`. Temporary live backend used isolated XDG data and was stopped; MCP playtest was stopped cleanly.
- Historical archive branches and the complete preservation bundle were retained and verified. The one generated editor-cache change was copied outside the checkout before restoration; original user override hashes are unchanged. Worktree inventory contains only main; `git worktree prune` completed.
- Optional recovery/volta framebuffer proof remains unverified: the synthetic source fixture was rejected before capture (dangling ending / incorrect display onset), documented with the evidence.
