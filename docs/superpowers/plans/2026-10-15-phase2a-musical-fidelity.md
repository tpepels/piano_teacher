# Phase 2A — musical correctness and source fidelity

User spec: [Phase 2A brief](../../phase2a-musical-fidelity-brief.md).
Base: latest origin/main `f5e1957`; branch `codex/phase2a-musical-fidelity` in
`/home/tom/Projects/piano_teacher_phase2a`. Do not merge into main.

## Intent and confirmed defects

Make the existing imported exercises readable and unambiguously traceable to
what the grader assesses, without rebuilding playback, curriculum or UI.
Read README, ROADMAP, both 2026-10-15 verification records and production code.
Initial full suite: 450 passed in 156.52 seconds. RTK is unavailable.

Actual file-to-production probes reproduce lost pickup/trailing-rest measures,
parallel unison tie chains merging, feedback on the wrong hand's unison,
per-measure lane changes swapping tied voices, discarded flats/keys, forced
bass for high left-hand music, reversed explicitly named hands and silently
rounded microtones. Temporary pre-fix evidence: `/tmp/piano-phase2a-corpus-audit`.

## Shared interfaces and compatibility

- Append defaulted fields to frozen `Note`: `source_id: str = ''`,
  `voice: str = ''`, `spelling: tuple[str,int,int] | None = None` (step/alter/octave).
  Imports assign deterministic unique attack IDs independent of filesystem path.
  Tied continuations extend that attack; source start/end stay precise quarter beats.
- Add frozen `KeySignature(beat,fifths,hand='both',mode=None)` and
  `ClefChange(beat,sign,line,octave_change=0,hand='both')` in `music.py`;
  append default empty tuple fields `Piece.key_signatures` / `Piece.clef_changes`.
  Keep explicit source key/spelling; no inferred key for MIDI without metadata.
- `source_note_id(note,index)` returns the imported canonical ID or a unique
  local legacy identifier for manually constructed internal/test phrases.
  Do not add new metadata to LearningPlan stage hashes or route version.
- `LessonScore` adds default `note_bindings`, keyed by deterministic emitted XML
  note ID. Each binding has source_id, is_attack, segment_index, source_beat,
  display_beat, pitch and hand. Stable whole-phrase lanes precede bar splitting.
- Preserve layout notes for every actual glyph, including continuations. Add
  those identity fields, `attack_map` (source ID → glyph ID), `continuation_map`,
  and a strict mapping schema flag. Validation checks one intended attack per
  required ID, correct pitch/hand and real SVG location. Feedback uses IDs.
  Legacy anonymous hand-built layouts remain an explicitly limited compatibility
  path; imported exercise grading must use strict maps.
- Keep display qstamps distinct from source beats. Source attack anchors use
  actual rendered x at exact source time; rests, held continuations, measure
  boundaries and terminal barlines keep measured geometry. Reject unrepresentable
  collisions rather than silently shifting/merging assessed attacks.
- Pass piece metadata to the existing lesson compiler. Source clefs/signatures
  remain contextual; otherwise choose readable G/F registers without pitch changes.
  Carry clef choices to the existing count-in glyphs. No new product controls.
- Corrected source structure may invalidate a prior XML stage's clean streak;
  preserve historical mastery/session data through existing identity migration.
  The supplied MIDI must retain 2346 notes / 237 bars / 712 beats / 301 stages.

## 1. Source identity, import time and metadata

Owner: import worker. Files: `music.py`, `score.py:import_piece`, focused new
`tests/test_source_fidelity.py`; coordinate score.py hunks with renderer worker.

- [x] Write real MIDI/XML tests reproducing unique repeated/unison/overlap IDs,
  voice-scoped contiguous ties, pickups (0,1,5), trailing rests and explicit names.
- [x] Confirm failing assertions before implementation; add unsupported malformed
  MIDI/ties, microtones, grace/nonpitched and conflicting measure/meter errors.
- [x] Implement source IDs and metadata with explicit source measures; preserve
  MIDI PPQ times and the supplied file's existing paired events/course structure.
- [x] Run import and course/persistence regressions; review and commit coherent work.

