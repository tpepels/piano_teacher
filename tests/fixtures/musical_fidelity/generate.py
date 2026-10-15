"""Recreate the checked-in, deliberately small MIDI/MusicXML corpus.

The expected musical facts live separately in manifest.json.  This generator
does not import the application and does not calculate expected results.
"""
from pathlib import Path
from xml.sax.saxutils import escape

import mido

HERE = Path(__file__).resolve().parent


def midi(name, tracks, *, meter=(4, 4), meters=(), key=None, ppq=480, end=None):
    score = mido.MidiFile(ticks_per_beat=ppq)
    meta = [(0, mido.MetaMessage("set_tempo", tempo=500000)),
            (0, mido.MetaMessage("time_signature", numerator=meter[0], denominator=meter[1]))]
    meta += [(round(beat * ppq), mido.MetaMessage("time_signature", numerator=num, denominator=den))
             for beat, num, den in meters]
    if key is not None:
        meta.append((0, mido.MetaMessage("key_signature", key=key)))
    track = mido.MidiTrack()
    previous = 0
    for tick, message in sorted(meta, key=lambda item: item[0]):
        track.append(message.copy(time=tick - previous))
        previous = tick
    score.tracks.append(track)
    for title, notes in tracks:
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=title)])
        events = []
        for start, stop, pitch in notes:
            events.append((round(start * ppq), 1, pitch))
            if stop is not None:
                events.append((round(stop * ppq), 0, pitch))
        previous = 0
        for tick, on, pitch in sorted(events):
            track.append(mido.Message("note_on" if on else "note_off", note=pitch,
                                      velocity=80 if on else 0, time=tick - previous))
            previous = tick
        track.append(mido.MetaMessage("end_of_track", time=max(0, round((end or 0) * ppq) - previous)))
        score.tracks.append(track)
    score.save(HERE / (name + ".mid"))


def note(step="C", octave=4, duration=4, *, alter=None, voice=1, staff=None,
         tie=None, chord=False, kind="quarter", tuplet=None, dots=0):
    pitch = f"<step>{step}</step>" + ("" if alter is None else f"<alter>{alter}</alter>") + f"<octave>{octave}</octave>"
    return ("<note>" + ("<chord/>" if chord else "") + f"<pitch>{pitch}</pitch><duration>{duration}</duration>"
            + ("" if tie is None else f'<tie type="{tie}"/>')
            + f"<voice>{voice}</voice><type>{kind}</type>" + "<dot/>" * dots
            + ("" if staff is None else f"<staff>{staff}</staff>")
            + ("" if tuplet is None else f"<time-modification><actual-notes>{tuplet[0]}</actual-notes><normal-notes>{tuplet[1]}</normal-notes></time-modification>")
            + "</note>")


def rest(duration, *, voice=1, staff=None, kind="whole", dots=0):
    return (f"<note><rest/><duration>{duration}</duration><voice>{voice}</voice><type>{kind}</type>"
            + "<dot/>" * dots
            + ("" if staff is None else f"<staff>{staff}</staff>") + "</note>")


def attributes(*, meter=(4, 4), divisions=4, key=None, clef=("G", 2), grand=False):
    return (f"<attributes><divisions>{divisions}</divisions>"
            + ("" if key is None else f"<key><fifths>{key}</fifths></key>")
            + f"<time><beats>{meter[0]}</beats><beat-type>{meter[1]}</beat-type></time>"
            + ("<staves>2</staves>" if grand else "")
            + (f'<clef number="1"><sign>G</sign><line>2</line></clef><clef number="2"><sign>F</sign><line>4</line></clef>' if grand
               else f"<clef><sign>{clef[0]}</sign><line>{clef[1]}</line></clef>") + "</attributes>")


def measure(number, content, *, pickup=False):
    return f'<measure number="{number}"' + (' implicit="yes"' if pickup else "") + f">{content}</measure>"


def xml(name, parts):
    definitions = "".join(f'<score-part id="P{i}"><part-name>{escape(title)}</part-name></score-part>'
                          for i, (title, _) in enumerate(parts))
    body = "".join(f'<part id="P{i}">{content}</part>' for i, (_, content) in enumerate(parts))
    (HERE / (name + ".musicxml")).write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<score-partwise version="4.0"><work><work-title>'
        + name + f"</work-title></work><part-list>{definitions}</part-list>{body}</score-partwise>\n")


