# Physical MIDI acceptance: adaptive Coda + Fukuda

**Status:** Requires execution with a real USB/Bluetooth MIDI keyboard and
Godot 4.7.2. Passing CI or virtual note injection does not mark these passed.

## Preparation

1. Update the development checkout on `main` with `git pull --ff-only`.
2. Run `./run.sh` with the native in-process bridge already installed.
3. Connect the actual MIDI keyboard and verify that the device and
   MIDI-input activity are visible in Settings.
4. Select `Coda + Fukuda · MIDI combined lessons` and open a source MIDI
   piece with chords, fast notes, regular eighth notes, rests and both hands.
5. Record Godot build/version, keyboard model, USB/Bluetooth transport and
   configured MIDI latency offset along with the result.

## Required playing session

1. From the lesson overview, verify consecutive short passages precede
   connectors and the original whole-piece performance. Confirm source
   rests, barlines and held notes are visible and playable.
2. Start the first offered stage with its count-in, play deliberate correct
   notes, pause/resume, and retry. Check that every visual attack and
   recorded MIDI judgment uses the same transport position.
3. Select the first passage's original stage and deliberately play one
   **wrong** chord pitch. Wait for the settled assessment. Expect a
   source-bound Fukuda reduction in that passage without losing prior
   mastery, manual tempo or position elsewhere.
4. Return to its original notes and repeat **the same** wrong pitch.
   Expect the simplification to reappear even though the saved error's
   category and source ID have not changed.
5. Correct that original pitch on another full scored attempt. The saved
   source-error record must clear, with the original notes still available.
6. Produce one **late** attack in a passage supporting a dotted exercise.
   Expect a Coda dotted rhythmic scaffold; repeat with a short note-off
   and expect a Coda slowdown scaffold.
7. Navigate to another passage, alter its BPM, stop, exit, reopen the
   piece and confirm the same selected stage, earned progress, manual
   tempo and source-specific error evidence are restored.
8. Master each short passage and bridge, then complete the unchanged
   original whole-piece finale. Confirm no earlier reduction substitutes
   for a clean original take.

## Record failures precisely

For every failure, retain the input MIDI title/hash, selected strategy,
lesson number/hand/level, BPM, note pitch/source beat, expected/actual
attack or release time, transport phase, score revision and user action.
A screenshot/short screen capture helps diagnose notation handoffs, but
a screenshot alone cannot prove grading timing. Do not claim hardware
acceptance until all eight checks pass on actual connected hardware.

## Software evidence

The bounded [adaptive/composed curriculum checks](https://github.com/tpepels/piano_teacher/actions/workflows/composed-midi-lessons.yml)
cover source-ID continuity, computed stage selection, target-tempo
mastery, progress persistence, score rendering, Listen and grading.
The [Godot 4.7.2 smoke workflow](https://github.com/tpepels/piano_teacher/actions/workflows/godot-startup-check.yml)
checks native screen contracts. The
[actual production-scene native test](https://github.com/tpepels/piano_teacher/actions/runs/41663899894)
passed at `aecbb09`, covering last-piece startup, retained score readiness,
and Play/Pause/Resume on a generated two-hand source. The
[real-MIDI written-rest regression](https://github.com/tpepels/piano_teacher/actions/runs/41665774242)
passed at `cc7efe9` across a full silent measure. Frame-level notehead
travel acceptance, the actual Beethoven score, and the eight physical
keyboard checks are still separate gates. None of these CI runs is a
physical MIDI test.
