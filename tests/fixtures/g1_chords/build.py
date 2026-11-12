"""Build the G1 adversarial chord fixtures: every chord must draw.

Run from the repository root to regenerate (the outputs are committed):
(g1_app_hard_chords.mid is the in-app readiness sweep input.)

    .venv/bin/python tests/fixtures/g1_chords/build.py

g1_chords.mid is an ordinary multi-track MIDI file, the input a user imports.
MIDI carries sounding pitch only, so shapes that exist only as written spelling
(three heads on one staff position, double accidentals, C clefs, grace chords,
arpeggio marks) come from g1_chords.musicxml, the other supported import.
cases.json names the case in each source measure for the probe and its tables.
"""
from __future__ import annotations

import json
from pathlib import Path

import mido

HERE = Path(__file__).resolve().parent
TICKS = 480

# (bar, case, [(track, channel, beat_in_bar, beats, pitch), ...]).
# Track 0 "Right Hand", 1 "Left Hand", 2 "Right Hand 2" (a duplicating part).
_W = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _p(name: str) -> int:
    step, rest = name[0], name[1:]
    alter = rest.count("#") - rest.count("b")
    return (int(rest.strip("#b")) + 1) * 12 + _W[step] + alter


def _chord(track, beat, beats, names, channel=0):
    return [(track, channel, beat, beats, _p(n)) for n in names.split()]


