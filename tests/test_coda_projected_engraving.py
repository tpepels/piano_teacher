"""Opt-in real Verovio SVG evidence for Coda source-timed notation.

Uses the production engraving path and its independently checked source
attack mapping, not placeholder geometry or mock SVG. Does not launch Godot
or run the corpus. Original score is retained as its own source object.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Phrase
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceDotted,CodaReferenceChordification,CodaReferenceSlowdown,
)
from piano_teacher.research.coda_score_projection import project_coda_score


SOURCE=Path(__file__).parent/"fixtures/research/coda_four_families.musicxml"


@pytest.mark.parametrize("kind",["dotted-long","dotted-short","chord","slow-2","slow-4"])
def test_coda_real_engraving_retains_identical_note_ids_and_beat_clock(kind,tmp_path):
    piece=load_musicxml(SOURCE,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,8,piece.notes),
        tuple(range(len(piece.notes))))
    if kind=="chord":
        plan=CodaReferenceChordification(8).transform(
            original,boundaries=piece.bar_boundaries,quantization=4,
            source_musicxml=piece.source_musicxml).timing
        family="chordification"
    elif kind.startswith("slow"):
        plan=CodaReferenceSlowdown(int(kind[-1])).transform(original).timing
        family="tempo-shaping"
    else:
        plan=CodaReferenceDotted(kind=="dotted-long").transform(
            original,boundaries=piece.bar_boundaries,quantization=4,
            source_musicxml=piece.source_musicxml).timing
        family="dotted-rhythms"
    stage=project_coda_score(piece,plan,reference_family=family,bpm=80,revision=5)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"preproc"))
    score=artifacts.engraving(stage.selection)
    model=artifacts.source_model(stage.selection)
    expected={note.source_id for note in piece.notes}
    assert len(expected)==16
    assert set(score.layout["attack_map"])==expected
    assert score.layout["beats"]==pytest.approx(stage.tempo_map.duration_beats)
    assert score.pages
    assert len(score.pages)<8
    assert len(model["notes"])==len(expected)
    assert all(note["id"] in score.layout["attack_map"] for note in model["notes"])
    assert all(0<=glyph["x"]<=1 and 0<=glyph["y"]<=1
               for glyph in score.layout["notes"])
    output=tmp_path/"engraving-proof"
    output.mkdir(exist_ok=True)
    (output/f"{kind}.musicxml").write_text(artifacts.notation_musicxml(stage.selection))
    for i,svg in enumerate(score.pages):
        root=ET.fromstring(svg)
        assert root.tag.endswith("svg")
        assert "viewBox" in root.attrib
        assert len(list(root.iter()))>60
        (output/f"{kind}-page-{i}.svg").write_text(svg)
    # A real Verovio-derived glyph must be linked to every graded note.
    ink={glyph["source_id"] for glyph in score.layout["notes"]
         if glyph.get("is_attack")}
    assert ink==expected


def test_actual_coda_wav_live_input_and_missed_note_use_svg_clock(tmp_path):
    """No mock renderer/audio/grading: one dotted stage, real Verovio/WAV."""
    import wave

    from piano_teacher.application.listen_session import ListenSession
    from piano_teacher.demo import DemoAudioCache
    from piano_teacher.live_input_view import LiveInputView
    from piano_teacher.measure_grid import phrase_grid
    from piano_teacher.practice import PlayedNote
    from piano_teacher.timed_assessment import timed_live_marks

    piece=load_musicxml(SOURCE,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,8,piece.notes),
        tuple(range(len(piece.notes))))
    plan=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,quantization=4,
        source_musicxml=piece.source_musicxml).timing
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",
                             bpm=80,revision=9)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"preproc"))
    engraving=artifacts.engraving(stage.selection)
    canonical={n.source_id:n for n in stage.variant.notes}
    assert set(engraving.layout["attack_map"])==set(canonical)

    # The application's actual sample/synthesis cache renders the same
    # selected exercise that the score and MIDI grader consume.
    cache=DemoAudioCache(tmp_path/"actual-audio",sample_rate=8000)
    session=ListenSession(tmp_path/"actual-audio",cache=cache)
    token=session.prepare(stage.listen_selection())
    session.thread.join(timeout=8)
    assert not session.thread.is_alive()
    assert session.take_failure() is None
    snapshot=session.snapshot()
    assert snapshot["audio_available"]
    assert snapshot["duration_seconds"]==pytest.approx(stage.tempo_map.duration_seconds)
    with wave.open(str(session.audio_path(token)),"rb") as wav:
        assert wav.getframerate()==8000
        assert wav.getnframes()/8000==pytest.approx(
            stage.tempo_map.duration_seconds,abs=.00013)
        assert any(wav.readframes(1600))

    target=next(note for note in stage.variant.notes
                if note.hand=="right" and note.pitch==64)
    # Reuse the actual transformed stage clock for a physical MIDI onset.
    view=LiveInputView()
    view.receive(
        pitch=target.pitch,is_on=True,
        now=100+stage.tempo_map.seconds_at(target.start),
        phrase=stage.variant.phrase,hand="right",bpm=80,from_beat=0,
        run_at=100,running=True,paused=False,preview=False,mode="practice",
        transport_id=11,tempo_map=stage.tempo_map)
    assert view.events[-1]["source_id"]==target.source_id
    assert view.events[-1]["status"]=="on_time"

    played=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                       stage.tempo_map.seconds_at(n.end))
            for n in stage.variant.notes
            if n.hand=="right" and n.source_id!=target.source_id]
    marks=timed_live_marks(
        stage.variant.phrase,"right",stage.tempo_map,played,
        from_beat=0,elapsed_seconds=stage.tempo_map.duration_seconds,
        grid=phrase_grid(stage.variant.phrase,stage.piece.bar_boundaries),
        layout=engraving.layout)
    missed=[m for m in marks if m["source_id"]==target.source_id
            and m["status"]=="missed"]
    assert missed
    assert missed[0]["note_id"]==engraving.layout["attack_map"][target.source_id]
    assert stage.original_piece.notes==piece.notes


def test_real_authored_eighth_beam_groups_survive_selected_coda_stage(tmp_path):
    """Use the checked-in independent beam MusicXML, not a generated example."""
    source=Path(__file__).parent/"fixtures/connector_pixels/beams/score.musicxml"
    piece=load_musicxml(source,bpm=80)
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,0,
                  piece.bar_boundaries[-1],piece.notes)
    original=ExerciseVariant("original",phrase,tuple(range(len(phrase.notes))))
    plan=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,
        quantization=8,source_musicxml=piece.source_musicxml).timing
    # Beams protect all original attacks in this intentionally beamed voice.
    assert plan.exercise_phrase.notes==original.notes
    stage=project_coda_score(
        piece,plan,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"beam"))
    xml=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    actual=[(n.findtext("pitch/step"),[b.text for b in n.findall("beam")])
            for n in xml.findall("./part[@id='RH']/measure/note")
            if n.find("pitch") is not None]
    authored=ET.fromstring(piece.source_musicxml)
    expected=[(n.findtext("pitch/step"),[b.text for b in n.findall("beam")])
              for n in authored.findall("./part[@id='RH']/measure/note")
              if n.find("pitch") is not None]
    assert actual==expected
    score=artifacts.engraving(stage.selection)
    assert set(score.layout["attack_map"])=={
        n.source_id for n in piece.notes}
    assert score.pages and len(score.pages)<=2


def test_unchanged_authored_slur_and_staccato_are_actual_verovio_ink(tmp_path):
    """Other hand's Coda rhythm changes while the slurred RH phrase stays."""
    from piano_teacher.exercise_contracts import OriginalTiming

    root=ET.fromstring(SOURCE.read_text())
    notes=[n for n in root.findall("./part")[0].findall("./measure")[0].findall("note")
           if n.find("pitch") is not None]
    start=ET.SubElement(notes[0],"notations")
    ET.SubElement(start,"slur",type="start",number="1")
    articulations=ET.SubElement(start,"articulations")
    ET.SubElement(articulations,"staccato")
    stop=ET.SubElement(notes[3],"notations")
    ET.SubElement(stop,"slur",type="stop",number="1")
    fixture=tmp_path/"authored-arc.musicxml"
    fixture.write_text(ET.tostring(root,encoding="unicode"))
    piece=load_musicxml(fixture,bpm=80)
    original=ExerciseVariant("original",Phrase(1,1,2,0,8,piece.notes),
                             tuple(range(len(piece.notes))))
    result=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,quantization=4,
        source_musicxml=piece.source_musicxml)
    assert result.changed_sources
    stage=project_coda_score(
        piece,result.timing,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"arc-cache"))
    notation=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert len(notation.findall(".//slur[@type='start']"))==1
    assert len(notation.findall(".//slur[@type='stop']"))==1
    assert len(notation.findall(".//staccato"))==1
    rendered=artifacts.engraving(stage.selection)
    assert set(rendered.layout["attack_map"])=={
        n.source_id for n in piece.notes}
    svg=ET.fromstring(rendered.pages[0])
    classes={token for node in svg.iter() for token in
             node.get("class","").split()}
    assert "slur" in classes
    (tmp_path/"authored-arc.svg").write_text(rendered.pages[0])