def main():
    midi("midi_four_four", [("Right Hand", [(0, 1, 60), (1, 2, 62), (2, 3, 64), (3, 4, 65)])])
    midi("midi_three_four", [("Right Hand", [(0, 1, 60), (1, 2, 64), (2, 3, 67), (3, 6, 72)])], meter=(3, 4))
    midi("midi_six_eight", [("Right Hand", [(0, .5, 60), (.5, 1, 62), (1, 1.5, 64), (1.5, 3, 67)])], meter=(6, 8))
    midi("midi_mixed_meter", [("Right Hand", [(0, 3, 60), (3, 7, 62), (7, 11, 64)])], meter=(3, 4), meters=((3, 4, 4),))
    midi("midi_repeated_attacks", [("Right Hand", [(0, 1, 60), (1, 2, 60), (2, 2.5, 60), (2.5, 3, 60), (3, 4, 60)])])
    midi("midi_chords", [("Right Hand", [(0, 2, 60), (0, 2, 64), (0, 2, 67), (2, 4, 62), (2, 4, 65), (2, 4, 69)])])
    midi("midi_parallel_unisons", [("Right Hand A", [(0, 2, 60)]), ("Right Hand B", [(0, 1, 60), (1, 2, 60)])])
    midi("midi_cross_hand_unisons", [("Right Hand", [(0, 1, 60), (2, 4, 64)]), ("Left Hand", [(0, 2, 60), (2, 4, 48)])])
    midi("midi_held_crossbar", [("Right Hand", [(0, 6, 60), (6, 8, 64)])])
    midi("midi_sparse_rests", [("Right Hand", [(2, 3, 60), (6, 7, 64)])], end=8)
    midi("midi_explicit_gb_key", [("Right Hand", [(0, 1, 66), (1, 2, 70)])], key="Gb")
    midi("midi_unknown_key", [("Right Hand", [(0, 1, 61), (1, 2, 66)])])
    midi("midi_high_left", [("Left Hand", [(0, 1, 84), (1, 2, 88)])])
    midi("midi_low_right", [("Right Hand", [(0, 1, 36), (1, 2, 40)])])
    midi("midi_raw_ppq997", [("Right Hand", [(1 / 997, 18 / 997, 60), (31 / 997, 47 / 997, 64), (499 / 997, 700 / 997, 67)])], ppq=997)
    midi("midi_triplets", [("Right Hand", [(0, 1 / 3, 60), (1 / 3, 2 / 3, 62), (2 / 3, 1, 64), (1, 2, 67)])])
    xml("xml_pickup", [("Right Hand", measure(0, attributes() + note(), pickup=True)
                       + measure(1, note("D", duration=16, kind="whole")))])
    xml("xml_mixed_meter", [("Right Hand", measure(1, attributes(meter=(3, 4)) + note(duration=12, kind="half", dots=1))
                            + measure(2, attributes() + note("D", duration=16, kind="whole")))])
    xml("xml_parallel_tied_voices", [("Right Hand", measure(1, attributes() + note(duration=16, kind="whole", tie="start")
               + "<backup><duration>16</duration></backup>" + rest(8, voice=2, kind="half") + note(duration=8, voice=2, kind="half", tie="start"))
               + measure(2, note(duration=8, kind="half", tie="stop") + rest(8, kind="half")
               + "<backup><duration>16</duration></backup>" + note(duration=4, voice=2, tie="stop") + rest(12, voice=2, kind="half", dots=1)))])
    xml("xml_chord_ties", [("Right Hand", measure(1, attributes() + "".join(note(s, duration=16, kind="whole", tie="start", chord=i > 0) for i, s in enumerate("CEG")))
              + measure(2, "".join(note(s, duration=8, kind="half", tie="stop", chord=i > 0) for i, s in enumerate("CEG")) + rest(8, kind="half")))])
    xml("xml_keys_spelling", [("Right Hand", measure(1, attributes(key=-5) + note("D", duration=16, alter=-1, kind="whole"))
                             + measure(2, attributes(key=4) + note("G", duration=16, alter=1, kind="whole")))])
    xml("xml_crossed_named_hands", [("Right Hand", measure(1, attributes(clef=("F", 4)) + note("C", 3, 16, kind="whole"))),
                                    ("Left Hand", measure(1, attributes() + note("C", 5, 16, kind="whole")))])
    xml("xml_grandstaff_voices", [("Piano", measure(1, attributes(grand=True) + note("C", 5, 16, staff=1, kind="whole")
                                  + "<backup><duration>16</duration></backup>" + note("C", 3, 16, voice=2, staff=2, kind="whole")))])
    xml("xml_trailing_rests", [("Right Hand", measure(1, attributes() + note() + rest(12, kind="half", dots=1))
                              + measure(2, rest(16)) + measure(3, rest(16)))])
    xml("xml_quintuplets", [("Right Hand", measure(1, attributes(divisions=5)
                             + "".join(note(s, duration=1, kind="16th", tuplet=(5, 4)) for s in "CDEFG") + rest(15, kind="half", dots=1)))])
    upper = "".join(measure(i + 1, (attributes() if i == 0 else "")
                            + "".join(note(s, 5, 4) for s in "CDEG")) for i in range(48))
    lower = "".join(measure(i + 1, (attributes(clef=("F", 4)) if i == 0 else "")
                            + note("C", 3, 16, kind="whole")) for i in range(48))
    xml("xml_long_multipage", [("Right Hand", upper), ("Left Hand", lower)])
    xml("unsupported_orphan_tie", [("Right Hand", measure(1, attributes() + note(duration=16, kind="whole", tie="stop")))])
    xml("unsupported_microtone", [("Right Hand", measure(1, attributes() + note(duration=16, alter=".5", kind="whole")))])
    midi("unsupported_unclosed_midi", [("Right Hand", [(0, None, 60)])], end=4)
    midi("unsupported_ambiguous_overlap", [("Right Hand", [(0, 3, 60), (1, 2, 60)])])


if __name__ == "__main__":
    main()
