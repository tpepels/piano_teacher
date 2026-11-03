# Step 3 — transformed notation and transport

Keep `main` working and commit small changes; no long corpus audit.

## Acceptance work

- [x] 3.1 Retimed scores preserve source-linked slurs, expressive marks, lyrics, fingering and safe authored rest spellings; use real source ids.
- [x] 3.2 Reject unsafe beat transformations around authored tie chains, tuplet groups, and voice/rest collisions; prevent orphan tie, beam and tuplet syntax.
- [x] 3.3 Regenerate rhythmic beams and tuplets from the transformed clock, retaining authored beam/tuplet metadata where timing is unchanged; preserve tie styling when endpoints remain valid.
- [x] 3.4 Use the same transformed note events and tempo map for engraving, Listen audio, live transport, assessment, recovery and partial seeks.
- [x] 3.5 Focused real-MusicXML regression suite and short Godot verification. Document any unsupported cases rather than silently dropping authored annotations.

## Invariants

- No changes to established stage keys, learning progress or original-piece notes.
- Every rendered graded attack resolves to its source note id.
- Printed noteheads and MIDI assessments agree on transformed starts/releases.
- Ordinary original passages retain original notation behavior.
- Authored rests, ties and tuplets must be preserved when safe; unsafe retiming
  must be explicitly ineligible, not silently strip the notation.
- CI is bounded to short tests, no broad notation corpus run.

## Status
2026-10-30: Step 3 started. Initial baseline from Step 2: bounded real
MusicXML tests and Godot 4.7.2 checks passed. No Step 3 acceptance yet.

## Accepted automated checkpoint — 2026-10-30

**5/5 scoped Step 3 work items implemented and accepted by short automated tests.**

- `notation/rhythm_safety.py`: imported MusicXML marks authored tie-chain
  attacks and tuplets ineligible for dotted timing changes, preserving their
  original durations and notation.
- `exercise_pipeline.py` / `learning.py`: source-aware eligibility is part
  of stage generation; no changes to original stage keys or saved progress.
- `application/score_artifacts.py`, `notation/lesson.py`,
  `notation/source_annotations.py`: transformed stages retain the original
  MusicXML. The projector reanchors slurs and note expressions by source id,
  preserves safe authored rests/ties, moves exact note-anchored dynamics to
  their new time, regenerates beams from the retimed clock and retains tuplet
  presentation details on unchanged matched groups.
- `tests/test_transformed_source_notation.py`: a real imported three-bar
  MusicXML fixture with authored slur, beams, staccato, fingering, anchored
  direction, tied continuation and dotted-half rest; plus explicit quintuplet
  protection and unchanged authored bracket/number restoration.
- `tests/test_transformed_transport.py`: synthesized Listen WAV note attacks,
  releases, source ids, full duration and silence match tempo-mapped grading;
  partial seek/time-map origin also checked.
- **Run [41076832890](https://github.com/tpepels/piano_teacher/actions/runs/41076832890)**
  at `e810d967`: 66 Python tests passed, one Godot-dependent Python test
  skipped before installing Godot, then the settings test passed separately.
  Godot 4.7.2 main parsing succeeded; visual clock and Listen drift returned
  zero failures. This workflow is opt-in/path-triggered only, with a three
  minute maximum and no broad notation corpus audits.

### Remaining production acceptance (outside scoped automated Step 3)

- [ ] Real piano MIDI plus speaker audio and manual notation/pixel inspection
      of transformed source scores.
- [ ] Broader unusual MusicXML: multiple concurrent voices, cross-staff
      slurs/ties, nested tuplets, ambiguous directions, ornament interactions
      and publisher-specific tie styling. Unsafe source rhythms currently do
      not generate dotted variants rather than silently dropping their marks.

This checkpoint does **not** certify all possible MusicXML, physical MIDI
latency or educational effectiveness. The next system roadmap phase is richer
exercise/adaptation algorithms, not more broad CI.
