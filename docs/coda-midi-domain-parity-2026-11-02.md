# Phase 3: MIDI-domain Coda reproduction — implementation audit

Reference: `annieetang/coda_backend@a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`.

## Musical equivalence contract

- Input is the original MIDI score and the caller-selected measure excerpt.
- Score, Part, Voice, dotted 3:1/1:3, each original automatically generated
  chord width, and slowdown ×2/×4 are **separately enumerated**.
- The PPQ-exact MIDI onset/release graph substitutes for original MusicXML
  written notes. No reconstructed beam, editorial tie, or articulation is
  treated as if it had been authored in MIDI.
- Every transformed note preserves its source ID and remains in the requested
  excerpt. Playback slowdown is implemented as BPM ÷2 or ÷4 rather than
  stretching notation; the performed seconds are equivalent.
- Continuous equal-duration runs may cross a barline when their attacks and
  releases are contained in the selected MIDI excerpt. The old strict
  MusicXML-specific barline guard was incorrect for this domain.
- The source quantization is shared across both hands, even when lesson stages
  are shown independently. The active meter at excerpt start is used for the
  author's chord-width enumeration.
- `midi_coda_catalog(piece, original)` yields an explicit outcome for every
  request: `inventory`, `generated`, `unchanged`, `author-invalid`, or
  `unrepresentable`, with reasons for the last two. Unsupported matrix
  conditions cannot silently count as successful parity.

## Verification still required before closing Phase 3

This inventory and regression coverage do **not** independently prove
complete Coda MIDI-domain parity. A separate pinned-author comparison must
execute each representable score/part/voice request, compare sounding MIDI
attacks/durations/IDs across varied polyphonic scores and enumerate all
discrepancies, including original invalid or missing outputs. It must check
the `unrepresentable` and `unchanged` entries rather than skipping them.
The MIDI-domain original reference inputs need a documented, reproducible
MusicXML bridge; raw input should never require MusicXML from a user.

Pedagogical superiority is a distinct Phase 7 acceptance criterion.
