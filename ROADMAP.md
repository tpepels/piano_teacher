# Piano Teacher - path to a complete MIDI-based piano tutor

## Target product

An offline, fullscreen Linux piano-learning application with a small, elegant
Godot interface. Load a user-owned MIDI or MusicXML song and practice its
traditional piano notation using a USB MIDI keyboard. An audible count-in
begins a strict clock: the cyan timing beam and score advance at the selected
BPM regardless of player input. Real playing is judged note by note; listening
to a demonstration is a separate action.

The app is inspired by the timed sheet-music experience of learning products
such as Simply Piano but is not a copy of their lessons or proprietary content.

## Development milestones and acceptance gates

These milestones are sequential for the core practice experience. Do not
claim a milestone done merely because unit tests pass: Godot parsing, actual
engraving, a connected piano and audio timing must also be exercised.

### 0 - Stable startup and verifiable vertical slice

- Fix missing modules, permissions, parser failures, dependency mismatches and
  UI errors that silently produce grey or blank windows.
- Run `python -m pytest -q` and `scripts/check_godot.sh` before release.
- Exercise the real MIDI import, Verovio SVG, CairoSVG PNG, Godot texture, and
  USB input with a short real file.
- **Gate:** app opens fullscreen, displays score, starts and completes a
  two-measure timed preview, and exits cleanly on the target Arch system.

### 1 - Trustworthy transport and following notation

- Share one time base for backend, count-in audio, animated playhead, MIDI
  timestamping and metronome; account for latency and pause/restart.
- Start at a musical time-zero line, move continuously at the selected BPM and
  scroll notation with a comfortable read-ahead distance, even in silence.
- Handle multi-system/page transitions, rests, tempo overrides, repeat, restart,
  interruptions, automatic passage change and score preprocessing.
- **Gate:** 30 repeated starts/stops at 40/80/120 BPM with no stuck state;
  musical position and audio clicks stay synchronized on target hardware.

### 2 - Reliable score import and readable notation

- Use a canonical beat-based event model shared by engraving, scoring and demo.
- Quantize performed MIDI sensitively; preserve original timing as an option;
  avoid nonsensical ledger-line stacks and inconsistent time signatures.
- Handle tempo maps, pickups, ties, chords, rests, voices, pedal data, difficult
  rhythms, and correctly map notation to source MIDI events.
- Correctly identify left/right hands and permit persistent reassignment.
- **Gate:** a test corpus of at least 20 varied real MIDI/MusicXML pieces
  renders legible staves, with correct note/event correspondence. Unsupported
  files get actionable errors rather than fake notation.

### 3 - MIDI hardware, calibration and scoring

- Device discovery/reconnection; visible note-input diagnostic; latency
  calibration; sustain pedal and overlapping chords; repeat-note matching.
- Score pitch, onset (nominal ±100ms), release (nominal ±20% duration), extras,
  missed notes, hands and error categories correctly.
- Highlight mistakes on their engraved noteheads during/after a pass.
- **Gate:** deterministic recording fixtures plus live hardware trials agree;
  empty-input previews never award mastery or progress the curriculum.

### 4 - Complete adaptive lesson progression

- Teach the two-measure blocks per hand, then both; bridge every adjacent
  block with four-measure uninterrupted connections, and conclude with the
  whole piece.
- Start around 40% tempo; advance speed from verified clean repeats; isolate
  recurring mistakes; allow manual hand, passage and tempo override.
- Preserve per-hand, per-passage, per-tempo mastery over restarts.
- **Gate:** a 16+ measure composition can be completed end to end without
  manual intervention, with reasonable recovery after repeated errors.

### 5 - Demonstration playback and practice tools

- Implement Listen using a local piano sound generator (e.g., FluidSynth),
  with both-hands/one-hand demos and selected passage playback.
- Metronome on/off/volume, adjustable loop regions, slowdown and clear audio
  routing without dependence on the connected keyboard synthesizer.
- **Gate:** demo pitches and timings correspond to the same score events
  evaluated in practice; playback stops reliably and does not count as playing.

### 6 - Finished UX, preferences and progress

- Calm full-screen home/library/practice/settings screens; responsive layout,
  stable large notation, prominent timing beam, subtle inactive staff.
- Library search, sort, recent/continue; settings for device, folder, hand
  corrections, latency, visual toggles, notation labels and audio.
- Explain loading errors and prerequisites without exposing implementation
  details; keyboard-only control; accessible contrasts/text scaling.
- **Gate:** first-run-to-practice flow succeeds without a terminal walkthrough.

### 7 - Packaging, reliability and release

- Produce an Arch-ready installable distribution with bundled/validated Python
  and Verovio assets, Godot runtime and an appropriate audio backend.
- End-to-end startup/import/score/clock/scoring/persistence smoke suite, with
  short and dense example scores; renderer/geometry screenshot comparisons.
- Manage file errors, USB disconnects, rapid navigation and shutdown cleanly.
- **Gate:** clean-machine installation and an extended real-piano rehearsal
  complete with no manual dependency repair or unhandled exception.

## Definition of feature-complete

User points the application to a music folder, selects a suitable MIDI/MusicXML
piece, verifies or corrects hands, presses Start, hears a measured count-in,
then follows a scrolling full-size score while playing at adjustable tempo.
Correctness feedback is located on the score; the lesson engine adapts,
repeats difficult transitions and remembers mastery. Listen plays a piano
demo separately. The application works offline and can be installed and used
without editing code.

Features deliberately outside the first feature-complete release: microphone
note detection, copyrighted course catalogue, PDF/photograph transcription,
online accounts, cloud synchronization and automatic high-confidence
fingering for arbitrary imported songs.
