Historical diagnosis before implementation. The final outgoing-only correction and its independent pixel checks are documented in the recovery report and boundary-pixel-proof.json. Incoming same-clock placement remains open.

# Boundary assessment (no implementation)

Retained shard-0-of-24/07-Le_Pianiste_virtuose_-_Première_partie_(1-20)_-_C_L_Hanon/original-0197-0200-both/native-8.00000.png shows both final 16th flags intersecting the terminal stroke. Source events pt4a2d2ea02bb20cac198b49d742375b6fs0 (C4) and ptb7c2b2d269b8752e6bee848e64a07a2ds0 (C3) are at beat 7.75; measure 200 ends at beat 8.0. Saved hanon-boundary-crop.png confirms the contact.

Root: view.gd _required_ink_density checks neighboring event ink rectangles only. BarlineLayout.project places each boundary at beat*density - 1.35*gap. Terminal boundaries have no following event against which the final flags can impose clearance.

Proposed algorithm: add boundary constraints during each staff-gap candidate evaluation, retaining the one global linear density and common lead. Enumerate actual source/preparation/terminal boundaries and their explicit stroke offsets, widths and vertical segments. Compare ordinary glyph contours (heads, shafts, flags, ledger, dots, accidentals, rests) only where they overlap those segments in Y; do not treat intentionally crossing tie/beam/slur ink as a forbidden collision. Let P be density, b the boundary beat, t event beat, L=1.35*gap, r/l the glyph ink edges relative to its event anchor, s_left/s_right the stroke extremes relative to its boundary anchor, c the engraving clearance:

- For t < b: P >= (r + c + L - s_left)/(b-t).
- For t > b: P >= (-L + s_right - l + c)/(t-b).
- Keep the maximum with configured P, leaving 96 unchanged when its actual contours already clear.

At t == b the relative position is independent of P. A courtesy accidental extending left into the stroke cannot be separated by a density change; it needs an explicit accidental/voice-column placement constraint, or another authorized layout change. This must fail explicitly rather than divide by zero, silently omit a source object, quantize its time, or relax the independent verifier. Repeat punctuation, multi-stroke endings and preparation transitions need their source-owned bounds included in tests.

This is a second rendering problem and remains unresolved by this one-defect tie change.
