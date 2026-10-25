# Canonical audit recovery and native fingering placement

The production Lumikey provider, whole-piece plans, manual overrides and lesson
progression are unchanged. This change repairs diagnostic publication, makes
the canonical capture boundary explicit, and replaces remote hand lanes with
local fingering layout in the existing native compositor.

## Runner findings

The retained shard reached a recorded **630/632 cases**, **19/21 sources** and
270/270 measures. It recorded 301 failed-case entries before the final packaging
import raised `ModuleNotFoundError: scripts`. Direct execution puts `scripts/`
on Python's import path; importing it again as a top-level package was invalid.
Both ordinary failure packaging and previous-interruption recovery now use an
import that works with direct-file and module execution.

At the start of this investigation the checked-out Bash wrapper matched HEAD
`04da92b` and passed `bash -n`. Its recorded modification time fell inside the
earlier sweep. Editing a running copy reproduced the reported `break`/`fi`
errors: Bash can read a changed file in the middle of a top-level loop. This is
consistent with the historical failure, but the exact historical file bytes
are unavailable; it is not evidence of an OOM kill. The wrapper now parses its
complete `main` function before starting work and exits inside that function.

Standalone coordination packages its failures; the outer Bash wrapper requests
`--no-package-diagnostics` and publishes once after its log writer flushes.
Failure statuses survive packaging errors. SIGINT/SIGTERM during archive
publication are recorded and deferred until the atomic ZIP is complete; later
signals do not replace the first signal's exit status. Recovery publication is
protected too. When called by Bash the packager reports publication success
separately from the signal status owned by the outer driver, preventing a
completed ZIP from being mislabeled as failed after different signals.
Checkpointing, exclusive writer ownership, capture provenance,
resume/reuse, two-worker defaults, memory ceilings and deadlines remain active.

The regression tests exercise actual direct/module Python invocations with a
genuinely invalid MIDI file, unexpected coordinator failure, recovery of a prior
checkpoint, the actual outer Bash wrapper, failed packaging, mid-run edits and
signals during both work and packaging. They do not launch a corpus audit.

## Canonical music versus instructional annotations

Canonical capture requires this explicit configuration:

```json
{"version":1,"score_ink":"canonical","fingering_annotations":false,"transport_overlay":true}
```

The native view's public annotation switch disables fingering paint and hidden
editor targets. It does not change musical events, layout, source identities,
tuplets, time signatures or any music recognition threshold. The configuration
is part of fixture, asset-cache, verification/checkpoint and capture-manifest
identity; incompatible old captures cannot silently count as a new result.

The canonical reference removes only MusicXML `technical/fingering` elements
and unidentified containers emptied by that removal. All remaining bytes,
namespaces, IDs, comments, musical numbers and other technical marks survive.
The original imported piece and its Note objects are preserved.

Dedicated fingering captures take real normal and annotation-free frames with
transport decoration explicitly disabled in their own capture configuration.
Their pixel difference isolates the instructional layer. An independent atlas
of all five digits checks the actual glyph against the source assignment with
the existing **IoU > .80 and alternative margin > .12**. Full reference-glyph
pixels require two-pixel clearance from bright canonical music. The reference
viewport now uses the real stage background, correcting an antialiasing
calibration error without changing thresholds. Canonical auditing uses no
digit mask or general ink exemption.
Separate punctuation-on/off captures check clearance from dim barline/repeat
ink too; that strict intervention belongs only to annotation collision tests.

Positive captures are byte-identical in canonical mode when fingerings change
or disappear. Deliberately erased/wrong/detached digits fail the annotation
oracle; removed music and authentic added note ink near label positions still
fail the independent music oracle.

## Placement and visual evidence

Numbers start close to their own heads, with right/left-hand preferences,
polyphonic stem context, chord-tone side columns, and meaningful authored
placement hints. Local alternatives stay within 2.45 staff spaces of their
source head and two spaces horizontally. If preferred placements fail, a finer local search stays within
the same bounds; this recovers four Evans digits at 1216×455 without increasing
distance or reducing clearance. The fixed font-metric envelope spans
all five digits, so a correction does not move unrelated labels. Scrolling and
practice loops translate this cached layout without reflow; tempo does not
change assignments or placement.
Viewport edges reveal only whole annotation cells, avoiding partial numerals
that could resemble a different finger; this culling never reflows the score.

