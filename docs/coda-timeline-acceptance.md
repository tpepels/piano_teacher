# Coda research: transformed timeline acceptance

Status: **partial automated integration**. The current live application's
existing dotted-pair and two-phase-tempo stages use their selected
`ExerciseStage.variant.phrase` for both notation and grading. This increment
corrects two previously independent consumers of that selected timeline.

## Automated results and boundaries

- Python `TempoMap.as_segments()` is the shared beat-to-second source for
  WAV note warping, mapped grading, feedback and HTTP session projection.
- Godot's new `tempo_timeline.gd` performs the same piecewise integration:
  `visual_transport_clock.gd` uses its seconds-to-beats inverse, and
  `demo_player.gd` uses its beats-to-seconds conversion when comparing
  audible WAV position against the moving playhead. The poll-free main.gd
  fallback uses it as well. Fixed-tempo stages remain unchanged.
- `LiveInputView` uses that same map to associate provisional MIDI keydowns
  with source identities and classify early/late input. This previously
  used constant BPM while the final grader used variable BPM.
- A bounded checked-in MusicXML fixture tests notation attack/source IDs,
  warped Listen WAV *source positions*, whole-take MIDI scoring, keydown
  preview and settled notehead feedback. Godot has an opt-in headless
  mapped-clock oracle; CI uses short Python checks and skips Godot when absent.

**This does not activate the standalone Coda research transformations**:
the exact Coda thesis/source parity gate is still open, and the new
part-splitting, tempo-shaping and polyphonic dotted-rhythm prototypes
have not been made production-selectable. Existing integrated experimental
timing settings remain separate from the canonical original-score mastery
stage.

## Required physical verification (not performed in CI)

On the Linux laptop with the actual MIDI keyboard and speakers:

1. Update `main`, launch `./run.sh` with your normal hardware. Connect MIDI
   and confirm the application reports the chosen physical device.
2. Select **dotted-long-short** and **two-phase-tempo** in settings. Use a
   short two-hand MusicXML passage with several evenly timed attacks and
   select the transformed stage; keep its final original stage available.
3. In Listen, watch noteheads at the slow-to-normal tempo boundary.
   Verify by ear or captured loopback audio that the same attack reaches
   the speaker and fixed playhead together across that boundary.
4. In Practice, play the same right-hand notes on time, then deliberately
   play one key early, one late and one wrong pitch. Confirm provisional
   feedback and final grading refer to the *same* noteheads.
5. Repeat after Pause/Resume and from a selected later measure. Verify
   count-in, first attack, tied notes, releases and repeated-note identity.
6. Capture a loopback recording plus MIDI event timestamps, and report
   measured speaker/audio latency and MIDI-key latency separately.
   Godot's software drift estimator explicitly does **not** measure
   physical output or input latency.

Record pass/fail and any measurable offset for each scenario. A failing
hardware case blocks full end-to-end acceptance; a passing automated
contract is insufficient evidence for real-device synchronization.

No multi-minute CI, corpus raster audit or background process is needed
for the regular push gate.
