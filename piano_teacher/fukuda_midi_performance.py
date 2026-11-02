"""MIDI-performance acquisition for Fukuda's score/performance DTW analysis.

The original Fukuda paper transcribes piano audio by CQT/NMF. In the
MIDI-only desktop product the performance is a direct sequence of MIDI
key-on/key-off events. This importer preserves tempo-map changes and
converts those events into the normal PlayedNote seconds-based model.
No microphone or sound transcription is involved.
"""
from __future__ import annotations

from collections import defaultdict,deque
from pathlib import Path

import mido

from .practice import PlayedNote


def load_performed_midi(path: str | Path) -> tuple[PlayedNote,...]:
    midi=mido.MidiFile(str(path))
    if midi.type==2 or midi.ticks_per_beat<=0:
        raise ValueError("Only synchronous PPQ MIDI performances can be aligned")
    seconds=0.
    microseconds=500000
    pressed=defaultdict(deque)
    notes=[]
    for message in mido.merge_tracks(midi.tracks):
        seconds+=mido.tick2second(message.time,midi.ticks_per_beat,microseconds)
        if message.type=="set_tempo":
            if message.tempo<=0:
                raise ValueError("Invalid performed MIDI tempo")
            microseconds=message.tempo
        if message.type not in ("note_on","note_off"):
            continue
        if message.channel==9:
            continue
        identity=(message.channel,message.note)
        if message.type=="note_on" and message.velocity>0:
            pressed[identity].append(seconds)
        else:
            if not pressed[identity]:
                raise ValueError("Orphan MIDI key release")
            onset=pressed[identity].popleft()
            if seconds<=onset:
                raise ValueError("Zero-length MIDI key press")
            notes.append(PlayedNote(message.note,onset,seconds))
    if any(pressed.values()):
        raise ValueError("MIDI performance contains unreleased keys")
    if not notes:
        raise ValueError("No piano key presses in performance")
    return tuple(sorted(notes,key=lambda n:(n.onset,n.pitch,n.release)))


def analyze_recorded_midi(score: str | Path, performance: str | Path) -> dict:
    """Compare performed MIDI against the complete original MIDI score."""
    from .music import load_midi, Phrase
    from .fukuda_midi import detect_midi_mistakes
    original=load_midi(score)
    last=max(original.bar_boundaries[-1],max(n.end for n in original.notes))
    source=Phrase(0,1,len(original.bar_boundaries)-1,
                  original.bar_boundaries[0],last,original.notes)
    played=load_performed_midi(performance)
    result=detect_midi_mistakes(source,played,bpm=original.bpm)
    return {
        "input_format":"midi-only",
        "source_title":original.title,
        "score_attacks":len(source.notes),
        "performed_attacks":len(played),
        "dtw_aligned_onsets":len(result.alignment),
        "mismatches":[{
            "source_id":x.source_id,"pitch":x.pitch,
            "onset_beat":x.onset_beat,"kind":x.kind}
            for x in result.mismatches],
        "extra_notes":[{"seconds":t,"pitch":p}
                       for t,p in result.extra_pitches],
        "note_source":"direct MIDI, no CQT/NMF or acoustic pitch estimation",
    }
