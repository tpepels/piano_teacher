# Coda Gate 2 — expanded-source and original automatic-chord diagnostic (2026-11-01)

**Research-only. Not production Coda parity.**

## Reproducible source comparison

- Pinned author: `annieetang/coda_backend@a4eb85dfc2bd418818ca9ff775c0a11ccccb3530`, unchanged apart from the unused database initializer.
- [Successful bounded original-backend workflow](https://github.com/tpepels/piano_teacher/actions/runs/41347316618) on `2a343ca773076cb3e5366dd85dce1f5c7aa4f9dc`; retained artifact `13099996436` with `extended-source-voices.json`, `real-source-voices.json`, and `supported-subset.json`.
- Added `piano_teacher/research/coda_extended_sources.py`, `coda_auto_chord_levels.py`, `coda_native_written.py` and `scripts/probe_coda_upstream_extended.py`. Research-only, deterministic, no production lesson family enabled.
- Run the explicit `.github/workflows/coda-upstream-parity.yml` workflow to regenerate evidence. The standard 24-case strict parity certificate is **independently preserved**, rather than expanding its eligible subset on a diagnostic observation.

Coda's actual automatic chord-width set is:

```python
{q, 2*q, q//2, denominator, 2*denominator,
 denominator//2, numerator*denominator}
```

The independent adapter enumerates that **entire set**, deterministic ascending order. It retains an invalid zero width when it occurs, reporting the original backend error rather than silently filtering it. Quantization follows the original shortest **written note/rest** in the excerpt and its first time signature; no undocumented replacement grid is selected.

## Ten additional source excerpts

| Excerpt | Result | Quantization / limitation |
|---|---|---|
| Chord ties | Source parsed; native/reference MMR not exact | q=4, no parity case promoted |
| Grand-staff independent voices | 2 exact source-voice MMRs | q=4 |
| Quintuplets | Source parsed; native/reference MMR not exact | q=20; rhythmic disagreement retained |
| Trailing written rests | 1 exact source-voice MMR | q=4 |
| Mixed 3/4-to-4/4 meter | 1 exact source-voice MMR | q=3 |
| Sixteenth-note beamed passage | 2 exact source-voice MMRs | q=16; some protected rhythm differences |
| 5:4 authored tuplet | Adapter source-grid rejection | q=12; onsets not exactly expressible |
| 7:4 authored tuplet | Adapter source-grid rejection | q=16; onsets not exactly expressible |
| Autumn Leaves excerpt (authored measures 37–38) | Adapter source-grid rejection | q=76; onsets not exactly expressible |
| Danny Boy excerpt (measures 1–2) | 2 exact source-voice MMRs | q=8; one original output invalid tie |

**Coverage:** 10 source excerpts; 7 processed through the full differential; 3 explicitly rejected before algorithm comparison for off-grid source timing. Ten reference voices were attempted in processable excerpts, **8 exactly matched source MMRs**; two remain genuine source-MMR mismatches. Rejected excerpts and unmatched voices have no parity success assigned.

## Original automatic chordification: all widths and outcomes

Across matched source voices, the original backend was asked for every automatically selected chordification width: **37 generated width-level requests**.

| Original/backend vs independent adapter | Count |
|---|---:|
| Actual transformation, exact bare written and sounding match | 3 |
| Different generated output | 2 |
| Original author returns no exercise | 32 |
| **Total** | **37** |

These three observed matches are **not automatically added** to the older 24-case strict certificate. They need separately reviewed per-voice source identity, notation/style and graded exercise coverage before that subset can be expanded.

The entire ten-excerpt expanded diagnostic generated 69 exercise cases (37 auto chords and 32 slowdown/dotted cases). The complete status breakdown is **16 observed changing strict matches, 6 exact unchanged outputs, 10 sounding-only matches, 4 different sounding outputs, 1 original invalid-tie output and 32 original None results**. These are unapproved *diagnostics*, not 69 new certified exercises.

The original backend has severe yield limitations for these source excerpts: 32/37 automatic chord-width requests returned no output. Do not treat that as either a working exercise or a regression against the native adapter.

## Bounded real notation → Listen → MIDI-grading verification

[Real pipeline run 41347147004](https://github.com/tpepels/piano_teacher/actions/runs/41347147004): **22 tests passed in 2.02 seconds** (after dependency setup). This includes two new independent full-score MusicXML exercises:

- `tests/fixtures/musical_fidelity/xml_mixed_meter.musicxml`: authored meter transition retained in x2 written slowdown.
- `tests/fixtures/musical_fidelity/xml_trailing_rests.musicxml`: original trailing written rests retained through x2 transformation.

`tests/test_coda_wider_pipeline.py` uses actual `project_coda_score`,
`ScoreArtifacts.engraving` (real Verovio SVG and attack map), `DemoAudioCache`
(real WAV samples), `ListenSession`, `stage.grade` (clean synthetic MIDI
onset/off timing), and `LiveInputView` onset feedback. It verifies original
source immutability and that rendered attack IDs match the graded score.
Previous Coda source-tie, beam, and 3:2/5:4/7:4 tuplet SVG tests remain in the
same bounded workflow.

**Limitations:** This is the software pipeline for selected Coda exercises.
Physical MIDI keyboards, native Godot framebuffer timing, original Coda
annotation/style equivalence, full Score/Part/Voice output inventory,
and measured teaching gains remain unverified.

## Research status

**Gate 2 remains open.** The baseline certified subset is unchanged:
24 exact *source-changing* written-and-sounding cases in the original six-score
manifest. New source-repertoire and automatic width results are diagnostic
only, with explicit off-grid and mismatch cases; no algorithm was altered to
mimic unsafe original backend behavior.

Next research work: independently resolve the two new source MMR mismatches;
check original backend rejections at all generated chord widths and identify
which are algorithmic restrictions versus invalid source/grid states;
broaden author-output parity using genuinely independent scores; and then
verify complete authored slurs/beams/directions, actual Godot and physical
MIDI on eligible transformed stages.
