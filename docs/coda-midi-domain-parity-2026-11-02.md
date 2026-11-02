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

## Executable differential (2026-11-02)

`scripts/probe_coda_midi_author_algorithms.py` injects the exact same
MIDI-derived 128-pitch onset/duration/piano-roll matrices into the actual
unmodified pinned `ExerciseLine` transformation methods and the independent
adapter. It compares **sounding pitch, onset and release**. A separate
tolerance of 2×10⁻⁶ quarter beats is used only to classify music21
serialization rounding; source-note or pitch loss is never tolerated.

The domain is **all 16 supported imported-MIDI regression fixtures plus
all 17 bundled real repertoire files**, not an undocumented selection.
If the binary Coda matrix cannot express a file within its bounded capacity,
it is recorded as a `source-rejected` case with an explicit reason rather
than counted as success.

The first 16-file run (GitHub Action 41479523951) compared 181 author
transformation requests. Its initial diagnostic count was 33 exact, 8
apparent mismatches, 83 author-invalid, 46 author-None and 11 exceptions.
Detailed inspection showed that 3 apparent mismatches were author-produced
six-note blocked chords (violating the paper's five-tone upper bound) and
the other 5 were within 10⁻⁶ quarter-beat serialization rounding.
The revised run explicitly classifies these rather than hiding them.
The expanded 33-file differential is still diagnostic and is not a
comprehensive input-domain parity certificate.

## Long-song algorithm implementation

`research/coda_midi_sparse.py` replaces the product's dense 128-row
piano-roll allocations with source-indexed attack/rhythm runs. Both dotted
patterns, each enumerated chord width and all original Voice/Part categories
are generated directly on the compact exact MIDI grid; x2/x4 slowdown
remains tempo-map based. Chord subgroups visit only onset-containing windows,
not all intervening silent ticks. The existing dense Coda oracle remains
unchanged, bounded and independent for cross-checking.

The original matrix limit remains enforced when actually allocating a
dense reference matrix; `max_cells=None` is permitted only in the sparse
MIDI quantization chooser. This is necessary to support the 17 complete
real MIDI repertoire pieces, all of which the earlier bounded dense
comparison rejected as oversized.

## Pinned original parity for longer repertoire excerpts

The pinned author backend's dense array cannot run directly over the whole
17-piece repertoire. The differential therefore runs on *safe, explicitly
bounded* short windows from the beginning, middle and end of every real
piece. Each chosen window contains original source notes in full, no clipped
onsets or releases, with independent source voice owners, and a matrix size
below the original backend's hard limit. All requested operations, original
failures, and differences are recorded. These samples are separate from the
full-song production sparse algorithm tests and **do not certify unexamined
full-song author algorithms**. Individual bounded windows are not assembled
into a fictitious whole-piece author output.

## Bounded original backend runs

The expanded three-window differential originally exceeded its 95-second
timeout. That run had a mistakenly permitted `continue-on-error` flag,
which has been removed. Original algorithm mismatches, missing windows, and
incomplete executions now fail the strict comparator.

The three reproducible repertoire windows run as separate bounded CI jobs:
position 0 together with all 16 original MIDI fixtures, and positions 1
and 2 independently on all 17 real pieces. Every position uses the actual
pinned author code, never a copied oracle, and writes a full per-request
report. The complete-piece sparse tests stay separate and mandatory.
