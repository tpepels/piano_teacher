# Real-score notation pixel sample — 30 October 2026

Exactly two original source MIDI scores, no corpus sweep or simulated
success. The source-bound generated MusicXML establishes printed events;
**actual Godot framebuffer PNGs** supply staff, notehead and rest ink.

- Tested revision: `701f28447fa827059d724039959799dc6bb636ce`.
- Native rendering: Godot **4.5.1** on GitHub Linux, Xvfb/software OpenGL.
  The user's local Godot 4.7.2 build is **not** covered by this CI.
- Focused run: https://github.com/tpepels/piano_teacher/actions/runs/41137661023
- Full artifact (source/generated XML, PNGs, controls, per-element JSON,
  mutated images and rejection reports, JUnit): `13016718888`.
- Result: **2 passed**, 15.21s, with two source-specific corruption
  controls rejecting the fabricated evidence.

## Peace Piece — measures 1–2

Source: Bill Evans `Peace_Piece_-_Bill_Evans_(Piano_Solo).midi`.
The imported score has exactly **one** written rest in these measures:
one eighth rest at source beat 0. The actual frame initially covered that
tiny contour with the foreground fixed playhead, yielding a genuine
`unverified` 0.556 contour score. The native renderer now paints the
playhead **behind** source notation, preserving noteheads and rest ink.
The independent actual-frame subtraction verifies **1/1** eighth-rest
identity, font silhouette, visible source ink and staff-grid placement.

Control: replacing the suppressed-rest image with an unchanged baseline
causes **1/1 to become unverified**. No threshold change authorizes it.

## Chopin Nocturne Op. 9 No. 2 — measures 5–6

Source: the bundled genuine MIDI performance of the Nocturne. The
generated selected score has **77** visible written noteheads. The test
selects the two most populous source onsets (beats 1.0 and 5.5), totaling
**8** written noteheads, and captures real Godot frames at both onsets.

Dense beam/ledger ink made the prior single-frame staff detector fail on
a missing common exposed rail core. The verifier now optionally constructs
a conservative, **pixelwise minimum of the two real frames**. This
cannot fabricate a line absent in either image; it removes foreground ink
which moves between captures. The same original strict independent
five-line staff detector, pitch tolerance, authentic glyph family/Dice
thresholds and exclusive notehead assignment remain mandatory.

Result: **8/8** sampled source noteheads independently matched, with
individual contour scores 0.880–0.949. The other **69** noteheads were
not captured and remain unverified. The independent negative control
erases one photographed staff rail in one original frame. The combined
reference then fails the unchanged staff proof, and **8/8 become
unverified** as required.

## Release decision

These are fixed *samples*, not evidence that the entire music corpus is
correct. Other original sources, all unsampled measures, rare multi-voice
connector configurations, unsupported constructs, dense Liszt
learn-0065, and the actual Godot 4.7.2 environment remain unresolved.
The repository's full coverage denominator must retain these exclusions.
