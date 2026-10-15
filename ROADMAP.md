# Piano Teacher — adaptive MIDI-to-exercise piano tutor

## Current implementation status — 2026-10-15

- **Visible software playback verified:** actual desktop/HTTP frames at 30, 40,
  80 and 120 BPM track the same rendered note moving left under a stable timing
  line. Count-in, pause/resume, restart, rests and multi-page/system projection
  are covered. Python remains the sole clock; no-input previews cannot master.
- **Dark UI implemented and desktop inspected:** library, practice, lesson path
  and settings use the approved forest/charcoal/stone palette. The normal launcher
  was exercised with a real MIDI at desktop and 1024×768/800×600 window sizes.
- **Curriculum consolidated:** the supplied 2,346-note piece now has 45 learning
  sections, 44 boundary connections and one complete original performance: 301
  stages instead of 1,209. Difficult two-bar work remains. Existing progress is
  migrated additively by musical identity; target tempo survives navigation.
- **Notation corrected:** real rest events and measured staff lines participate
  in geometry; transparent margins crop correctly. Compound rests and tied
  durations preserve onset alignment. The complete source passes required-note
  alignment and contains the held ending through beat 712/bar 237.
- **Adaptive engine retained:** five-error boundary recovery, 10% slowdown,
  target restoration, automatic repetition, three clean target-speed full takes,
  score-ready handoff and saved mastery remain regression/integration tested.
- **Physical acceptance remains open:** real USB MIDI input, disconnect/reconnect
  behavior on the target instrument, speaker audibility and latency must be
  checked with the user. Software captures do not replace this gate.

See `docs/verification-2026-10-15.md` for exact local evidence and limitations.
The remaining roadmap below describes product direction and hardware acceptance;
older CI notes at the end are historical evidence, not the current test count.

## Product definition (confirmed 2026-10-14)

The app is a fullscreen, offline Linux **piano teacher**, not a MIDI player,
karaoke transcription or static sheet-music viewer. It accepts user-owned MIDI
(and MusicXML), analyses musical material and generates a progressive sequence
of **purpose-made, playable exercises**. The original score is a reference,
not the default lesson presentation. The final destination is a correct,
full-tempo rendition of the imported piece.

Non-negotiable teaching behaviour:

1. Difficult material is **simplified first** (remove optional chord tones,
   lighten accompaniment, simplify hard rhythmic figures without shifting the
   overall musical time grid), then deliberately restored in later exercises.
   Original note positions remain traceable and the full original is revisited.
2. **A tempo-capped preparation interval precedes every attempt**. The score/lead-in moves
   from the first audible count-in beat; the first playable note arrives at the
   timing marker after the moving lead-in. Count-in and notation use one musical
   clock. Rests and empty bars are genuinely time-bearing.
3. **Five distinct wrong or missed required notes** within a rolling
   two-measure window trigger recovery. Continue through the *end* of the
   current two-measure chunk, then rewind to an appropriate boundary about two
   bars earlier. Every retry begins with a fresh short moving lead-in.
   Do not double count one wrong pitch as both missed and extra.
4. On threshold failure slow by **10%** (minimum 12 BPM). Following a clean
   pass increase in increments, bounded by the exercise's target BPM. Neither
   a slowed success nor an unconnected timing preview awards full mastery.
5. Require **three consecutive clean performances at the current exercise's
   target tempo** to progress. Incorrect attempts reset the clean streak.
   Persist passage, hand, simplification level, target tempo and mastery.

User can always Stop, Pause, Restart, navigate exercises or override tempo.
Attempts chain automatically with a short, understandable feedback interval.
Listen/demonstration is a separate audio mode; silent previews never grade.

## Delivery order and acceptance gates

We develop the core experience in short testable increments. A Python-only
test pass never constitutes Godot/hardware acceptance.

### Phase 0 - Stable launch and import-to-screen vertical slice [software verified; physical acceptance open]

Reliable executable launcher, Verovio fonts and CairoSVG assets, Python API,
Godot scene parsing and actual startup, real score PNG geometry, isolated
backend ownership of port 8765 and readable runtime errors.

**Acceptance:** application opens on target Arch machine; loads a real MIDI,
shows a real engraved score, enters/exits a timed preview without a grey or
blank screen; backend and headless Godot integration checks pass.

### Phase 1 - Adaptive moving-lesson runtime [software verified; learner/hardware acceptance open]

