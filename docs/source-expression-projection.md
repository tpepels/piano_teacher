# Imported MusicXML expressions in practice lessons

The imported original XML is always retained unchanged. Derived curriculum
scores preserve only the markings whose **source-note identities and staff
membership** survive the selected exercise.

- Articulations, ornaments, technical instructions, lyrics and independent
  notations are attached to the **first generated segment** of their original
  source attack; tied continuations do not repeat the markings.
- Slurs are retained only when both original source endpoints survive in
  the same generated hand. Orphan or half-visible slurs are not invented.
- Staff-specific directions, including dynamics and pedal instructions, are
  routed to the appropriate generated grand-staff hand. They use MusicXML
  offsets and cannot advance the exercise timing cursor. Ambiguous unstaffed
  directions in a source with multiple active hands are deliberately omitted.
- Original source `<tie>` and tuplets are **not** blindly copied: the lesson
  compiler must respell durations in simplified variants with its own exact
  rhythmic semantics.
- Native Godot can reproduce the source slurs with authentic Verovio fragments.
  Other expressive classes are not currently natively drawn; if present,
  the compositor explicitly selects the **complete Verovio-page engraving**
  rather than silently presenting a score without expression. This is a
  compatibility step, not native expression coverage.

The preservation pass does **not** yet reproduce ornaments occurring only
on source tied continuations, expressive directions without an unambiguous
source staff, or missing slur endpoints in a filtered lesson. Future work
should emit authentic Verovio-derived fragments for dynamics, pedals and
articulations in native mode and expand the source-identity mapping for
continuations.

Regression suite: `tests/test_source_expression_projection.py`.