def test_real_parallel_voice_source_ties_have_independent_verovio_connector_ink(tmp_path):
    """Original source barline ties in two separate voices, no inferred ties."""
    from piano_teacher.exercise_contracts import OriginalTiming

    source=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"
    piece=load_musicxml(source,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,len(piece.bar_boundaries)-1,0,
                           piece.bar_boundaries[-1],piece.notes),
        tuple(range(len(piece.notes))))
    plan=OriginalTiming().transform(original)
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"parallel-ties"))
    xml=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert len(xml.findall(".//tie[@type='start']"))>=2
    assert len(xml.findall(".//tie[@type='stop']"))>=2
    score=artifacts.engraving(stage.selection)
    assert set(score.layout["attack_map"])=={
        n.source_id for n in piece.notes}
    roots=[ET.fromstring(page) for page in score.pages]
    tie_groups=[node for root in roots for node in root.iter()
                if "tie" in node.get("class","").split()]
    assert len(tie_groups)>=2
    (tmp_path/"parallel-voices.svg").write_text(score.pages[0])


def test_real_authored_triplet_group_engraves_on_unmodified_source_attacks(tmp_path):
    """Real 3:2 eighth group plus independently dotted left hand."""
    source=Path(__file__).parent/"fixtures/research/coda_authored_triplet.musicxml"
    piece=load_musicxml(source,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,1,0,4,piece.notes),
        tuple(range(len(piece.notes))))
    plan=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,quantization=12,
        source_musicxml=piece.source_musicxml).timing
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"real-triplets"))
    xml=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert len(xml.findall(".//notations/tuplet[@type='start']"))==1
    assert len(xml.findall(".//notations/tuplet[@type='stop']"))==1
    score=artifacts.engraving(stage.selection)
    assert set(score.layout["attack_map"])=={n.source_id for n in original.notes}
    classes={token for svg in score.pages for elem in ET.fromstring(svg).iter()
             for token in elem.get("class","").split()}
    assert "tuplet" in classes
    for i,svg in enumerate(score.pages):
        (tmp_path/f"real-triplet-{i}.svg").write_text(svg)


