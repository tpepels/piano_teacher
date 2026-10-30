# Native framebuffer sample: exact-revision visual evidence

This is an **explicit, small** real-rendering job, distinct from semantic
coverage and from the 24-shard corpus audit. It runs via
`.github/workflows/native-framebuffer-sample.yml`, initially on that
workflow's creation and subsequently via GitHub Actions **Run workflow**.
The single job has a **six-minute maximum**, with an independent 155-second
pytest deadline. It renders actual production native Godot frames under Xvfb.

Five selected test cases, with concrete immutable source and actual Godot
captures: a new unforced three-voice stem/adjacent-head specimen; a causal
erasure mutation of its first voice; a genuine Bill Evans *Autumn Leaves*
bars 37-40 flagged-tie passage (eight independently owned tie connections);
and two real-source-derived overlapping-slur + tie variants. A source
fixture plus original Verovio SVG establishes the written score. The
independent Python pixel checks own the final verdict. An `xfail` on
overlapping RH curves is **unverified**, not a verified visual pass.

The evidence upload includes the tested SHA, JUnit, test log, original and
generated MusicXML, actual native frame PNGs, raw verification JSON, and
relevant original reference SVGs retained in the pytest temp directory.
Absent captures are not counted as checked. CI does not quietly substitute
old screenshots or historical result counts. Failure of any mandatory
non-xfail case fails the workflow.

This sample **does not establish complete current-corpus coverage**:
in particular rest corridors/dots, dense Liszt heads, printed accidentals,
unusual rhythm groups, and all other unselected measures are unverified.
The existing Phase 3/4 denominators and release decision remain authoritative.

To run again, use the workflow's manual dispatch. Do **not** run 24 shards in
normal push CI. After checking the retained JUnit and JSON, address every
real mismatch in a focused source-specific change, retaining corrupted-image
controls and source identities.

## Current revision sample result (2026-10-30)

The first complete sample at `c345a3f2` ran actual Godot rendering and
independent source pixel checks: **2 passed, 1 failed, 2 xfailed**. The
three-voice test confirmed **three distinct verified physical stems** but the
pitch-only oracle did not verify all three head contours. Actual PNG shows
three distinct noteheads spread across approximately 90 pixels; the old
source-pitch verifier searched only ±16 pixels around the fixed playhead.
Both source-derived crossing slur variants remain explicitly unverified or
mismatched, while the real Autumn flagged ties passed. The original artifact
is preserved in GitHub Actions run `41135285306`; no old counts are reused.

The follow-up bounds horizontal search using the number of adjacent written
voice groups and the independently photographed staff gap. It does **not**
relax contour Dice, family discrimination, staff-position, pixel exclusivity,
or mismatch/unsupported accounting. A real erased-head mutation is also
included in the next sample. The current revision must be re-captured to
claim any new coverage.

## Fresh independent run: 30 October 2026

- Tested source revision: `39770ccd6760b33c4eded52b89962b78029a92a3`.
- GitHub Actions run: https://github.com/tpepels/piano_teacher/actions/runs/41135723434
- Source-bound PNGs, original/generated scores, actual Verovio SVGs,
  JUnit, and independent pixel reports: artifact `13016956247`.
- Exact selected result: **4 passed, 2 xfailed, 0 failed** (29.98 s).
  `xfail` is an **unverified/mismatched** source connector case, **not**
  a pixel-verified score or a release pass.
- Three-voice adjacent C5/D5/E5 specimen: **3/3 independently registered
  heads**, **3/3 physical stems**, three distinct shaft owners. The
  established erased-head and erased-shaft controls **both passed**.
  Prior `c345a3f2` showed those stems but failed head verification because
  the source-pitch oracle's central horizontal search missed voice columns
  outside its ±16-pixel interval. The revised oracle widens the *candidate
  location* only for source-confirmed three-or-more crowded voices. Pixel
  ownership, contour quality, pitch and staff tolerances are unchanged.
- Real Bill Evans *Autumn Leaves*, bars 37–40, standard viewport:
  **8/8 tie connections independently verified** against actual Godot
  frames, including the two formerly flag-obstructed chord ties.
- Two source-derived overlapping RH-slur/LH-tie cases: each **2/4
  connector obligations verified**; default has **2 mismatches**,
  separated has **1 mismatch and 1 unverified**. Both retain an
  expected-failure test result; the case is **not accepted** for release.
- The current release decision still blocks unsupported and unverified
  whole-score notation. No claim about the full MIDI/MusicXML corpus,
  REST clearance or dense Liszt passages follows from this sample.

Machine-readable provenance and per-construct counts are in
`docs/evidence/native-framebuffer-2026-10-30/summary.json`. All sample
capture bytes and complete reports are in the GitHub Actions artifact.

## Superseding current-revision source pixel evidence: `701f2844`

The default and separated overlapping RH slurs now have source-bound causal
proof using stable, unmodified and singly-suppressed **production Godot
framebuffers**. The previous `2/4` slur-and-tie connector results were the
uncorrected full-frame oracle's ambiguity; this is now resolved for these
specimens by demanding an independently registered source-pair head/stem
attachment, an authentic curved stroke, at least 24 source-exclusive changed
pixels, and stable repeat/restoration images. No global contour threshold
was relaxed; an absent, unchanged, or drifting control is not accepted.

- Run: https://github.com/tpepels/piano_teacher/actions/runs/41137661038
- Revision: `701f28447fa827059d724039959799dc6bb636ce`.
- Result: **14 passed, 0 xfail, 0 failed**, 40.63s focused test execution.
- Artifact: `13016074993` (original source and generated XML,
  actual Verovio references, native and suppressed/restored PNGs,
  independent pixel reports and negative controls).
- Scope includes 3 source slurs and 1 tie per overlap variant, an actual
  Bill Evans flagged-tie passage and the three-voice notehead/stem
  specimen. The mutated suppression controls fail closed.

The source-derived crossing-slur fixture deliberately adds authored
slur marks to a retained test score. These counts **must not** be promoted
to full real-score or full-corpus coverage. This run also recaptured the
samples after moving the playhead beneath score ink; earlier frame
evidence stays historical. See `docs/native-real-score-sample.md` for
separately captured genuine MIDI performances and denominators.