MIDI_CASES = [
    # bar 1-2: two heads on one staff position (sharp spelling in C major)
    (1, "unison-pair-up", _chord(0, 0, 1, "E4 G4 G#4")),
    (1, "unison-pair-down", _chord(0, 1, 1, "G5 G#5 B5")),
    (1, "unison-pair-half", _chord(0, 2, 2, "F4 F#4")),
    (2, "chromatic-cluster-up", _chord(0, 0, 1, "C4 C#4 D4 D#4 E4")),
    (2, "chromatic-cluster-down", _chord(0, 1, 1, "A5 A#5 B5 C6 C#6")),
    (2, "unison-pair-whole-lh", _chord(1, 0, 4, "F2 F#2 A2")),
    # bar 3-4: dense clusters of seconds, 4 to 6 adjacent notes, both stems
    (3, "cluster-4-up", _chord(0, 0, 1, "C4 D4 E4 F4")),
    (3, "cluster-5-down", _chord(0, 1, 1, "C5 D5 E5 F5 G5")),
    (3, "cluster-6-up", _chord(0, 2, 1, "D4 E4 F4 G4 A4 B4")),
    (3, "cluster-6-down", _chord(0, 3, 1, "A4 B4 C5 D5 E5 F5")),
    (4, "cluster-lh-up", _chord(1, 0, 1, "C2 D2 E2 F2")),
    (4, "cluster-lh-down", _chord(1, 1, 1, "B2 C3 D3 E3 F3")),
    (4, "eleven-heads", _chord(0, 2, 2, "C4 D4 E4 F4 G4 A4 B4 C5 D5 E5 F5")),
    # bar 5-6: very wide chords on ledger lines
    (5, "wide-ledger-rh", _chord(0, 0, 1, "A4 C7")),
    (5, "wide-ledger-lh", _chord(1, 0, 1, "A0 E1 G3")),
    (5, "wide-span-over-four-octaves", _chord(0, 2, 2, "C4 E5 C8")),
    (6, "twelve-chromatic", _chord(0, 0, 2, "C4 C#4 D4 D#4 E4 F4 F#4 G4 G#4 A4 A#4 B4")),
    (6, "ledger-cluster-high", _chord(0, 2, 1, "A6 B6 C7")),
    (6, "ledger-cluster-low", _chord(1, 3, 1, "C1 D1 E1")),
    # bar 7-8: mixed durations in one onset, dots, beams
    (7, "mixed-durations-one-onset", _chord(0, 0, 2, "C4 E4") + _chord(0, 0, 1, "G4 A4")),
    (7, "dotted-cluster", _chord(0, 2, 1.5, "C5 D5 F5")),
    (7, "dotted-eighth-pair", _chord(0, 3.5, .5, "G4 A4")),
    (8, "beamed-seconds", _chord(0, 0, .5, "C5 D5") + _chord(0, .5, .5, "E5 F5")
        + _chord(0, 1, .5, "G4 A4") + _chord(0, 1.5, .5, "B4 C5")),
    (8, "beamed-unisons", _chord(0, 2, .5, "G4 G#4") + _chord(0, 2.5, .5, "F4 F#4")),
    (8, "dotted-half-lh-cluster", _chord(1, 0, 3, "E3 F3 G3")),
    # bar 9-10: identical pitches from two tracks or two channels, cross-hand
    (9, "duplicates-two-tracks", _chord(0, 0, 1, "C4 E4 G4") + _chord(2, 0, 1, "E4 G4")),
    (9, "duplicates-two-channels", _chord(0, 2, 1, "C5 E5") + _chord(0, 2, 1, "C5 E5", channel=1)),
    (10, "cross-hand-split", _chord(0, 0, 1, "C2 E2 C5 E5")),
    (10, "lh-reaches-treble", _chord(1, 2, 1, "C3 E3 C6 E6")),
    # bar 11-12: polyphony around chords (voice stem directions)
    (11, "chord-under-held-note", [(0, 1, 0, 4, _p("C6"))] + _chord(0, 1, 1, "E4 F4")
        + _chord(0, 2, 1, "D4 E4") + _chord(0, 3, 1, "G4 G#4")),
    (11, "whole-second-lh", _chord(1, 0, 4, "C3 D3") + [(1, 1, 1, 1, _p("G2"))]),
    (12, "two-voice-same-onset", _chord(0, 0, 1, "E5 F5 G5") + _chord(0, 0, 2, "C4 D4", channel=1)),
]
# bar 13-14 in C sharp major, 15-16 in G flat major: key spelling at work.
MIDI_CASES += [
    (13, "sharp-key-unison", _chord(0, 0, 1, "E4 F4 F#4")),   # E, E sharp, F sharp
    (13, "sharp-key-b-sharp", _chord(0, 1, 1, "B4 C5 C#5")),  # B, B sharp, C sharp
    (15, "flat-key-unison", _chord(0, 0, 1, "B4 C5 D#5")),    # C flat, C, E flat
    (15, "flat-key-g-flat", _chord(0, 1, 1, "F#4 G4 A#4")),   # G flat, G, B flat
]
# bar 17-18: stems Verovio sets from the farthest head, not the mean, and
# heads whose arrangement depends on their absolute staff position.
MIDI_CASES += [
    (17, "asymmetric-low-anchor", _chord(0, 0, 1, "A3 F5 G5 A5")),
    (17, "asymmetric-high-anchor", _chord(0, 1, 1, "C4 D4 E4 C6")),
    (17, "far-ledger-joins-column", _chord(0, 2, 1, "D4 E4 B5")),
    (17, "asymmetric-pair", _chord(0, 3, 1, "B3 C4 G5 A5")),
    (18, "whole-asymmetric", _chord(0, 0, 4, "A3 F5 G5 A5")),
    (18, "whole-far-ledger", _chord(1, 0, 4, "G2 A2 E4")),
]
# bar 19-20: performed MIDI. One chord's keys release a few ticks apart; a
# held bass sounds under moving (also humanised) chords of the same track.
def _humanised(track, beat, names, releases, channel=0):
    return [(track, channel, beat, beats, _p(name))
            for name, beats in zip(names.split(), releases)]