- **1A - Lesson timeline:** one signed beat clock; one moving preparation bar
  before every attempt; fixed-tempo visual movement from the very first
  count-in beat; continuous note timing after lead-in; pauses/stops/restarts;
  next-attempt scheduling with short visible feedback intervals.
- **1B - Error recovery:** identify distinct wrong/missed required notes on
  the active exercise; detect five within a rolling two-bar window; do not
  interrupt mid-chunk; rewind to a safe preceding boundary; slow by 10%;
  retry with a short moving lead-in; recover speed incrementally after
  a clean pass without granting premature mastery.
- **1C - MIDI-to-exercise generation:** infer track/hand roles, measure
  structure and phrase boundaries; generate simpler musical variants then
  progressively restore omitted notes, chords and rhythms, with traceable
  source-to-exercise mappings. Do not engrave MIDI unchanged and call it a
  lesson. Preserve the original for the final performance exercise.
- **1D - Curriculum and repetition:** separate per-hand learning, both-hand
  integration, bridges across fragments, three clean repeats per exercise at
  its target tempo, persistent mastery and meaningful manual override.
- **1E - End-to-end adaptive lesson:** responsive Godot presentation for
  lead-in, note arrivals, mistake markers, feedback, retries, level changes
  and exercise readiness; real-engraving smoke against imported pieces.

**Acceptance:** take a sufficiently complex imported MIDI and automatically
produce at least two different exercise variants; watch two moving lead-in
measures; perform/replay a passage three times; deliberate mistakes cause a
deferred two-bar rewind and 10% slowdown; clean playing restores target tempo
and only then advances. No hardware input means visual preview only.

### Phase 2 - Musical representation and notation fidelity

Canonical quarter-beat timebase and stable note IDs shared by source notes,
simplified lesson variants, engraving, evaluation and demonstrations. Better
quantization, pickup bars, multiple voices, ties, chords, tempo maps, rests,
hand assignments and outlier ledger lines. Allow persistent hand corrections.

**Acceptance:** a corpus of at least 20 representative MIDI/MusicXML imports
produces readable *lesson notation*, and every displayed required note maps
back to the correct MIDI pitch/time. Unsupported material reports limitations.

### Phase 3 - Input calibration and robust feedback

MIDI device discovery/reconnect, latency calibration, sustained/repeated
notes, chords/pedal, note-on/off capture, pitch and rhythm matching,
early/late/short/long, extras vs wrongs, and correct on-score highlighting.

**Acceptance:** deterministic performance fixtures and live keyboard trials
produce matching note assessments. A preview without input never masters.

### Phase 4 - Personalized teaching and longer pieces

Refine difficulty estimation, error-aware section boundaries, repeated
trouble-spot isolation, adaptive threshold policies, tempo recovery and
longer-form progression. Per-piece retained settings/mastery across sessions.

**Acceptance:** a 16+ bar piece is taught without manual passage navigation;
later full-piece practice retains all original notes.

### Phase 5 - Listen, demonstrate and supporting practice tools

Local piano soundfont playback with optional one-hand demonstration,
metronome options, section loop selection and audio routing. Playback cannot
be confused with recorded student MIDI.

**Acceptance:** demo sound and engraving share the same event/time model.

### Phase 6 - Graphics, UX and accessibility

Purpose-built exercise-score layout, large notation, uncluttered full-screen
home/library/practice/settings, subtle inactive hand, readable moving beam,
optional note names/finger hints, transparent feedback and difficulty settings.

**Acceptance:** new user can import music and learn without editing files or
running terminal commands.

### Phase 7 - Packaging and release

Arch-ready installable application, dependency/resource bundling, offline
operation, deterministic Python and real-Godot smoke tests, score snapshots,
performance/load tests, crash recovery, clean shutdown and USB unplug/replug.

**Acceptance:** clean-machine installation and extended real-piano practice
session without manual dependency repairs or unhandled errors.

## Current testing policy

For each increment, provide deterministic backend tests, source/GDScript
checks, and as soon as available headless Godot integration. Hardware/audio
validation can be deferred explicitly but must not be claimed complete.
Avoid treating source-based assertions as proof of visual correctness.
Do not wait for CI; report local tests and exact commands to run on Arch.

## Deliberate first-release exclusions

No microphone recognition, copyrighted song/course catalogue, scanned score
recognition, automatic guaranteed fingering, online accounts or cloud sync.
