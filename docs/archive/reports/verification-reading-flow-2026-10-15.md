# Reading flow verification — 2026-10-15

The earlier practice redesign (`53659ad`, `66faf82`) was fast-forward merged
and pushed to `main` with the user's authorization. This follow-up keeps the
same screens and control count while making practice easier to read and resume.

## Behavior

- Practice tempo controls native engraving space: slower beats have wider gaps.
  Noteheads, accidentals, stems, beams and ties keep their proportions. Encoded
  breaks avoid system justification changing that spacing; a measured relayout
  keeps dense notation inside its page.
- Count-in uses the opening passage's measured beat distance. Both clefs, the
  source meter and real engraved rests move toward the timing line. Partial
  preparation beats use an eighth rest. The first note reaches the line without
  a change in incoming speed.
- The primary control is Start → Pause → Resume; Space follows the same cycle.
  Stop is a separate secondary action. Opening Settings or Lesson path pauses
  an active attempt. Back preserves the pause, and Settings remembers its origin.
- Practice metadata is shorter, feedback wraps, and only the current passage's
  full stage chain appears in the lesson list.
- Focused buttons cannot turn a Space press into a second action. Immediate
  navigation preserves the pause/stop intent across pending HTTP responses,
  and delayed pre-action snapshots cannot overwrite the acknowledged state.
- Generated sharps and natural cancellations are visible across voices and
  measures. Native glyph bounds keep opening/recovery accidentals and ledger
  lines clear of the preparation mask.
- Tempo recovery retains the completed score and feedback during the reading
  break, then waits for new spacing to load before starting the retry clock.

## Evidence

Real desktop checks use Godot 4.7.2 with X11/OpenGL, ordinary HTTP polling and
actual rendered pixels. Isolated XDG directories preserve the user's progress
and preferences. No physical piano is required for these software checks.

| Check | Result |
|---|---|
| Full Python/Godot regression suite | **244 passed**, 20.86 seconds |
| Godot parser | Pass |
| Backend smoke | Pass |
| Godot practice smoke | Pass: score pixels, moving count-in, clicks and silent completion |
| Adaptive Godot smoke | Pass: three clean synthetic takes, next stage, revision acknowledgement and persistence |
| Complete user MIDI at production spacing | Pass: all 2,346 source notes, 2,679 glyphs including ties, 60 pages at 40 BPM |
| Dense notation bounds | Pass: eighths through sixty-fourths, native glyph size retained |
| Desktop playback, 30/40/80/120 BPM | Pass: 40 actual rendered samples |
| Desktop playback, 800×600 at 120 BPM | Pass: 10 actual rendered samples |
| Normal launcher screens and settings | Pass: 1536×960, 1024×768 and 800×600 |
| Real X11 opening and recovery ink regression | Pass: preserves sharp signs and ledger lines |
| Pending-navigation regressions | Nine pass, including same-millisecond stale snapshots and failed first requests |

The same opening note moved at 165.08, 165.92, 165.72 and 163.13 pixels/second
at 30, 40, 80 and 120 BPM respectively. Paused-note drift was zero. Every tracked
note sample had at least 100 contrasting notehead pixels. The real Godot motion
regression also compares velocity immediately before and after the downbeat.

Local reproducible artifacts:

- `/tmp/piano-reading-flow-visible/`: four-tempo frames, measured positions and logs.
- `/tmp/piano-reading-flow-compact/`: compact desktop count-in/playback frames and logs.
- `/tmp/piano-reading-flow-ui-final/`: library, practice, lesson, settings and MIDI menu frames.
- `/tmp/piano-reading-flow-complete/`: complete actual MIDI raster.
- `/tmp/piano-notation-ink-review/`: source/preparation comparison frames.

Independent review caught dense native-page overflow, clef/meter crowding,
focused-button double activation, pending-navigation races and hidden accidentals.
Each received a failing-then-passing regression. No important review finding
remains open.

Physical USB piano input, speaker audibility, audio/MIDI latency and pedal
behavior remain unverified. Whole-piece scores preload cropped textures;
streaming neighboring systems remains a future memory optimization.