@pytest.mark.parametrize("factor", [2,4])
def test_real_mixed_meter_coda_written_slowdown_svg(factor,tmp_path):
    source=Path(__file__).parent/"fixtures/research/coda_mixed_meter.musicxml"
    piece=load_musicxml(source,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,5,piece.notes),
        tuple(range(len(piece.notes))))
    plan=CodaReferenceSlowdown(factor).transform(original).timing
    stage=project_coda_score(piece,plan,reference_family="tempo-shaping",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/f"mixed-{factor}"))
    model=artifacts.source_model(stage.selection)
    assert [m["meter"] for m in model["measures"]]==(
        [[3,4]]*factor + [[2,4]]*factor)
    score=artifacts.engraving(stage.selection)
    assert score.pages
    assert set(score.layout["attack_map"])=={n.source_id for n in original.notes}
    assert score.layout["beats"]==factor*5
    for i,svg in enumerate(score.pages):
        root=ET.fromstring(svg)
        assert root.tag.endswith("svg")
        (tmp_path/f"mixed-meter-x{factor}-{i}.svg").write_text(svg)


@pytest.mark.parametrize("actual,normal",[(5,4),(7,4)])
def test_source_authored_quintuplet_septuplet_produces_real_svg(
        actual,normal,tmp_path):
    source=Path(__file__).parent / "fixtures/research" / f"coda_group_{actual}_{normal}.musicxml"
    piece=load_musicxml(source,bpm=80)
    original=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    # Original quintuplet/septuplet remains intact; LH can change.
    plan=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,
        quantization=20 if actual==5 else 70,
        source_musicxml=piece.source_musicxml).timing
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"coda-ratio"))
    rendered=artifacts.engraving(stage.selection)
    assert set(rendered.layout["attack_map"])=={
        n.source_id for n in original.notes}
    classes={token for svg in rendered.pages for elem in ET.fromstring(svg).iter()
             for token in elem.get("class","").split()}
    assert "tuplet" in classes
    assert rendered.pages
    for i,svg in enumerate(rendered.pages):
        (tmp_path/f"coda-{actual}-{normal}-{i}.svg").write_text(svg)


def test_retimed_slur_keeps_its_real_verovio_curve(tmp_path):
    from dataclasses import replace
    from piano_teacher.exercise_contracts import OriginalTiming,TimingPlan

    root=ET.fromstring(SOURCE.read_text())
    right=[n for n in root.findall("./part")[0].findall("./measure")[0].findall("note")
           if n.find("pitch") is not None]
    a=ET.SubElement(right[0],"notations")
    ET.SubElement(a,"slur",type="start",number="1")
    b=ET.SubElement(right[-1],"notations")
    ET.SubElement(b,"slur",type="stop",number="1")
    filename=tmp_path/"retimed-slur.musicxml"
    filename.write_text(ET.tostring(root,encoding="unicode"))
    piece=load_musicxml(filename,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,8,piece.notes),
        tuple(range(len(piece.notes))))
    default=OriginalTiming().transform(original)
    events=list(default.events)
    for n in original.notes:
        if n.hand!="right" or n.start>=4:
            continue
        idx=next(i for i,x in enumerate(original.notes) if x.source_id==n.source_id)
        start=(0,1.5,2,3.5)[int(n.start)]
        duration=(1.5,.5,1.5,.5)[int(n.start)]
        events[idx]=replace(events[idx],exercise_start=start,
                            exercise_end=start+duration)
    transformed=TimingPlan("retimed-slur",original,tuple(events),8)
    stage=project_coda_score(
        piece,transformed,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"slur-model"))
    score=artifacts.engraving(stage.selection)
    assert set(score.layout["attack_map"])=={n.source_id for n in original.notes}
    classes={token for svg in score.pages for elem in ET.fromstring(svg).iter()
             for token in elem.get("class","").split()}
    assert "slur" in classes
    (tmp_path/"retimed-source-slur.svg").write_text(score.pages[0])