MIDI_CASES += [
    (19, "humanised-triad", _humanised(0, 0, "C4 E4 G4", (1.0, 1.02, .97))),
    (19, "humanised-seventh-half", _humanised(0, 1, "D4 F4 A4 C5", (2.03, 1.96, 2.0, 1.98))),
    (19, "genuinely-different-values", _humanised(0, 3, "E4 G4", (1.0, .5))),
    (20, "held-bass-under-moving-chords", [(1, 0, 0, 4, _p("C2"))]
        + _humanised(1, 0, "E3 G3", (.98, 1.01)) + _humanised(1, 1, "F3 A3", (1.02, .97))
        + _humanised(1, 2, "E3 G3", (1.0, 1.03)) + _humanised(1, 3, "D3 F3", (.96, 1.0))),
]
MIDI_KEYS = {13: "C#", 15: "Gb", 17: "C"}
MIDI_BARS = 20


# A short in-app file: the hardest MIDI shapes, two bars per lesson.
APP_CASES = [
    (1, "unison-pair-up", _chord(0, 0, 1, "E4 G4 G#4")),
    (1, "chromatic-cluster-up", _chord(0, 1, 1, "C4 C#4 D4 D#4 E4")),
    (1, "asymmetric-low-anchor", _chord(0, 2, 1, "A3 F5 G5 A5")),
    (1, "asymmetric-high-anchor", _chord(0, 3, 1, "C4 D4 E4 C6")),
    (2, "eleven-heads", _chord(0, 0, 2, "C4 D4 E4 F4 G4 A4 B4 C5 D5 E5 F5")),
    (2, "far-ledger-joins-column", _chord(0, 2, 1, "D4 E4 B5")),
    (2, "unison-pair-down", _chord(0, 3, 1, "G5 G#5 B5")),
    (1, "cluster-lh-up", _chord(1, 0, 2, "C2 D2 E2 F2")),
    (1, "unison-pair-lh", _chord(1, 2, 2, "F2 F#2 A2")),
    (2, "whole-second-lh", _chord(1, 0, 4, "C3 D3")),
    (3, "twelve-chromatic", _chord(0, 0, 4, "C4 C#4 D4 D#4 E4 F4 F#4 G4 G#4 A4 A#4 B4")),
    (3, "wide-ledger-lh", _chord(1, 0, 4, "A0 E1 G3")),
    (4, "beamed-unisons", _chord(0, 0, .5, "G4 G#4") + _chord(0, .5, .5, "F4 F#4")
        + _chord(0, 1, .5, "C5 D5") + _chord(0, 1.5, .5, "E5 F5")),
    (4, "cluster-6-down", _chord(0, 2, 2, "A4 B4 C5 D5 E5 F5")),
    (4, "ledger-cluster-low", _chord(1, 0, 4, "C1 D1 E1")),
]


def build_midi(path: Path, cases=None, bars: int | None = None, keys=None) -> None:
    cases = MIDI_CASES if cases is None else cases
    bars = MIDI_BARS if bars is None else bars
    keys = MIDI_KEYS if keys is None else keys
    song = mido.MidiFile(type=1, ticks_per_beat=TICKS)
    names = ["Right Hand", "Left Hand", "Right Hand 2"]
    events = {track: [] for track in range(len(names))}
    for bar, _, notes in cases:
        for track, channel, beat, beats, pitch in notes:
            start = round(((bar - 1) * 4 + beat) * TICKS)
            end = start + round(beats * TICKS)
            events[track].append((start, 1, mido.Message(
                "note_on", channel=channel, note=pitch, velocity=72)))
            events[track].append((end, 0, mido.Message(
                "note_off", channel=channel, note=pitch, velocity=0)))
    for track, name in enumerate(names):
        timeline = [(0, -2, mido.MetaMessage("track_name", name=name))]
        if track == 0:
            timeline.append((0, -2, mido.MetaMessage("time_signature", numerator=4, denominator=4)))
            timeline.append((0, -2, mido.MetaMessage("set_tempo", tempo=500000)))
            timeline.append((0, -2, mido.MetaMessage("key_signature", key="C")))
            for bar, key in keys.items():
                timeline.append(((bar - 1) * 4 * TICKS, -1, mido.MetaMessage("key_signature", key=key)))
        # A final silent bar end keeps the last measure complete.
        timeline.append((bars * 4 * TICKS, 2, mido.MetaMessage("end_of_track")))
        timeline += events[track]
        timeline.sort(key=lambda item: (item[0], item[1]))
        out = mido.MidiTrack()
        now = 0
        for tick, _, message in timeline:
            if message.type == "end_of_track":
                continue
            out.append(message.copy(time=tick - now))
            now = tick
        out.append(mido.MetaMessage("end_of_track", time=bars * 4 * TICKS - now))
        song.tracks.append(out)
    song.save(path)


