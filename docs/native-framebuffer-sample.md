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
