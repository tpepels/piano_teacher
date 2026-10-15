# Phase 2A: musical correctness and score fidelity

Implementation branch: `codex/phase2a-musical-fidelity`, based on main
`f5e1957`. Main is unchanged. This work uses the existing MIDI-to-exercise,
grading, playback, curriculum and dark Godot interface.
Plan/baseline commit: `8ba6a14`; implementation and regression corpus: `65ddda5`.

## What changed

Imported attacks now carry deterministic source IDs, independent of the file's
location. The IDs survive simplified exercises, generated MusicXML, actual
Verovio noteheads, assessment and feedback. Repeated notes, parallel voices and
cross-hand unisons have distinct identities. Tied continuations carry the
original attack's identity and cannot satisfy a missing required attack.

Previously feedback could attach the right hand's C4 to the left hand's C4,
and per-measure voice allocation could swap overlapping unison tie chains.
Production engraving now emits explicit IDs, keeps stable lanes across bars,
and validates real glyphs, pitches, hands and attack counts. Imported material
cannot use the old approximate pitch/onset compatibility path.

MusicXML pickups and explicit rest measures now retain their actual quarter-beat
grid. A one-beat pickup followed by two four-beat bars stays `0, 1, 5, 9`;
previously it became `0, 4, 8`. Full-piece performance includes leading and
trailing silent measures. Ties are scoped by source part/staff/voice/pitch.
Source timing remains exact for grading; display duration and the notation
resolution are separate. Cursor attack anchors use the exact source onset and
the corresponding actual engraved position.

Explicit XML spelling, key and clef context reach the active exercise compiler.
An explicitly written D-flat remains D-flat. MIDI without key metadata gets no
invented key signature. Named hands take precedence over register guesses;
high left-hand material can use treble, and low right-hand material can use
bass. The moving preparation bar uses the same opening clefs as its lesson.
Common triplets/quintuplets use ordinary base note values and one group number,
instead of a chain of tiny tied residuals. A held MIDI pitch keeps its attack's
enharmonic spelling across a key change.

## Regression evidence

The baseline branch passed **450 tests in 156.52 seconds**. New tests were run
before their fixes:

- Initial real-file corpus: **40 failed, 17 passed**. Failures included lost
  measure grids/spelling/hand assignments, absent canonical mappings and
  silently accepted unsupported inputs.
- Engine integration: **2 failed, 1 passed**. Simultaneous cross-hand unisons
  shared one feedback glyph, and source metadata never reached the compiler.
- A later introduction-rest regression failed because the full-piece stage
  began at the first nonempty two-bar passage; it now includes the source rest
  measures.
- Rendered preparation test failed because clef metadata was absent. It now
  compares actual native Godot pixels for changed clefs on both staves.

The checked-in corpus has **26 supported actual MIDI/MusicXML files** and
**four rejection fixtures**, with independently recorded source facts. It covers
4/4, 3/4, 6/8, meter changes, pickups, rests, repeated pitches, chords, separate
voices, overlapping ties, cross-hand unisons, keys and spelling, crossed named
hands, high/low registers, triplets, quintuplets and PPQ 997 timing. Every generated
variant is checked through production Verovio, evaluation and feedback. A
240-attack original exercise is engraved across six actual pages.
The artifact run passed all **30 file cases**, exercised **76 generated
hand/level variants** and wrote **14 real score PNGs**.

The user's complete MIDI retains **2,346 unique source attacks, 237 bars,
712 quarter beats and 301 stages**. All 301 stage keys were compared directly
against main and are identical. An old-format ordinary MIDI progress record
reopens with the same stage, target BPM, clean streak and saved mastery.
Correcting a previously malformed MusicXML course can change its actual musical
span; existing migration preserves history and resets an incompatible streak.
This is covered by an actual-file pickup migration test, including retained
historical mastery and target BPM.

The final complete original engraving has **2,346 assessed attacks**, **2,579
positioned glyphs including continuations**, and **60 pages** at 40 BPM. Glyph
count differs from the old 2,679 because duration spelling and stable voices
change tied display segments; the required attack count remains exactly 2,346.
The generated-lesson command validates every explicit mapping and real location.

Independent review found one additional metadata ambiguity: simultaneous
conflicting MIDI keys were sorted and silently resolved. A failing-first real
MIDI test now requires a clear rejection; duplicate identical declarations stay
supported. Review found no additional confirmed defect after that fix.

## Local verification results

All checks ran locally on Arch Linux with Godot 4.7.2, a real X11/OpenGL window,
and the production music21/Verovio/CairoSVG path. CI was not used as evidence.
Installed versions: Python 3.14.8, pytest 9.1.1, Mido 1.3.3, music21 9.9.2,
Verovio 5.7.0, CairoSVG 2.9.1 and Pillow 12.3.0.

