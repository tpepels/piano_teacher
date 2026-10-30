# Step 3 — transformed notation and transport

Keep `main` working and commit small changes; no long corpus audit.

## Acceptance work

- [ ] 3.1 Retimed scores preserve source-linked slurs, expressive marks, lyrics, fingering and safe authored rest spellings; use real source ids.
- [ ] 3.2 Reject unsafe beat transformations around authored tie chains, tuplet groups, and voice/rest collisions; prevent orphan tie, beam and tuplet syntax.
- [ ] 3.3 Regenerate rhythmic beams and tuplets from the transformed clock, retaining authored beam/tuplet metadata where timing is unchanged; preserve tie styling when endpoints remain valid.
- [ ] 3.4 Use the same transformed note events and tempo map for engraving, Listen audio, live transport, assessment, recovery and partial seeks.
- [ ] 3.5 Focused real-MusicXML regression suite and short Godot verification. Document any unsupported cases rather than silently dropping authored annotations.

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
