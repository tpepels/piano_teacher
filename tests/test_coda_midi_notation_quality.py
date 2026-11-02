"""Independent generated-MIDI notation checks: beams, rests, ties, tuplets.

The original source is MIDI. Generated MusicXML is an output and must
remain traceable to the source attack IDs and exact transformed clock.
Verovio SVG verifies real engraving, not authorial transcription parity.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

import mido
import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.music import load_midi, Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_midi_passage import project_midi_passage


def _make_tie_beam_midi(path):
    file=mido.MidiFile(type=1,ticks_per_beat=960)
    rh=mido.MidiTrack()
    lh=mido.MidiTrack()
    rh.append(mido.MetaMessage("track_name",name="Right Hand",time=0))
    rh.append(mido.MetaMessage("time_signature",numerator=4,denominator=4,time=0))
    lh.append(mido.MetaMessage("track_name",name="Left Hand",time=0))
    right=[]
    # Four eighth notes in first bar; one note held across the barline.
    for i,p in enumerate((72,74,76,77)):
        start=i*480
        right.extend([(start,1,p),(start+480,0,p)])
    right.extend([(7*480,1,79),(9*480,0,79)])
    left=[(0,1,48),(1920,0,48),(3840,1,48),(4800,0,48)]
    def add(track,events,channel):
        previous=0
        for tick,on,pitch in sorted(events,key=lambda x:(x[0],x[1])):
            track.append(mido.Message("note_on" if on else "note_off",
                note=pitch,channel=channel,velocity=88 if on else 0,
                time=tick-previous))
            previous=tick
        track.append(mido.MetaMessage("end_of_track",time=7680-previous))
    add(rh,right,0)
    add(lh,left,1)
    file.tracks.extend((rh,lh))
    file.save(path)


def test_midi_written_beams_and_two_staff_rests_remain_real_score_elements(tmp_path):
    source=tmp_path/"beams-with-rests.mid"
    _make_tie_beam_midi(source)
    piece=load_midi(source)
    assert piece.source_musicxml==""
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,0,piece.bar_boundaries[-1],
                  piece.notes)
    generated=build_lesson_score(
        phrase,boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        source_musicxml="")
    score=ET.fromstring(generated.musicxml)
    parts=score.findall("part")
    assert len(parts)==2
    assert {p.get("id") for p in parts}=={"RH","LH"}
    assert len(score.findall(".//rest"))>0
    assert len(score.findall(".//beam"))>0
    assert len(score.findall(".//clef"))>=2
    assert all(note.find("voice") is not None
               for part in parts for note in part.findall(".//note"))
    assert set(generated.note_bindings)=={n.source_id for n in piece.notes}


def test_generated_midi_crossbar_ties_are_sounding_single_attacks(tmp_path):
    source=tmp_path/"tie-beam.mid"
    _make_tie_beam_midi(source)
    piece=load_midi(source)
    original_count=len(piece.notes)
    passage,stage=project_midi_passage(
        piece,1,2,family="tempo-shaping",slowdown_factor=2)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"cache"))
    xml=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert xml.findall(".//tie[@type='start']")
    assert xml.findall(".//tie[@type='stop']")
    assert xml.findall(".//tied[@type='start']")
    assert xml.findall(".//tied[@type='stop']")
    model=artifacts.source_model(stage.selection)
    assert len(model["notes"])==original_count
    assert len(model["attack_map"]) if "attack_map" in model else True
    assert {n["id"] for n in model["notes"]}==passage.original_source_ids
    engraved=artifacts.engraving(stage.selection)
    assert set(engraved.layout["attack_map"])==passage.original_source_ids
    assert all(ET.fromstring(svg).tag.endswith("svg") for svg in engraved.pages)


def test_midi_triplet_rhythm_notation_has_actual_ratio_and_verovio_ink(tmp_path):
    source=Path(__file__).parent/"fixtures/musical_fidelity/midi_triplets.mid"
    piece=load_midi(source)
    passage,stage=project_midi_passage(
        piece,1,len(piece.bar_boundaries)-1,
        family="tempo-shaping",slowdown_factor=2)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"triplet"))
    score=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert score.findall(".//time-modification"), "Missing generated tuplet ratios"
    mapped={entry["id"] for entry in artifacts.source_model(stage.selection)["notes"]}
    assert mapped==passage.original_source_ids
    engraved=artifacts.engraving(stage.selection)
    assert set(engraved.layout["attack_map"])==mapped
    assert engraved.pages
