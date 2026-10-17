# Regression recovery — 17 October 2026

Work is on `main`, starting at `3e4e32a`. Python's transport, MIDI assessment and progression rules are preserved. The timing code adds the timestamp of its existing clock sample to the state response. Engraving metadata separately declares whether temporal spacing is requested.

## Principal causes and repairs

| Cause | Origin | Repair |
|---|---|---|
| The parent score canvas moved at 60 FPS, but its locally drawn playhead repainted at 30 FPS. The cached line moved with its parent on intervening frames. | `65ba483` | Repaint the overlay whenever its parent projection changes. Stationary frames retain their cache. |
| HTTP phase-error filtering deliberately varied presentation tempo, up to 2%. | `89d1acd`, reduced in `d5a47ca` | Project backend musical time at its nominal BPM. Calibrate process clock epochs from the lowest-latency idle sample; use the backend sample timestamp for the first active response. Freeze this calibration during movement. |
| Proportional spacing silently stopped when a warped system exceeded 16,384 pixels. Small imported ornament/rest intervals triggered it. | `83e7a13` | Separate logical score width from physical texture width. Wide systems use native image regions and sparse transparent gaps with bounded residency. A connected tie/beam stays in one source texture. |
| The header-cropping safety flag also controlled temporal spacing. Keeping a genuine meter/key/clef change silently kept unequal spacing. | `ScoreStrip.build()` coupling | Temporal layout has its own metadata flag; preserving context never disables equal beat spacing. A real 3/4→4/4 regression reproduces the former 218–1,491 px/beat variation. |
| A vertically expanding lesson-list scroll container inside another scroll container received zero height. | `3e4e32a` | One scroll container owns the complete Path content and its lesson rows. |
| A score minimum of 48% of window height ignored hints and status text, pushing transport controls below the window. | `aef57fe` | The score expands into remaining space, with a 135-pixel floor. Compact windows omit the redundant three-hand status row. Typography stays readable. |
| Count-in painted another clef and meter before an already engraved opening header. | `7670eb5`, clef metadata added in `65ddda5` | Real practice scores retain the original Verovio header; preparation adds staff/rests only. Standalone preparation rendering remains supported. |
| Clean-pass decoration overwrote the backend's actionable next-step instruction. | `_on_state()` challenge presentation | Preserve a nonempty backend `next_action`. |
| Exit to library only navigated away from a paused attempt, leaving its transport active. | Pause-sheet exit callback | Send the existing backend Stop action before opening the library. |

`fe4ce1d` is a test-variable correction, not the original proportional renderer. The two/forty-measure motion tests passed at the starting checkout. They did not cover the rendered playhead between redraws or the imported wide-system fallback.

The existing Music drawer did not collapse in this checkout: its measured width at 1536×960 is 998.4 pixels. Its real controls, Path, Settings and starting-point panel are now checked after container layout settles, including navigation and scrolling to the last lesson at four resolutions.

## Evidence

Local artifacts are in `playtest-results/regression-recovery/evidence/` (intentionally excluded from Git alongside other playtest captures):

- `motion-before.mp4` and `motion-after.mp4`: 360 actual Godot frames each, 1536×960, four seconds each at 40, 80 and 120 BPM, with controlled polling bias. These are deterministic projection captures, not a live hardware-latency measurement.
- `motion-before.json`, `motion-after.json`, `motion-summary.json`: per-frame beat, canvas position and detected playhead pixel.
- `imported-motion-before.log`, `imported-motion-after.log`: whole-passage spacing checks on the actual imported MIDI; no source MIDI is included.
- `lesson-before.png`, `lesson-after.png`: identical populated Path fixture, before and after the zero-height list repair.
- `library-*.png`, `settings-*.png`, `picker-*.png`: actual desktop drawer/modal captures.
- `countin-before.png`, `countin-after.png`: the same count-in frame, showing removal of the second clipped preparation clef/meter while retaining the engraved opening header.
- `practice-800x600-after.png`, `practice-desktop-after.png`, `pause-800x600-after.png`: real imported-MIDI interaction captures, including readable transport and a scrollable compact pause panel.
- `cpu.json`, `cpu-before.log`, `cpu-after.log`: real application-process measurements with an isolated backend and MIDI disabled.

