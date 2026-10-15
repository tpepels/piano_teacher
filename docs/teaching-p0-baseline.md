# Teaching interaction P0 baseline — 2026-10-15

Baseline commit: `7670eb543fa89393ef809d39f16f0c24f1fcfd1c` in
`/home/tom/Projects/piano_teacher_teaching`. This verification ran before P1
implementation, with no changes to production code. The linked virtualenv was
used with `PYTHONPATH=/home/tom/Projects/piano_teacher_teaching`; an import check
confirmed `piano_teacher.__file__` resolved inside this checkout. `rtk` was not
installed, so commands used the direct shell fallback.

Evidence is retained under `/tmp/piano-teaching-p0`. Desktop captures came from
real Godot 4.7.2, X11/OpenGL compatibility renderer on AMD Radeon 860M; no static
mockups were substituted. Test data/config/cache directories were isolated.
Source MIDI and existing user progress/preferences were not modified.

## Fresh results

| Command/check | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **244 passed in 20.02s**, exit 0; `pytest.log` |
| `./scripts/check_godot.sh` | Pass, real Godot parser, exit 0 |
| `.venv/bin/python scripts/smoke_phase0.py` | Pass, MIDI import → engraving → valid PNG → HTTP clock, ungraded preview and error handling; `smoke-phase0.log` |
| `.venv/bin/python scripts/smoke_godot.py` | Pass, actual practice scene, visible PNG notes, moving count-in, timed playback, click scheduling and natural silent completion; `smoke-godot.log` |
| `.venv/bin/python scripts/smoke_adaptive_godot.py` | Pass, isolated synthetic MIDI: three full clean takes → outline stage, score revision/image acknowledgement and persistence; `smoke-adaptive-godot.log` |
| `.venv/bin/python scripts/check_visible_playback.py --output-dir /tmp/piano-teaching-p0/visible --bpms 30 40 80 120` | Pass, **40 actual rendered frames**, empty failures; `visible.log`, `visible/samples.json` |
| `.venv/bin/python /tmp/piano-teaching-p0/check_extended_playback.py --output-dir /tmp/piano-teaching-p0/extended --bpms 40` | Pass, **7 actual rendered frames** covering a complete slow phrase; `extended.log`, `extended/samples.json` |
| `.venv/bin/python scripts/check_desktop_ui.py "/home/tom/Music/Piano Teacher/Merry-Go-Round-of-Life.midi" --output-dir /tmp/piano-teaching-p0/desktop` | Pass, normal `./run.sh`, **11 rendered frames**, home/library/practice/lesson/settings/MIDI menu, 1536×960, 1024×768 and 800×600; `desktop.log`, `desktop/launcher.log`, `desktop/ui-result.json` |
| `.venv/bin/python scripts/check_generated_lesson.py "/home/tom/Music/Piano Teacher/Merry-Go-Round-of-Life.midi" --output-dir /tmp/piano-teaching-p0/generated` | Pass, 2,346 source notes; opening skeleton has 11 required notes/13 glyphs, original 24 required notes/31 glyphs; `generated.log` |
| Same generated-lesson check with `--complete-song` and `--output-dir /tmp/piano-teaching-p0/complete` | Pass, **all 2,346 required notes, 2,679 positioned glyphs, 60 pages**; `complete.log` |

All Python commands above had the explicit checkout `PYTHONPATH` prefix. The
normal launcher already sets it itself. The first five normal desktop captures
were window-manager clamped to 1536×886; the explicit 1536×960, 1024×768 and
800×600 captures have their requested dimensions. The three frame sets retain
**58 actual rendered UI frames** altogether; source-score rasters are separate.

## Motion and appearance

Each ordinary playback tempo retains ten frames: six samples across count-in
and playback, two paused frames, resumed playback and a restarted count-in.
The same source note ID moves continuously, while the timing line and notation
scale stay stable. Minimum detected contrasting notehead pixels were **100**
at every tempo. Maximum measured timing-line drift was **0.00012 px**;
paused-note drift was **0 px** at every tempo. All sample failure arrays are
empty. Start, Pause, Resume, Restart and Stop completed without runtime errors.
The natural no-device preview returned to `ready` with no mastery awarded.

