# Native notation baseline — 21 October 2026

This is the **current post-refactor audit**, following source reorganisation
(PR #15), rest/voice engraving (PR #16), and the focused two-measure
curriculum (PR #17). It supersedes the stage-count baseline from
[20 October](native-notation-verification-2026-10-20.md).

## Reproduced result

[Seven-shard exhaustive audit](https://github.com/tpepels/piano_teacher/actions/runs/39604211440)
on [PR #18](https://github.com/tpepels/piano_teacher/pull/18), plus the
[regular integration suite](https://github.com/tpepels/piano_teacher/actions/runs/39604211449),
both passed. The audit ran on commit `ff669c024`, subsequently merged as
`16b9776e0` into `main`.

| Source MIDI | Native curriculum stages | Expected/painted noteheads | Max px/beat |
| --- | ---: | ---: | ---: |
| Ala — Joep Beving | 213 | 3,654 / 3,654 | 526.4 |
| Autumn Leaves — Bill Evans | 206 | 3,596 / 3,596 | 868.1 |
| Chopin, Nocturne Op. 9 No. 2 | 122 | 7,253 / 7,253 | 7,017.6 |
| Danny Boy — Bill Evans | 63 | 1,885 / 1,885 | 454.1 |
| Merry-Go-Round of Life | 756 | 14,002 / 14,002 | 1,571.3 |
| Peace Piece — Bill Evans | 311 | 12,251 / 12,251 | 7,943.1 |
| Waltz for Debby | 252 | 4,343 / 4,343 | 450.9 |
| **Total** | **1,923** | **46,984 / 46,984** | |

**Zero failures, zero raster fallbacks, zero missing note IDs, and linear,
unchanged beat spacing in every stage.**

The new stage total differs from the previous 1,041 because the curriculum
now creates source-grid two-measure focus stages and bridges. This is not an
independent claim that the score contains more distinct musical notes:
the audit counts each visible notation event across all exercise variants.

## Regression discovered and repaired

The first post-refactor audit exposed **13 Chopin stages** with
`Automatic score density must be between 24 and 8192`. The rest-collision
and notehead ink bounds needed a scale above the old single 17 px staff-gap
fallback. The native compositor now chooses the widest readable staff gap
from a fixed bounded set (22, 17, 14, 11, 8.5 px), recalculates authentic
glyph collisions and chooses **one fixed horizontal density for the entire
stage**. It never clips required spacing or shifts MIDI onset times. If no
supported gap fits, native rendering still declines explicitly rather than
silently placing overlapping glyphs. All 13 previously failing stages passed
in the second audit.

## Reproduction and limitations

From an environment with Godot 4, the repository's MIDI examples and the
installed app dependencies:

```sh
PIANO_TEACHER_NATIVE_NOTATION=1 \
.venv/bin/python scripts/check_native_notation.py \
  --compact --output /tmp/piano-native-audit
```

For a file-specific audit add `--only Chopin`, etc. JSON summary and detailed
failure evidence are written to the output folder; the GitHub workflow uploads
per-source run artifacts. The GitHub Action can also be launched manually.

This verifies actual native notehead coverage and timeline linearity at
synthetic rendering poses. It **does not** replace visual readability checks
for extremely dense passages, a physical MIDI keyboard latency check, or
a future MusicXML annotation-preservation audit.