| Tempo | Before maximum line error | After maximum line error | After travel / nominal tempo |
|---|---:|---:|---:|
| 40 BPM | 6.8 px | 0.8 px | 1.000000 |
| 80 BPM | 11.8 px | 0.8 px | 1.000000 |
| 120 BPM | 16.8 px | 0.8 px | 1.000000 |

Before the fix, the automated pixel regression failed on 18 of 36 sampled frames. It now checks count-in through the first onset at all three tempos. Geometry checks additionally cover whole passages, rests, barlines, system joins, pause/resume, retry, Stop, fixed zoom, native notehead ink, and deferred texture restoration. A synthetic ornament regression reproduces the imported MIDI texture-limit failure without committing personal music.

The actual imported Ala MIDI reproduced travel ranging from approximately 218 to 35,700 pixels per beat before repair. The repaired geometry uses approximately 35,700 pixels per beat consistently, with small integer raster-rounding differences. **This exposes a remaining usability limit:** unquantized microscopic ornament/rest durations can require very wide musical spacing to preserve all original glyph clearance. Their geometry no longer changes camera speed, but this is not a claim that such dense raw notation is comfortable to practise. Canonical note timing and grading were not simplified to hide this issue.

## CPU and timing limits

Eight-second samples, 1536×960, one-core CPU normalization:

| State | Starting main script | Repaired main script |
|---|---:|---:|
| Ready, no score | 2.75% | 1.87% |
| Ready, loaded warm-up | 4.12% | 2.37% |

Both runs used current shared modules, an isolated backend, and no MIDI; other verification processes were active on the host. These process measurements do not establish a statistical speedup or reproduce the earlier reported 10% on every hardware configuration. No additional speculative FPS or polling optimization was introduced.

Clock epoch calibration still has uncertainty from local HTTP asymmetry. Musical projection and metronome scheduling share the same backend-derived beat; USB/display/acoustic latency remains a hardware-session check. The original suite also crashed in FluidSynth while concurrent transport tests loaded the user's optional 1.2 GiB bank. Transport/PCM journey tests now select deterministic fallback audio; sampled-piano rendering retains its dedicated test, and production Listen retains the configured bank. A separate real Salamander render also passed: stereo PCM, 64,000 frames at 16 kHz, exactly four seconds, nonzero peak 2,273 (`sampled-listen.json`).

## Validation

The starting full run crashed in native FluidSynth. A baseline rerun excluding that Listen test module completed with 667 passed, 9 failed, 1 skipped. Stale journey checks expected removed navigation, the old white score, hidden Stop controls and old summary text. Capture helpers also awaited an idle redraw that low-processor mode could suppress indefinitely. Tests now use current user-facing routes and explicitly request rendered capture frames.

Final verification: `.venv/bin/python -m pytest -q -rs --tb=short` completed with **708 passed, 1 skipped in 252.41 seconds**. The skip is the system-SF2/libfluidsynth-dependent test; the separate installed Salamander render described above provides additional sampled-audio evidence. The corrected explicit Exit expectation also passes all 15 practice-interaction scenarios. The focused review found no remaining important findings in the repaired projection, sparse texture path, context-change spacing or pause Exit behavior.

The real launcher completed **39 preflight checks**, opened desktop Godot, and exited cleanly with its diagnostic ZIP/report. This was a short idle session with MIDI probing disabled, not hardware acceptance. Its report records the expected 30 FPS idle cap (28.3 minimum sampled FPS and a 149.4 ms worst startup frame); it contains no live Practice/Perform grading or Listen-sync samples. Active motion is assessed separately by the rendered captures and regression fixtures above.

Hardware-session entry point:

```bash
.venv/bin/python playtest.py --preflight
```

The preflight now includes clock calibration, drawer accessibility, real MIDI proportional geometry and actual rendered-playhead checks.