Collision bounds distinguish heads, actual shafts, individual ledger lines,
flags, dots and source connectors from the empty space inside their combined
rectangle. Flag/shaft envelopes come from nontransparent authentic sprite
pixels after separately reserving heads; no guessed flag-side cutoff is used.
Source barline strokes/repeat dots and chord-specific dot anchors are included.
Assignment IDs remain authoritative, shared physical keys retain independently
editable source identities, and tied continuations do not invent assignments.

MusicXML presentation attributes are projected separately from the saved plan.
They follow the source tie ownership and do not trigger inference or override
writes. See the [MusicXML fingering definition](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/fingering/)
and [engraved fingering placement guidance](https://lilypond.org/doc/v2.24/Documentation/notation/inside-the-staff#fingering-instructions).

Before evidence uses the actual native view from `04da92b` with the same real
model, assets, camera and viewport as the after evidence. Both evidence frames
include transport decoration. The canonical comparison frame is a separately
captured annotation-free frame.

| Passage | Before | After |
| --- | --- | --- |
| Hanon ascending, measures 7–8 | [remote lanes](evidence/fingering-placement-2026-10-25/hanon-before.png) | [local numbers](evidence/fingering-placement-2026-10-25/hanon-after.png) |
| Chopin, measures 5–6 | [remote lanes](evidence/fingering-placement-2026-10-25/chopin-before.png) | [local numbers](evidence/fingering-placement-2026-10-25/chopin-after.png) |
| Peace Piece, measures 3–4 | [remote lanes](evidence/fingering-placement-2026-10-25/evans-before.png) | [chord/voice attachment](evidence/fingering-placement-2026-10-25/evans-after.png) |

Also retained: [Hanon canonical frame](evidence/fingering-placement-2026-10-25/hanon-canonical.png),
[simplified step](evidence/fingering-placement-2026-10-25/hanon-skeleton.png) and
[corresponding original](evidence/fingering-placement-2026-10-25/hanon-original.png).

Real framebuffer regressions also cover Hanon low and descending passages,
simplified versus original Hanon (2 versus 8 attacks using the same whole-piece
plan), shared keys, both hands, corrections, ties, beams and variable
staff size. Hanon source attachment additionally uses independently read source
pitches/IDs, photographed rails, external head contours and measured image
motion; renderer head coordinates/density are not inputs to that check.
The Chopin MIDI represents ornamental flourishes as short written notes rather
than authored ornament/grace tags. A separate measure-22 capture checks that
rapid figure alongside the broader register changes in measures 5–6.

When a minimum legible number cannot fit locally, the renderer records its
source ID and reason. The application shows a space warning alongside unknown,
review or provider status, with guidance to enlarge the practice window.
Assignments are retained, rather than silently lost or moved to a remote lane.
The finite local search is greedy, so a reported failure is not a mathematical
proof that no continuous placement exists. It remains an explicit issue to
inspect, rather than a claimed successful annotation.
The existing Peace Piece plan still has 350 unknown assignments due to its
overlapping-key constraints; placement does not manufacture replacements.

## Retained failures and scope

The old shard's **634 fixtures contain 10,442 events and zero fingering
assignments**; its source references likewise contain no authored fingering.
Its failures therefore cannot be attributed to instructional numbers.
Existing captures and successful checkpoints have been preserved.

Reported musical mismatches remain in the retained evidence, including ties
(for example Autumn Leaves), ledger lines, rest placement and a few flag or
accidental mismatches. Boundary translation, source-clock ownership, ambiguous
contours, and unsupported tuplets/rhythms are verification limitations, not
automatically confirmed engraving defects. Two captures were also invalidated
by renderer dependencies changing during capture. This work does not relabel
those failures or claim a clean corpus. No full shard sweep was run.

## Validation

The fast CI command passed **322 tests, with 4 intentionally inapplicable
fixture combinations skipped**, followed by the Godot parse check. The focused
runner failure-path suite passed 68 tests. Focused framebuffer suites verify
the original failure, corrected output and deliberately regressed reservations;
the resized Evans case now has 36 visible assignments and no placement issues.
`bash -n scripts/verify-notation.sh` and `git diff --check` also passed.
After the final horizontal authored-hint check, the affected placement,
application correction and metadata suites passed **22 tests, 4 skipped**.

The real application was inspected through Godot MCP for Hanon, Chopin and
Peace Piece, including normal/canonical mode. Only a temporary backend data
directory was used. The user's XDG override hashes are unchanged. Historical
archive branches and the preservation bundle remain intact.

Recommended next local verification (fast checks only):

```bash
rtk proxy env LIBGL_ALWAYS_SOFTWARE=1 OPENBLAS_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1600x1000x24' bash scripts/verify-notation.sh --ci
```