The additional temporary harness reuses the production Godot scene, ordinary
HTTP polling and backend clock. Its small 3/4 MIDI has a held first note, an
explicit rest, a second attack and a held ending. Its source and generator are
in `/tmp/piano-teaching-p0/extended_playback.gd`,
`check_extended_playback.py` and `make-extended-check.py`.

| Actual 40 BPM frame | Clock beat | Evidence |
|---|---:|---|
| `extended/frame-40-onset-lead-in.png` | −2.2924 | Opening note visible during moving lead-in |
| `extended/frame-40-notehead-crossing.png` | 0.0087 | Actual first notehead is **2.17 px** from the fixed timing line |
| `extended/frame-40-held-note.png` | 1.3094 | Half note remains visible during its duration |
| `extended/frame-40-rest.png` | 2.5057 | Explicit rest passes the line, next attack stays visible |
| `extended/frame-40-mid-phrase.png` | 3.2062 | Second attack, both staves visible |
| `extended/frame-40-end-of-phrase.png` | 5.8082 | Held final note and phrase-ending barline remain visible |
| `extended/frame-40-finished.png` | completed | `ready`, `mastered = 0` |

The phase label in the crossing sample still says `count_in` because it is the
last polled state; the frame's rendered authoritative clock is already 0.0087.
This is ordinary polling at the transition, not a separate animation clock.

Visual inspection compared the actual 40 BPM lead-in/crossing/rest/ending and
actual MIDI practice/settings captures to `moodboard.png`. They preserve the
forest/charcoal background, stone notation/text and restrained teal timing line.
Both staves and real noteheads are legible at normal scale and at 800×600;
controls fit the viewport. No moving-score regression requiring a camera
rewrite was observed. Existing UI still foregrounds stage counts and has no
untimed guided interaction or hint keyboard; later milestones address those
known product gaps.

## Physical acceptance still pending

These software checks do **not** establish USB instrument recognition, physical
speaker audibility, audio/MIDI latency or pedal behavior. The adaptive smoke
injects played notes only inside its isolated engine; ordinary no-device
previews never count toward mastery.

On the target machine:

1. Connect the actual USB piano and intended speakers/headphones. Close other
   Piano Teacher instances, then run `./run.sh` from this checkout.
2. In Settings, choose the actual piano in **Choose USB MIDI piano**. Press and
   release single notes, a repeated pitch and a chord; verify device/activity
   feedback reflects that instrument. A MIDI Through port is not acceptance.
3. Open `/home/tom/Music/Piano Teacher/Merry-Go-Round-of-Life.midi`, select a
   generated opening passage and set target tempo to **40 BPM**. Start and watch
   the short moving lead-in. The incoming score must move smoothly under one
   fixed teal timing line, with notes visible through attack, hold, rest and end.
4. Confirm count-in clicks are audible through the intended output. Toggle the
   practice metronome and confirm its real sound matches the displayed beat;
   record any measurable latency/jitter or device/output mismatch.
5. Pause during a note, wait, then Resume: notation must freeze and continue
   from the same exercise and tempo. Stop/Restart must create a fresh lead-in.
   Opening Settings/Lesson path should pause without losing the passage.
6. Play correct notes, deliberately miss/wrong-play five distinct required notes
   over two bars, and confirm the attempt finishes its musical chunk before a
   slower retry. Check pedal/held notes and repeated attacks with the actual
   instrument; record observed grading/latency limitations.
7. Unplug during practice. The UI must show disconnected/ungraded status and
   abandon scoring. Reconnect and explicitly select the piano if needed; verify
   input recovers. A silent disconnected preview must leave clean/mastery credit
   unchanged.

Record the instrument name, audio output, window scale, observed latency and any
failure with a screenshot/short recording before marking this physical gate
accepted. Whole-piece cropped textures still preload; neighboring-system
streaming remains a future memory optimization.