## 2. Explicit engraving, musical durations and readable registers

Owner: engraving worker. Files: `lesson_score.py`, `score_geometry.py`,
`lesson_validation.py`, `feedback.py`, renderer portions of `score.py`, new tests.

- [x] Reproduce wrong-staff feedback and crossing unison tie chains in actual Verovio.
- [x] Emit per-source attack/segment IDs and preserve stable lanes across measures.
- [x] Bind actual glyphs to source IDs, reject missing/duplicate/wrong-hand attacks,
  and prevent continuations satisfying an absent required attack.
- [x] Preserve source spelling/key/clef context; choose readable clefs where absent;
  keep source vs display timing separate, including tuplets and release quantization.
- [x] Verify real SVG/PNG and feedback correctness plus existing geometry/clock tests.

## 3. Required regression corpus

Owner: corpus worker. New `tests/fixtures/musical_fidelity/`, deterministic generator,
manifest/README and `tests/test_musical_fidelity_corpus.py`.

- [x] Check in at least 20 small supported real MIDI/MusicXML fixtures covering
  varied meters, pickup, key changes, flats/enharmonics, source voices, crossed
  hands, low/high registers, unisons, ties, rests, tuplets and unusual PPQ timing.
- [x] Include separate unsupported/ambiguous fixtures with meaningful error assertions.
- [x] Test actual import → generated variants → compiler → production Verovio:
  unique stable IDs, pitch/hand/source onset, exactly one attack, continuations,
  no disappearing/duplicated events, same assessment and feedback mapping.
- [x] Render representative PNGs and at least one actual multi-page exercise;
  retain pre-fix failures and final artifact manifest for reproducibility.

## 4. Consumer integration and preservation

Owner: root. Files: `server.py`, `teaching.py`, small existing Godot preparation
paths, checking scripts and focused tests, only where required by fidelity.

- [x] Write regressions for guided unison marks, metadata-through-active-exercise,
  count-in clefs matching the body, and unchanged saved ordinary MIDI progress.
- [x] Pass metadata and use canonical attack lookups; retain existing public target
  IDs/session keys as compatibility aliases and add canonical source IDs.
- [x] Keep playback, scoring policy, recovery, three-clean mastery, previews,
  score acknowledgements, dark UI and compact course unchanged.

## 5. Verification and delivery

- [x] Fresh full pytest, Godot parser, smoke_phase0.py, smoke_godot.py,
  smoke_adaptive_godot.py, real engraving/generated-lesson checks.
- [x] Actual 2346-note complete-song alignment, multi-page source evidence,
  visible playback 30/40/80/120 and normal launcher checks from README.
- [x] Independent whole-branch review and fixes with failing-first regressions.
- [x] Commit implementation on the requested branch, exact results, before/after
  explanation, PNG evidence, remaining limitations and Arch reproduction commands.
  Do not merge or wait for CI.

## Execution rules and review focus

Only one process owns port 8765. All Python commands use this checkout's explicit
PYTHONPATH with the existing venv; full suites and desktop journeys run sequentially.
Agents own distinct files or agreed score.py sections; root makes commits.
The user's detailed spec authorizes implementation; proceed through the plan
without a second approval round. Keep the original main and user files untouched.

Prioritize parallel tied unisons, quantization collisions, implicit pickups with
part measure agreement, enharmonic keys/cancellations, source MIDI stage hashes,
and real display anchors at the exact beats used for assessment.

## Final execution evidence

Final reviewed tree: 561 pytest tests passed in 200.42s, no skips/failures.
All 30 corpus file cases passed across 76 variants and 14 real PNGs.
Actual full source: 2346 attacks / 2579 glyphs / 60 pages at 40 BPM;
237 bars / 712 beats / all 301 prior stage keys preserved. Native visible
playback, normal-launcher UI, parser and required smokes passed locally.
Independent review found conflicting simultaneous MIDI keys; a real-file
RED→GREEN regression now rejects them while allowing equal duplicates.
See docs/phase2a-musical-fidelity-verification.md for exact commands,
checked-in PNGs, compatibility tests and remaining limitations.
