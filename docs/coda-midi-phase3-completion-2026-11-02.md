# Coda Phase 3 — complete MIDI-domain algorithm reproduction

**Status: IMPLEMENTED AND VERIFIED (2026-11-02).**
**Reference:** `annieetang/coda_backend@a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`.
**Product input:** Standard MIDI files only. MusicXML is generated internally for
engraving; source MusicXML, authored rests, editorial ties and graphical
annotations do not exist in an imported MIDI event stream.

## Complete algorithm scope

The application's `coda-midi` strategy operates on a whole MIDI piece by
default or on a caller-selected complete-measure excerpt. The upstream author
accepts an excerpt; it does not select practice passages or define a lesson
progression. The application supplies its own explicit order.

All **six source-defined categories** are implemented:

1. Score Level — full source excerpt, both hands, unchanged.
2. Part Level — original parts/hands.
3. Voice Level: Original — each independently identified MIDI track/channel voice.
4. Voice Level: Dotted — both 3:1 and 1:3 patterns.
5. Voice Level: Chordified — **every** width from the original formula
   `{q, 2q, q//2, denominator, 2*denominator, denominator//2,
   numerator*denominator}`, including the invalid zero-width request.
6. Voice Level: Slowed Down — both factors 2 and 4. For MIDI playback these
   are equivalent BPM÷2 and BPM÷4 maps without inventing written note lengths.

All categories are independently enumerated per source voice; a request
which produces no safe change is retained as `unchanged`, `author-invalid`
or `unrepresentable` with its reason. All generated live stages preserve
source IDs, original note counts, exact PPQ tick provenance and original
selected measure boundaries. Dotted and chord operations are performed
on sparse source-attacks, not three enormous 128-pitch dense matrices.
The author-defined rhythmic grouping is reproduced across barlines and
silent gaps wherever it is musically representable. Unsafe chord grouping
and independently sustained source tones are protected.

## Original algorithm differential — COMPLETE defined corpus

The independent comparator executes the **actual unmodified pinned Coda
exercise methods** with equivalent MIDI-derived matrices. It compares
canonical sounding pitch, onset and note-off, with slowdown normalized to
the same performed seconds. No equality of synthesized MusicXML text is
required.

Coverage is **all 16 supported SMF fixtures as complete source excerpts**
plus **all 17 bundled genuine MIDI repertoire pieces** at **three safe
short excerpts each** (beginning, middle and ending positions). The pinned
original's dense matrix is incapable of processing the 17 long whole pieces;
the product's sparse algorithm and full-length lesson plan are verified
separately. The comparison is intentionally explicit about this reference
memory limitation, rather than silently treating excerpts as a full
original-backend run.

| Author/backend outcome | Requests |
|---|---:|
| Exact MIDI match | 184 |
| Match within 0.000002 quarter-beat export rounding | 53 |
| Original Coda malformed/unsafe sounding output | 410 |
| Original Coda returned `None` | 615 |
| Original Coda error on known invalid zero chord width | 11 |
| **Unexplained valid musical differences** | **0** |
| **Total requests** | **1,273** |

**All 67 input cases** (16 fixture excerpts plus 51 independently labelled
repertoire excerpts) completed without source rejection. The author-invalid
records contain counterexample source/author/native events, including
original note-on loss, simultaneous note-off shortening/extension,
invalid tied fragments and chords beyond the playable five-note policy.
Those defects are not copied into the live MIDI grader. Missing/invalid
author exercises are not counted as matches. All 12 repertoire jobs and
the separate 16-fixture pinned backend job passed strict gate checks.

- [17-piece / 51-excerpt original Coda comparison, 12 of 12 jobs successful](https://github.com/tpepels/piano_teacher/actions/runs/41485239072)
- [16 source MIDI fixtures versus pinned author](https://github.com/tpepels/piano_teacher/actions/runs/41485239252)
- [Exact per-request comparison script](../scripts/probe_coda_midi_author_algorithms.py)

## Full-piece product integration

- **Every one of the 17 bundled complete MIDI pieces** generates a native
  `LearningPlan` with source identities and terminal original-score practice.
  The dense author matrix size limit no longer blocks those pieces.
- Production exercise catalog and reference-guided timing/matrix contracts:
  [235 passed, 1 skipped, then 51 complete sparse/full-piece tests passed](https://github.com/tpepels/piano_teacher/actions/runs/41485698315).
- Actual `LearningPlan`-generated dotted and chord rhythm stages, plus x2/x4
  slowdown, were checked through Verovio SVG, internal MusicXML, Listen WAV
  and software MIDI grading: [41 passed](https://github.com/tpepels/piano_teacher/actions/runs/41485698379).
- Normal fast application suite: [successful](https://github.com/tpepels/piano_teacher/actions/runs/41485698339).
- MIDI-Coda course identity is now **version 6**, preventing old v5 Coda
  mastery from transferring to newly retimed exercise stages.

## Scope boundaries

The original backend is not defined for arbitrary repeated overlapping
same-pitch attacks in one binary voice, nor is its generated output safe
when an independent MIDI chord has unequal note durations. Such invalid
reference requests must be reported and cannot silently masquerade as
successful parity; original note identities remain valid in the product.
Neither a physics-based keyboard check nor a controlled human learning
study is part of Phase 3's algorithm-reproduction acceptance.

**Phase 3 algorithm implementation and the agreed MIDI-domain verification
gate are complete.** Pedagogical effectiveness remains a distinct,
open Phase 7 acceptance criterion requiring actual consenting learners.
