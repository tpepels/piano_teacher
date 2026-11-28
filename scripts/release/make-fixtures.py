"""Existing native two-hand and meter-specific player fixtures."""

from pathlib import Path

import mido

target = Path.home() / "Music" / "Piano Teacher" / "phase6_native_fixture.mid"
target.parent.mkdir(parents=True, exist_ok=True)
piece = mido.MidiFile(type=1, ticks_per_beat=480)
meta = mido.MidiTrack()
piece.tracks.append(meta)
meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
meta.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
meta.append(mido.MetaMessage("end_of_track", time=0))

def add_hand(channel, notes):
    track = mido.MidiTrack()
    piece.tracks.append(track)
    track.append(mido.Message("program_change", channel=channel, program=0, time=0))
    events = []
    for at, pitch, length in notes:
        events.append((at, 1, mido.Message("note_on", channel=channel, note=pitch, velocity=84)))
        events.append((at+length, 0, mido.Message("note_off", channel=channel, note=pitch, velocity=0)))
    last = 0
    for at, _, message in sorted(events, key=lambda item:(item[0],item[1])):
        message.time = at-last
        track.append(message)
        last = at
    track.append(mido.MetaMessage("end_of_track", time=0))

right = [(bar*1920+beat*480, [72,74,76,77,79,77,76,74][(bar+beat)%8], 400)
         for bar in range(8) for beat in range(4)]
left = [(bar*1920+beat*960, [48,55,52,55][(bar+beat)%4], 800)
        for bar in range(8) for beat in range(2)]
add_hand(0,right)
add_hand(1,left)
piece.save(target)
print("CREATED_FIXTURE", target)

# Small source for the full-scene synthetic physical MIDI journey.
# Two quickly spaced attacks start at the documented 50% floor so the
# journey exercises the return to Free after two failures there.
short = mido.MidiFile(type=1,ticks_per_beat=480)
short_meta = mido.MidiTrack()
short.tracks.append(short_meta)
short_meta.append(mido.MetaMessage("time_signature",numerator=4,denominator=4))
short_meta.append(mido.MetaMessage("set_tempo",tempo=mido.bpm2tempo(80)))
notes = mido.MidiTrack()
short.tracks.append(notes)
notes.extend([
    mido.Message("note_on",channel=0,note=72,velocity=84,time=0),
    mido.Message("note_off",channel=0,note=72,velocity=0,time=120),
    mido.Message("note_on",channel=0,note=79,velocity=84,time=120),
    mido.Message("note_off",channel=0,note=79,velocity=0,time=240),
])
short_path = target.parent / "ci_state_journey.mid"
short.save(short_path)
print("CREATED_FAKE_MIDI_JOURNEY",short_path)

# The same journey in 2/4: a bar is only two beats, so the count-in and
# the rest between repeats are short (owner report 2026-11-24).
two = mido.MidiFile(type=1,ticks_per_beat=480)
two_meta = mido.MidiTrack()
two.tracks.append(two_meta)
two_meta.append(mido.MetaMessage("time_signature",numerator=2,denominator=4))
two_meta.append(mido.MetaMessage("set_tempo",tempo=mido.bpm2tempo(80)))
two_notes = mido.MidiTrack()
two.tracks.append(two_notes)
two_notes.extend([
    mido.Message("note_on",channel=0,note=72,velocity=84,time=0),
    mido.Message("note_off",channel=0,note=72,velocity=0,time=120),
    mido.Message("note_on",channel=0,note=79,velocity=84,time=120),
    mido.Message("note_off",channel=0,note=79,velocity=0,time=240),
])
two.save(target.parent / "ci_state_journey_two_four.mid")
print("CREATED_FAKE_MIDI_JOURNEY_TWO_FOUR")