| Check | Actual result |
| --- | --- |
| Final `python -m pytest -q` after review fixes | **561 passed in 200.42 seconds**, no skips or failures |
| Godot parser (`./scripts/check_godot.sh`) | Passed |
| `smoke_phase0.py` | Passed import, real PNG, HTTP clock, pause/resume, preview and errors |
| `smoke_godot.py` | Passed actual score pixels, visible moving notes/beam, scheduled count-in and no preview mastery |
| `smoke_adaptive_godot.py` | Passed three clean takes, skeleton→outline, image/revision acknowledgement and saved progression |
| Fidelity corpus pytest | 60 passed; source facts, every variant, negative inputs and later-source excerpts |
| Corpus artifact command | 30 file cases passed, 76 generated variants, 14 PNGs, six-page original |
| `check_engraving.py` against actual MIDI | Passed; first source passage, 24 real positioned glyphs and PNG |
| `check_generated_lesson.py --complete-song` against actual MIDI | Passed; 2,346 required attacks, 2,579 real glyphs, 60 pages |
| `check_visible_playback.py` | Passed 40 rendered samples across 30/40/80/120 BPM, pause/resume/restart and completed ungraded preview |
| `check_desktop_ui.py` through normal `./run.sh` | Passed all screens at 1536×960, 1024×768 and 800×600 |
| Independent review focused tests | 45 passed; one finding fixed with a failing-first regression |

The full pytest suite also runs actual guided learner, instructional recovery,
Listen/Perform and responsive learning-UI journeys through native Godot and MIDI
callback adapters. These cover deferred recovery/10% slowdown, full-tempo
three-clean mastery, pause/resume and revision acknowledgement.

## Actual score and UI artifacts

Representative actual raster output is checked in under
[`docs/evidence/phase2a`](evidence/phase2a/):

- [High left hand in treble](evidence/phase2a/midi_high_left-1.png),
  [parallel tied voices](evidence/phase2a/xml_parallel_tied_voices-1.png),
  [pickup](evidence/phase2a/xml_pickup-1.png) and
  [source key/spelling](evidence/phase2a/xml_keys_spelling-1.png).
- [Triplets](evidence/phase2a/triplets.png) and
  [quintuplets](evidence/phase2a/quintuplets.png).
- [Six-page exercise, first page](evidence/phase2a/xml_long_multipage-1.png)
  and [last page](evidence/phase2a/xml_long_multipage-6.png).
- [Moving count-in at 40 BPM](evidence/phase2a/count-in-40bpm.png) and
  [normal launcher at 800×600](evidence/phase2a/practice-800x600.png).
- [Complete corpus report](evidence/phase2a/corpus-report.json), including
  explicit per-variant attack maps and source-note facts.

Score PNGs composite the production transparent raster on white for review;
UI captures come from actual native Godot windows. All six multi-page PNGs,
generated MusicXML, SVGs and layouts are reproducible with the corpus command.

## Reproducing on Arch Linux

Use the normal setup in README, including Godot 4, the project's Python extras
and its bundled Verovio fonts. Run desktop checks from an X11/Wayland session;
close Piano Teacher first because the native checks share port 8765. Each check
uses isolated application data. In this verification the branch worktree used
the original checkout's virtual environment, so `PYTHONPATH` explicitly selected
this worktree; an ordinary installation in this checkout does not need that
extra prefix.

```bash
sudo pacman -S godot python python-pip alsa-utils
python -m venv .venv
source .venv/bin/activate
pip install -e '.[godot,test]'
export PYTHONPATH="$PWD"
python -m pytest -q
./scripts/check_godot.sh
python scripts/smoke_phase0.py
python scripts/smoke_godot.py
python scripts/smoke_adaptive_godot.py
python scripts/check_musical_fidelity_corpus.py --output /tmp/piano-phase2a-corpus
python scripts/check_engraving.py --output /tmp/real-score.png "/path/to/music.mid"
python scripts/check_generated_lesson.py --complete-song --output-dir /tmp/full-score "/path/to/music.mid"
python scripts/check_visible_playback.py --output-dir /tmp/piano-visible
python scripts/check_desktop_ui.py "/path/to/music.mid" --output-dir /tmp/piano-ui
python scripts/smoke_student_journey.py --output-dir /tmp/piano-student
python scripts/smoke_learning_ui.py --output-dir /tmp/piano-learning-ui
```

`check_musical_fidelity_corpus.py` writes generated XML, actual SVGs, composited
score PNGs, layout maps and a JSON report. The fixture README documents their
deterministic regeneration. These are test fixtures, not a preloaded catalogue.

## Scope and remaining limits

The application still uses the chosen practice BPM and its existing single
clock. This milestone does not add source tempo-map playback, input calibration,
synthesis changes, catalogue content or teaching mechanics. Physical USB MIDI,
speaker audibility/latency and pedal behaviour need hardware verification.

Ambiguous same-track/channel/pitch overlapping MIDI events, orphan/unclosed
notes or XML ties, microtones, grace/unpitched or transposing XML material,
conflicting part measure grids/meters, and mid-measure key/clef changes receive
explicit errors. Extremely close attacks that collide at 1/10080-quarter-beat
notation resolution are rejected. Anonymous internal models keep a bounded
legacy compatibility path; imported exercises require strict identity maps.
Conflicting simultaneous MIDI key declarations are rejected as ambiguous too.