# --- MusicXML: written-spelling shapes MIDI cannot carry -----------------
_ACC = {-2: "flat-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}


def _note(head, *, chord=False, duration=4, kind="quarter", dots=0, voice=1,
          extra="", grace=False, notations=""):
    step, alter, octave = head
    return ("<note>" + ("<grace/>" if grace else "") + ("<chord/>" if chord else "")
            + f"<pitch><step>{step}</step>" + (f"<alter>{alter}</alter>" if alter else "")
            + f"<octave>{octave}</octave></pitch>"
            + ("" if grace else f"<duration>{duration}</duration>")
            + f"<voice>{voice}</voice><type>{kind}</type>" + "<dot/>" * dots
            + (f"<accidental>{_ACC[alter]}</accidental>" if alter else "")
            + extra + (f"<notations>{notations}</notations>" if notations else "") + "</note>")


def _heads(text):
    out = []
    for name in text.split():
        step, rest = name[0], name[1:]
        alter = rest.count("#") + 2 * rest.count("x") - rest.count("b")
        out.append((step, alter, int(rest.strip("#bx"))))
    return out


def _xml_chord(text, **kw):
    notations = kw.pop("first_notations", "")
    return "".join(_note(h, chord=i > 0, notations=(notations if i == 0 else kw.get("notations", "")),
                         **{k: v for k, v in kw.items() if k != "notations"})
                   for i, h in enumerate(_heads(text)))


def _rest(duration=4, kind="quarter", dots=0):
    return (f"<note><rest/><duration>{duration}</duration><voice>1</voice>"
            f"<type>{kind}</type>" + "<dot/>" * dots + "</note>")


XML_CASES = [
    # (measure, case, rh_content, attributes_for_rh)
    (1, "triple-g-flat-natural-sharp", 0, "Gb4 G4 G#4"),
    (1, "triple-f-plus-seconds", 1, "Fb4 F4 F#4 G4 G#4"),
    (1, "triple-b-double-flat", 2, "Bbb4 Bb4 B4"),
    (1, "double-accidentals", 3, "Fx4 A4 Cbb5"),
    (2, "alto-clef-chord", 0, "C4 D4 F4 F#4"),
    (2, "alto-clef-triple", 2, "Ab3 A3 A#3 C4"),
    (3, "tenor-clef-chord", 0, "A3 B3 B#3 D4"),
    (4, "treble-8vb-chord", 0, "E3 F#3 G3 G#3"),
    (5, "bass-clef-rh-chord", 0, "C3 Db3 D3 E3"),
    (6, "seven-sharps-double-sharp", 0, "Ex4 F#4 Fx4 A#4"),
    (7, "seven-flats-double-flat", 0, "Bbb3 Cb4 Dbb4 Fb4"),
    (8, "flat-key-unison-pair", 0, "Cb5 C5 Eb5"),
    (9, "identical-duplicate-spelling", 0, "E4 G4 G4"),
    (9, "enharmonic-same-pitch", 2, "E#4 F4 F#4"),
    (10, "dotted-half-cluster-down", 0, "C5 D5 E5 E#5"),
    # Bars 11-12 form their own exercise: the native view refuses a whole
    # exercise whose source has a grace chord or an arpeggio mark.
    (11, "grace-chord", 0, "C5 E5"),
    (11, "arpeggiated-chord", 2, "C4 E4 G4 C5"),
]
_CLEF = {2: ("C", 3, 0), 3: ("C", 4, 0), 4: ("G", 2, -1), 5: ("F", 4, 0), 6: ("G", 2, 0)}
_KEY = {6: 7, 7: -7, 8: -7, 9: 0}


def build_musicxml(path: Path) -> None:
    measures = []
    for number in range(1, 13):
        attrs = ""
        clef = _CLEF.get(number)
        if number == 1:
            clef = ("G", 2, 0)
        if number == 1 or clef or number in _KEY:
            parts = []
            if number == 1:
                parts.append("<divisions>4</divisions>")
            if number in _KEY or number == 1:
                parts.append(f"<key><fifths>{_KEY.get(number, 0)}</fifths></key>")
            if number == 1:
                parts.append("<time><beats>4</beats><beat-type>4</beat-type></time>")
            if clef:
                sign, line, octave = clef
                parts.append(f"<clef><sign>{sign}</sign><line>{line}</line>"
                             + (f"<clef-octave-change>{octave}</clef-octave-change>" if octave else "")
                             + "</clef>")
            attrs = "<attributes>" + "".join(parts) + "</attributes>"
        slots = {}
        for measure, _, beat, heads in XML_CASES:
            if measure == number:
                slots[beat] = heads
        body = []
        beat = 0
        while beat < 4:
            heads = slots.get(beat)
            if number == 10 and beat == 0:
                body.append(_xml_chord(heads, duration=12, kind="half", dots=1))
                body.append(_rest())
                break
            if heads is None:
                body.append(_rest())
            elif number == 11 and beat == 0:
                # A grace chord leading into the C5 E5 quarter chord.
                body.append(_xml_chord("D5 F5", grace=True, kind="eighth"))
                body.append(_xml_chord(heads))
            elif number == 11 and beat == 2:
                body.append(_xml_chord(heads, notations="<arpeggiate/>"))
            else:
                body.append(_xml_chord(heads))
            beat += 1
        measures.append(f'<measure number="{number}">{attrs}{"".join(body)}</measure>')
    left = []
    for number in range(1, 13):
        attrs = ("<attributes><divisions>4</divisions><key><fifths>0</fifths></key>"
                 "<time><beats>4</beats><beat-type>4</beat-type></time>"
                 "<clef><sign>F</sign><line>4</line></clef></attributes>") if number == 1 else ""
        left.append(f'<measure number="{number}">{attrs}<note><rest/><duration>16</duration>'
                    '<voice>1</voice><type>whole</type></note></measure>')
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n<score-partwise version="4.0">'
           '<work><work-title>G1 chord probe</work-title></work><part-list>'
           '<score-part id="RH"><part-name>Right Hand</part-name></score-part>'
           '<score-part id="LH"><part-name>Left Hand</part-name></score-part></part-list>'
           f'<part id="RH">{"".join(measures)}</part><part id="LH">{"".join(left)}</part>'
           '</score-partwise>\n')
    path.write_text(xml)


def cases() -> dict:
    return {
        "g1_chords.mid": [{"measure": bar, "case": name,
                           "beats": sorted({float(n[2]) for n in notes}),
                           "pitches": sorted({p for *_, p in notes})}
                          for bar, name, notes in MIDI_CASES],
        "g1_chords.musicxml": [{"measure": measure, "case": name, "beat": beat,
                                "heads": heads}
                               for measure, name, beat, heads in XML_CASES],
    }


if __name__ == "__main__":
    build_midi(HERE / "g1_chords.mid")
    build_midi(HERE / "g1_app_hard_chords.mid", APP_CASES, 4, {})
    build_musicxml(HERE / "g1_chords.musicxml")
    (HERE / "cases.json").write_text(json.dumps(cases(), indent=1) + "\n")
    print("wrote", HERE)
