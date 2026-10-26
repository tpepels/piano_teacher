# Continuous repetitions and visible preparation

These are real Godot framebuffer captures of the production native view. The
fixture harness loads the normal semantic score and authenticated Verovio
assets; it does not render a second score or stitch raster strips. The after
images include the transport playhead inside the engraved rest measure.

| Source | Before | Corrected rest | Corrected opening |
| --- | --- | --- | --- |
| Ala, m30, left hand | [before](ala30-before.png) | [after](ala30-after-rest.png) | [opening](ala30-after-opening.png) |
| Ala, m32, both hands | [before](ala32-before.png) | [after](ala32-after-rest.png) | [opening](ala32-after-opening.png) |

Additional captures: [Ala m29–32](ala29-32-after-rest.png),
[real clef/key/meter transitions](context-after-rest.png), and
[existing source rests](source-rests-after-rest.png).
[Full production app through Godot MCP](mcp-live-ala30-rest.png) shows the actual
Ala m30 left-hand skeleton preview paused inside its preparation measure.
Its backend ran with isolated temporary XDG data; [live state](mcp-live-state.json)
records the unchanged revision and shared timeline. The full original-note
captures above separately verify the unsimplified passage.
Recovery evidence includes [a change at silence start](recovery-suppressed-context.png),
[an overlapping earlier gap](recovery-regular-gap-overlap.png), and
[earlier-pass notes inside a later preparation](recovery-previous-pass-overlap.png).
[Recovery contracts](recovery-contracts.json) record their absolute intervals.
[Capture contracts and source-bound click requests](capture-contracts.json)
retain the timing and interaction evidence without committing large asset payloads.

## Root causes and correction

Each `_paint_source_pass()` previously reset its musical context and cleared
the shared notehead map. Consequently each copy reprinted opening symbols and
painting a later copy erased earlier interaction geometry. The native draw
loop and backend also inferred the silent interval independently from the final
bar, and that interval had no semantic rest. Backend feedback could extend the
pause beyond its musical length; partial previews could retain an extra source
offset.

`notation/practice_timeline.py` now defines the preparation measure separately
from source events, using the upcoming context's full nominal meter. A pickup
or shortened final bar keeps its real source duration. Required context
restoration is engraved at preparation start. The backend and native view use
the same duration and stride, with exact restart deadlines and no second
count-in. Failed and manual retries retain reverse movement, then traverse an
explicit preparation measure before their adaptive source target. Pause/resume
shifts the scheduling clocks without moving the visible position.

Recovery masks use absolute practice intervals across every visible pass.
Overlapping earlier gaps are replaced, and the outgoing context is selected
strictly before the replaced interval, preserving a real change at its start.
This also keeps source connectors and volta brackets out of preparation silence.
Perform-mode Retry retains its ordinary count-in. MIDI arriving at a due
handoff advances that handoff before live feedback and recording, without
waiting for the next HTTP state poll or moving the scheduled deadline.

The existing native compositor draws authentic hanging whole-measure rests on
both staves, including inactive-hand styling, centered between full-grandstaff
boundaries. Context changes reserve space for cancellation naturals as well as
incoming signature marks, so a restored clef cannot overlap the cancellation.
Local notehead maps support attachments within each pass; separate source/pass
instances preserve every visible click target. Repeated fingering corrections
resolve to the same original source identity and reuse the whole-piece plan.

The canonical annotation-free source path remains unchanged: derived practice
events do not enter source notes, source notation events, MIDI assessment or the
Verovio/source audit.

## Verification

The focused framebuffer suite checks Ala m30 LH, m32 both, m29–32, genuine
context changes and existing rests. Its independent oracle reads source XML,
external Verovio font resources and detected image rails/barlines, rather than
renderer-reported glyph geometry. Deliberately corrupted images remove rests
or boundaries, insert an authentic unwanted clef, move the repeated source or
change the visible pause length; all must be rejected. The original Ala capture
also fails the new regression.

Actual backend preview, clean-repeat, failed-take, local-recovery and manual
Retry snapshots drive a second framebuffer suite. It checks the rests, fixed
pixel velocity and exact framebuffer preservation through pause/resume.
Backend tests cover changing meters, pickups, partial attempts, late polls,
short rests, unchanged score revisions and preserved mastery rules.
Focused results: 95 forward/transport framebuffer checks passed; the three
additional recovery cases and their corruptions passed 10 checks with two
conditional skips; 151 backend lifecycle/grading checks, 18 barline checks and
three camera/fallback checks passed.
The final expanded fast CI gate passed **494 tests**, with **six conditional
skips**, followed by successful Godot script validation. [Full gate output](fast-ci.log)
and the focused `*.log` files in this directory retain the observed results.

One optional combination remains unverified in framebuffer pixels: recovery
overlapping a source volta. Its synthetic MusicXML fixture was rejected before
capture (`Dangling ending tag skipped`, followed by an incorrect source display
onset). The native ending filter uses the same absolute interval rule, but this
task does not claim independent pixel proof for that combination. Ordinary
source barline/ending semantics pass their 18 focused regressions.

Run the bounded local verification gate:

```sh
rtk proxy env LIBGL_ALWAYS_SOFTWARE=1 OPENBLAS_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1600x1000x24' ./scripts/verify-notation.sh --ci
```

This task deliberately does not rerun the 24-shard corpus audit.
