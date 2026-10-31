"""Bounded genuine MusicXML → Coda score, Listen, and MIDI grade.

All three objects share one TimingPlan; original Piece/mastery remains
immutable. The test verifies real MusicXML notes, authored rests,
source context and deliberately damaged source markup rejection.
"""
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.application.listen_session import ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.demo import DemoAudio
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.exercise_contracts import OriginalTiming
from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceChordification, CodaReferenceDotted, CodaReferenceSlowdown,
)
from piano_teacher.research.coda_score_projection import project_coda_score


SOURCE=Path(__file__).parent/"fixtures/research/coda_four_families.musicxml"


def context():
    original=load_musicxml(SOURCE,bpm=80)
    phrase=Phrase(1,1,2,0,8,original.notes)
    variant=ExerciseVariant("original",phrase,tuple(range(len(phrase.notes))))
    return original,variant


class Capture:
    def __init__(self,path):
        self.path=path
        self.calls=[]

    def render(self,variant,bpm):
        self.calls.append((variant,bpm))
        return DemoAudio(self.path,variant.phrase.end*60/bpm,
                         0,8000,"fake-reference-sample")


@pytest.mark.parametrize("kind",["dotted-long","dotted-short","chord","slow-2","slow-4"])
def test_coda_transformed_musicxml_listen_and_grading_share_clock(kind,tmp_path):
    original,variant=context()
    if kind.startswith("slow"):
        factor=int(kind[-1])
        result=CodaReferenceSlowdown(factor).transform(variant)
        family="tempo-shaping"
    elif kind=="chord":
        result=CodaReferenceChordification(8).transform(
            variant,boundaries=original.bar_boundaries,quantization=4,
            source_musicxml=original.source_musicxml)
        family="chordification"
    else:
        result=CodaReferenceDotted(kind=="dotted-long").transform(
            variant,boundaries=original.bar_boundaries,quantization=4,
            source_musicxml=original.source_musicxml)
        family="dotted-rhythms"
    assert result.timing.exercise_phrase.notes!=variant.notes
    stage=project_coda_score(original,result.timing,reference_family=family,
                             bpm=80,revision=8)
    assert stage.original_piece is original
    assert stage.timing.original==variant
    assert stage.piece is not original
    assert ET.tostring(ET.fromstring(original.source_musicxml)) == (
        ET.tostring(ET.fromstring(SOURCE.read_text())))
    assert stage.selection.transformed_rhythm
    assert stage.piece.bar_boundaries[-1]==result.timing.duration_beats
    assert len(stage.piece.bar_boundaries)==(5 if kind=="slow-2"
                                              else 9 if kind=="slow-4" else 3)
    assert stage.tempo_map.duration_beats==result.timing.duration_beats

    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"projection-cache"))
    xml=artifacts.notation_musicxml(stage.selection)
    root=ET.fromstring(xml)
    assert root.tag=="score-partwise"
    assert len(root.findall("part"))==2
    assert len(root.findall(".//part/measure"))==len(stage.piece.bar_boundaries[:-1])*2
    model=artifacts.source_model(stage.selection)
    by_id={item["id"]:item for item in model["notes"]}
    assert set(by_id)=={n.source_id for n in original.notes}
    assert len(by_id)==16
    assert model["duration_beats"]==stage.tempo_map.duration_beats
    for note in stage.variant.notes:
        assert by_id[note.source_id]["onset_beats"]==pytest.approx(note.start)
        assert by_id[note.source_id]["duration_beats"]==pytest.approx(note.end-note.start)
    attacks={symbol["source_id"] for symbol in model["notation_events"]
             if symbol["kind"]=="note" and symbol["is_attack"]}
    assert attacks==set(by_id)
    assert any(symbol["kind"]=="rest" for symbol in model["notation_events"])
    # A key alteration authored at the start of the second source measure
    # survives where that same musical change now occurs, after x2/x4
    # source-to-exercise time expansion.
    second_source_beat=4*(int(kind[-1]) if kind.startswith("slow") else 1)
    assert any(
        any(abs(m["start_beat"]-second_source_beat)<1e-7
            and m["keys"].get("right")==-1 for m in model["measures"])
        for _ in (0,)
    )
    assert stage.piece.source_musicxml != ""  # explicit authored rests retained
    assert ET.tostring(ET.fromstring(original.source_musicxml)) == (
        ET.tostring(ET.fromstring(SOURCE.read_text())))

    played=[PlayedNote(note.pitch,stage.tempo_map.seconds_at(note.start),
                       stage.tempo_map.seconds_at(note.end))
            for note in stage.variant.notes]
    assessment=stage.grade(played,hand="both")
    assert assessment.assessment.clean
    assert {n.note.source_id for n in assessment.assessment.notes}==set(by_id)

    capturer=Capture(tmp_path/"audio.wav")
    listen=ListenSession(tmp_path/"rendered",cache=capturer)
    token=listen.prepare(stage.listen_selection())
    listen.thread.join(timeout=2)
    assert not listen.thread.is_alive()
    assert listen.snapshot()["audio_available"]
    assert listen.snapshot()["duration_seconds"]==pytest.approx(
        stage.tempo_map.duration_seconds)
    assert listen.snapshot()["canonical_source_ids"]==[
        note.source_id for note in original.notes]
    (rendered,bpm),=capturer.calls
    assert bpm==80
    for actual,source in zip(rendered.notes,stage.variant.notes):
        assert actual.source_id==source.source_id
        assert actual.start==pytest.approx(source.start)
        assert actual.end==pytest.approx(source.end)


def test_coda_score_rejects_unsupported_annotations_without_silent_omission():
    original,variant=context()
    result=CodaReferenceDotted(True).transform(
        variant,boundaries=original.bar_boundaries,quantization=4,
        source_musicxml=original.source_musicxml)
    decorated=original.source_musicxml.replace(
        "<type>quarter</type>","<type>quarter</type><notations><articulations><staccato/></articulations></notations>",1)
    with pytest.raises(ValueError,match="annotations cannot follow a retimed source attack"):
        project_coda_score(replace(original,source_musicxml=decorated),
                           result.timing,reference_family="dotted-rhythms",bpm=80)
    augmented=original.source_musicxml.replace(
        "</measure>","<direction><direction-type><words>dolce</words></direction-type></direction></measure>",1)
    with pytest.raises(ValueError,match="Unsupported Coda source direction"):
        project_coda_score(replace(original,source_musicxml=augmented),
                           result.timing,reference_family="dotted-rhythms",bpm=80)


def test_coda_score_rejects_wrong_source_grid_and_mastery_overwrites():
    original,variant=context()
    result=CodaReferenceSlowdown(2).transform(variant)
    with pytest.raises(ValueError,match="whole original selected score"):
        project_coda_score(
            original,replace(result.timing,original=replace(
                variant,phrase=replace(variant.phrase,first_bar=2))),
            reference_family="tempo-shaping",bpm=80)
    no_source=replace(original,source_musicxml="")
    with pytest.raises(ValueError,match="original source MusicXML"):
        project_coda_score(no_source,result.timing,
                           reference_family="tempo-shaping",bpm=80)


def annotated_original(tmp_path, *, slur=True, dynamics=False, beam=False):
    root=ET.fromstring(SOURCE.read_text())
    right=root.findall("part")[0]
    bar=right.findall("measure")[0]
    notes=[n for n in bar.findall("note") if n.find("pitch") is not None]
    if slur:
        start=ET.SubElement(notes[0],"notations")
        ET.SubElement(start,"slur",type="start",number="1")
        art=ET.SubElement(start,"articulations")
        ET.SubElement(art,"staccato")
        stop=ET.SubElement(notes[3],"notations")
        ET.SubElement(stop,"slur",type="stop",number="1")
    if dynamics:
        later=right.findall("measure")[1]
        direction=ET.Element("direction",placement="below")
        group=ET.SubElement(direction,"direction-type")
        dyn=ET.SubElement(group,"dynamics")
        ET.SubElement(dyn,"p")
        later.insert(1,direction)
    if beam:
        for idx,note in enumerate(notes):
            # Unchanged authored eighth-note beam levels are verified
            # separately on the existing real-score beam fixture.
            ET.SubElement(note,"stem").text="up"
    source=tmp_path/"annotated-original.musicxml"
    source.write_text(ET.tostring(root,encoding="unicode"))
    piece=load_musicxml(source,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,2,0,8,piece.notes),
                             tuple(range(len(piece.notes))))
    return piece,variant


def test_coda_preserves_unmodified_source_slur_and_articulation_while_other_voice_changes(tmp_path):
    piece,variant=annotated_original(tmp_path)
    result=CodaReferenceDotted(True).transform(
        variant,boundaries=piece.bar_boundaries,quantization=4,
        source_musicxml=piece.source_musicxml)
    # Source slur protects all four RH attacks of measure 1.
    protected={n.source_id for n in variant.notes
               if n.hand=="right" and n.start < 4}
    assert not protected.intersection(result.changed_sources)
    assert result.changed_sources
    stage=project_coda_score(piece,result.timing,
                             reference_family="dotted-rhythms",bpm=80)
    art=ScoreArtifacts(PreprocessingCache(tmp_path/"score"))
    xml=ET.fromstring(art.notation_musicxml(stage.selection))
    starts=xml.findall(".//notations/slur[@type='start']")
    stops=xml.findall(".//notations/slur[@type='stop']")
    staccati=xml.findall(".//notations/articulations/staccato")
    assert len(starts)==len(stops)==len(staccati)==1
    model=art.source_model(stage.selection)
    assert len(model["notes"])==16
    assert any(n.start!=o.start or n.end!=o.end
               for n,o in zip(stage.variant.notes,variant.notes))
    assert any("slur" in str(item) for item in [ET.tostring(root) for root in starts])


def test_coda_preserves_source_dynamic_at_unchanged_measure_boundary(tmp_path):
    piece,variant=annotated_original(tmp_path,slur=False,dynamics=True)
    plan=CodaReferenceDotted(False).transform(
        variant,boundaries=piece.bar_boundaries,quantization=4,
        source_musicxml=piece.source_musicxml).timing
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    art=ScoreArtifacts(PreprocessingCache(tmp_path/"score"))
    root=ET.fromstring(art.notation_musicxml(stage.selection))
    assert len(root.findall(".//direction/direction-type/dynamics/p"))==1
    assert len(art.source_model(stage.selection)["notes"])==16


def test_coda_rejects_retimed_note_inside_an_authored_source_slur(tmp_path):
    piece,variant=annotated_original(tmp_path)
    # Deliberately use an unguarded plan from the same original source,
    # which would otherwise drop a slur's correct physical placement.
    from piano_teacher.exercise_contracts import TimingPlan
    original=OriginalTiming().transform(variant)
    mutable=list(original.events)
    idx=next(i for i,n in enumerate(variant.notes)
             if n.hand=="right" and n.start==1)
    mutable[idx]=replace(mutable[idx],exercise_start=2.1,exercise_end=2.5)
    broken=TimingPlan("unsafe-mark-change",variant,tuple(mutable),8)
    with pytest.raises(ValueError,match="overlapping or reordered slur"):
        project_coda_score(piece,broken,reference_family="dotted-rhythms",bpm=80)


def test_coda_rejects_unpaired_source_slur_instead_of_silent_omission(tmp_path):
    piece,variant=annotated_original(tmp_path)
    root=ET.fromstring(piece.source_musicxml)
    stop=root.find(".//slur[@type='stop']")
    assert stop is not None
    for parent in root.iter():
        if stop in parent:
            parent.remove(stop)
            break
    changed=replace(piece,source_musicxml=ET.tostring(root,encoding="unicode"))
    plan=OriginalTiming().transform(variant)
    with pytest.raises(ValueError,match="Unpaired or unsupported source slur"):
        project_coda_score(changed,plan,reference_family="dotted-rhythms",bpm=80)


def test_coda_real_score_plain_parallel_voice_ties_keep_barline_connectors(tmp_path):
    path=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"
    piece=load_musicxml(path,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,len(piece.bar_boundaries)-1,
            0,piece.bar_boundaries[-1],piece.notes),tuple(range(len(piece.notes))))
    plan=OriginalTiming().transform(variant)
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"tied"))
    score=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert len(score.findall(".//tie[@type='start']"))>=2
    assert len(score.findall(".//tie[@type='stop']"))>=2
    assert len(score.findall(".//tied[@type='start']"))>=2
    assert len(score.findall(".//tied[@type='stop']"))>=2
    model=artifacts.source_model(stage.selection)
    assert len(model["notes"])==len(variant.notes)
    assert {n["id"] for n in model["notes"]}=={
        n.source_id for n in variant.notes}


def test_coda_rejects_incomplete_parallel_voice_source_tie(tmp_path):
    path=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"
    piece=load_musicxml(path,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,len(piece.bar_boundaries)-1,
            0,piece.bar_boundaries[-1],piece.notes),tuple(range(len(piece.notes))))
    xml=ET.fromstring(piece.source_musicxml)
    first=xml.find(".//tie[@type='start']")
    assert first is not None
    for parent in xml.iter():
        if first in parent:
            parent.remove(first)
            break
    changed=replace(piece,source_musicxml=ET.tostring(xml,encoding="unicode"))
    with pytest.raises(ValueError,match="incomplete source ties"):
        project_coda_score(changed,OriginalTiming().transform(variant),
                           reference_family="dotted-rhythms",bpm=80)


def test_coda_rejects_retimed_or_styled_source_tie(tmp_path):
    path=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"
    piece=load_musicxml(path,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,len(piece.bar_boundaries)-1,
            0,piece.bar_boundaries[-1],piece.notes),tuple(range(len(piece.notes))))
    original=OriginalTiming().transform(variant)

    from piano_teacher.exercise_contracts import TimingPlan
    events=list(original.events)
    idx=next(i for i,n in enumerate(variant.notes)
             if n.voice.endswith("-v1") and n.start==0)
    events[idx]=replace(events[idx],exercise_end=3.75)
    changed=TimingPlan("invalid-retimed-tie",variant,tuple(events),
                        original.duration_beats)
    with pytest.raises(ValueError,match="safe shortened continuation"):
        project_coda_score(piece,changed,reference_family="dotted-rhythms",bpm=80)

    root=ET.fromstring(piece.source_musicxml)
    tied_note=root.find(".//note[tie]")
    assert tied_note is not None
    notations=ET.SubElement(tied_note,"notations")
    ET.SubElement(notations,"tied",type="start",placement="above")
    styled=replace(piece,source_musicxml=ET.tostring(root,encoding="unicode"))
    with pytest.raises(ValueError,match="plain, unretimed source-bar ties"):
        project_coda_score(styled,original,reference_family="dotted-rhythms",bpm=80)


def test_coda_rejects_unverified_authored_tuplet_marks(tmp_path):
    piece,variant=context()
    root=ET.fromstring(piece.source_musicxml)
    note=root.find(".//note[pitch]")
    assert note is not None
    ratio=ET.SubElement(note,"time-modification")
    ET.SubElement(ratio,"actual-notes").text="3"
    ET.SubElement(ratio,"normal-notes").text="2"
    decorated=replace(piece,source_musicxml=ET.tostring(root,encoding="unicode"))
    with pytest.raises(ValueError,match="requires unmodified 3:2, 5:4 or 7:4 eighth tuplets"):
        project_coda_score(decorated,OriginalTiming().transform(variant),
                           reference_family="dotted-rhythms",bpm=80)


@pytest.mark.parametrize("factor,grid,change_beat",[
    (2,(0,3,6,8,10),6),
    (4,(0,3,6,9,12,14,16,18,20),12),
])
def test_coda_mixed_meter_slowdown_projects_authored_bars_and_rests(
        factor,grid,change_beat,tmp_path):
    fixture=Path(__file__).parent/"fixtures/research/coda_mixed_meter.musicxml"
    piece=load_musicxml(fixture,bpm=80)
    assert piece.bar_boundaries==(0,3,5)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,5,piece.notes),
        tuple(range(len(piece.notes))))
    plan=CodaReferenceSlowdown(factor).transform(original).timing
    stage=project_coda_score(piece,plan,reference_family="tempo-shaping",bpm=80)
    assert stage.piece.bar_boundaries==grid
    assert stage.piece.time_signatures == (
        (0,3,4),(change_beat,2,4))
    assert any(key.beat==change_beat and key.fifths==-1
               for key in stage.piece.key_signatures)
    assert stage.piece.source_musicxml!=piece.source_musicxml
    assert piece.bar_boundaries==(0,3,5)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"mixed"))
    generated=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    for part in generated.findall("./part"):
        assert len(part.findall("./measure"))==2*factor
        measures=part.findall("./measure")
        first=measures[0].find("./attributes/time")
        second=measures[factor].find("./attributes/time")
        assert (first.findtext("beats"),first.findtext("beat-type"))==("3","4")
        assert (second.findtext("beats"),second.findtext("beat-type"))==("2","4")
        assert all(m.get("implicit")!="yes" for m in measures)
    model=artifacts.source_model(stage.selection)
    assert model["duration_beats"]==factor*5
    assert len(model["notes"])==len(piece.notes)==8
    assert {n["id"] for n in model["notes"]}=={
        n.source_id for n in piece.notes}
    rest_events=[e for e in model["notation_events"]
                 if e["kind"]=="rest"]
    assert rest_events
    # One written rest may legitimately split across the new barline.
    # x4 maps the source 2..3 quarter-rest into [8,12), crossing the
    # repeated 3/4 bar boundary at beat 9.
    rest_start,rest_end=2*factor,3*factor
    spans=sorted({(e["beat"],e["beat"]+e["duration_beats"])
                  for e in rest_events if e["staff"]=="left"
                  and rest_start-1e-7<=e["beat"]<rest_end-1e-7
                  and e["beat"]+e["duration_beats"]<=rest_end+1e-7})
    cursor=rest_start
    for first,last in spans:
        if first<cursor-1e-7:
            continue  # A separately padded voice may also contain rests.
        assert abs(first-cursor)<1e-7
        cursor=last
        if cursor>=rest_end-1e-7:
            break
    assert abs(cursor-rest_end)<1e-7
    played=[PlayedNote(note.pitch,stage.tempo_map.seconds_at(note.start),
                       stage.tempo_map.seconds_at(note.end))
            for note in stage.variant.notes]
    assert stage.grade(played).assessment.clean


def test_coda_slowdown_rejects_partial_source_bar_even_with_meter():
    original,variant=context()
    result=CodaReferenceSlowdown(2).transform(variant)
    # A pickup or partial measure needs an authored grouping policy.
    changed=replace(original,bar_boundaries=(0,3,8))
    with pytest.raises(ValueError,match="outside selected measure grid|incomplete source measures"):
        project_coda_score(changed,result.timing,reference_family="tempo-shaping",bpm=80)


def test_coda_complete_source_triplet_survives_independent_voice_transformation(tmp_path):
    path=Path(__file__).parent/"fixtures/research/coda_authored_triplet.musicxml"
    piece=load_musicxml(path,bpm=80)
    assert piece.bar_boundaries==(0,4)
    original=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    assert len(original.notes)==10
    plan=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,quantization=12,
        source_musicxml=piece.source_musicxml)
    triplet_ids={n.source_id for n in original.notes
                 if n.hand=="right" and n.start<1-1e-7}
    assert len(triplet_ids)==3
    assert not triplet_ids.intersection(plan.changed_sources)
    assert plan.changed_sources  # a different original voice actually changes
    stage=project_coda_score(
        piece,plan.timing,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"tuplets"))
    score=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert len(score.findall(".//time-modification"))>=3
    starts=score.findall(".//notations/tuplet[@type='start']")
    stops=score.findall(".//notations/tuplet[@type='stop']")
    assert len(starts)==1
    assert len(stops)==1
    assert starts[0].get("bracket")=="yes"
    assert starts[0].get("show-number")=="actual"
    model=artifacts.source_model(stage.selection)
    assert len(model["notes"])==10
    for symbol in model["notation_events"]:
        if symbol["source_id"] in triplet_ids and symbol["is_attack"]:
            assert symbol["time_modification"]=={"actual":3,"normal":2}
            assert symbol["note_type"]=="eighth"
    assert {n["id"] for n in model["notes"]}=={
        note.source_id for note in piece.notes}
    performed=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                          stage.tempo_map.seconds_at(n.end))
               for n in stage.variant.notes]
    assert stage.grade(performed).assessment.clean


def test_coda_rejects_partial_or_retimed_authored_triplet(tmp_path):
    path=Path(__file__).parent/"fixtures/research/coda_authored_triplet.musicxml"
    piece=load_musicxml(path,bpm=80)
    original=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    plan=OriginalTiming().transform(original)
    root=ET.fromstring(piece.source_musicxml)
    last=root.find(".//tuplet[@type='stop']")
    assert last is not None
    for parent in root.iter():
        if last in parent:
            parent.remove(last)
            break
    partial=replace(piece,source_musicxml=ET.tostring(root,encoding="unicode"))
    with pytest.raises(ValueError,match="incomplete or has unowned ratio notes"):
        project_coda_score(partial,plan,reference_family="dotted-rhythms",bpm=80)
    moved=list(plan.events)
    idx=next(i for i,n in enumerate(original.notes)
             if n.hand=="right" and abs(n.start-1/3)<1e-7)
    moved[idx]=replace(moved[idx],exercise_start=moved[idx].exercise_start+.05)
    from piano_teacher.exercise_contracts import TimingPlan
    unsafe=TimingPlan("shift-tuplet",original,tuple(moved),4)
    with pytest.raises(ValueError,match="cannot remap a source tuplet"):
        project_coda_score(piece,unsafe,reference_family="dotted-rhythms",bpm=80)
    with pytest.raises(ValueError,match="cannot remap a source tuplet"):
        project_coda_score(piece,CodaReferenceSlowdown(2).transform(original).timing,
                           reference_family="tempo-shaping",bpm=80)


def test_coda_tuplet_proof_rejects_changed_generated_bracket_and_ratio(tmp_path):
    """Negative control: source parity must fail on altered *output* XML."""
    from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
    from piano_teacher.research.coda_source_tuplets import (
        source_tuplet_groups, verify_projected_tuplets)

    path=Path(__file__).parent/"fixtures/research/coda_authored_triplet.musicxml"
    piece=load_musicxml(path,bpm=80)
    original=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    timing=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,quantization=12,
        source_musicxml=piece.source_musicxml).timing
    stage=project_coda_score(piece,timing,reference_family="dotted-rhythms",bpm=80)
    score=build_lesson_score(
        stage.variant.phrase,boundaries=stage.piece.bar_boundaries,
        time_signatures=stage.piece.time_signatures,
        key_signatures=stage.piece.key_signatures,
        clef_changes=stage.piece.clef_changes,
        default_clefs=infer_piece_clefs(stage.piece.notes),
        source_musicxml=stage.piece.source_musicxml,retimed_source=True)
    groups=source_tuplet_groups(piece,timing,factor=1)
    assert len(groups)==1
    verify_projected_tuplets(groups,score.musicxml,score.note_bindings)

    wrong_bracket=ET.fromstring(score.musicxml)
    first=wrong_bracket.find(".//tuplet[@type='start']")
    assert first is not None
    first.set("bracket","no")
    with pytest.raises(ValueError,match="changed source tuplet group styling"):
        verify_projected_tuplets(groups,ET.tostring(wrong_bracket,encoding="unicode"),
                                 score.note_bindings)

    wrong_ratio=ET.fromstring(score.musicxml)
    ratio=wrong_ratio.find(".//time-modification/actual-notes")
    assert ratio is not None
    ratio.text="5"
    with pytest.raises(ValueError,match="changed an authored tuplet ratio"):
        verify_projected_tuplets(groups,ET.tostring(wrong_ratio,encoding="unicode"),
                                 score.note_bindings)


def test_coda_retimed_source_slur_keeps_authored_ink_and_grading(tmp_path):
    """All four RH attacks retime inside the same voice and source measure."""
    from piano_teacher.exercise_contracts import TimingPlan
    piece,variant=annotated_original(tmp_path)
    source=OriginalTiming().transform(variant)
    retimed=list(source.events)
    for first_start,length in ((0,1.5),(1,0.5),(2,1.5),(3,0.5)):
        idx=next(i for i,n in enumerate(variant.notes)
                 if n.hand=="right" and n.start==first_start)
        at=(0,1.5,2,3.5)[first_start]
        retimed[idx]=replace(retimed[idx],
                              exercise_start=at,exercise_end=at+length)
    plan=TimingPlan("retimed-authored-slur",variant,tuple(retimed),8)
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    art=ScoreArtifacts(PreprocessingCache(tmp_path/"retimed-slur"))
    root=ET.fromstring(art.notation_musicxml(stage.selection))
    assert len(root.findall(".//slur[@type='start']"))==1
    assert len(root.findall(".//slur[@type='stop']"))==1
    assert len(root.findall(".//staccato"))==1
    assert {x["id"] for x in art.source_model(stage.selection)["notes"]}=={
        n.source_id for n in variant.notes}
    performed=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                          stage.tempo_map.seconds_at(n.end))
               for n in stage.variant.notes]
    assert stage.grade(performed).assessment.clean


@pytest.mark.parametrize("actual,normal,quantization",[(5,4,20),(7,4,70)])
def test_complete_source_quintuplet_and_septuplet_keep_original_ink(
        actual,normal,quantization,tmp_path):
    from piano_teacher.research.coda_source_tuplets import source_tuplet_groups
    path=Path(__file__).parent / "fixtures/research" / f"coda_group_{actual}_{normal}.musicxml"
    piece=load_musicxml(path,bpm=80)
    original=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    result=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,
        quantization=quantization,source_musicxml=piece.source_musicxml)
    groups=source_tuplet_groups(piece,result.timing,factor=1)
    assert len(groups)==1
    assert len(groups[0].source_ids)==actual
    assert (groups[0].actual,groups[0].normal)==(actual,normal)
    assert not set(groups[0].source_ids).intersection(result.changed_sources)
    assert result.changed_sources
    stage=project_coda_score(
        piece,result.timing,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/f"{actual}-{normal}"))
    root=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    first=root.find(".//tuplet[@type='start']")
    last=root.find(".//tuplet[@type='stop']")
    assert first is not None and last is not None
    assert first.get("bracket")=="yes"
    assert len(root.findall(".//time-modification"))>=actual
    model=artifacts.source_model(stage.selection)
    assert len(model["notes"])==len(original.notes)
    assert {n["id"] for n in model["notes"]}=={
        n.source_id for n in original.notes}


def test_retimed_source_bar_tie_shortens_after_boundary_without_retrigger(tmp_path):
    from piano_teacher.exercise_contracts import TimingPlan
    path=Path(__file__).parent/"fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml"
    piece=load_musicxml(path,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,8,piece.notes),
        tuple(range(len(piece.notes))))
    base=OriginalTiming().transform(original)
    events=list(base.events)
    index=next(i for i,n in enumerate(original.notes)
               if n.start==0 and n.voice.endswith("-v1"))
    events[index]=replace(events[index],exercise_end=5.5)
    plan=TimingPlan("shorter-source-tie",original,tuple(events),8)
    stage=project_coda_score(
        piece,plan,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"short-tie"))
    root=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert len(root.findall(".//tie[@type='start']"))>=2
    assert len(root.findall(".//tie[@type='stop']"))>=2
    model=artifacts.source_model(stage.selection)
    selected=next(n for n in model["notes"]
                  if n["id"]==original.notes[index].source_id)
    assert selected["duration_beats"]==pytest.approx(5.5)
    assert len(model["notes"])==len(original.notes)  # no second attack
    performed=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                          stage.tempo_map.seconds_at(n.end))
               for n in stage.variant.notes]
    assert stage.grade(performed).assessment.clean


def test_source_dynamic_follows_retimed_note_with_original_identity(tmp_path):
    """Move a source dynamic from beat 1 to the retimed attack at beat 1.5."""
    from piano_teacher.exercise_contracts import TimingPlan

    root=ET.fromstring(SOURCE.read_text())
    right=root.findall("./part")[0]
    bar=right.findall("./measure")[0]
    pitched=[n for n in bar.findall("note") if n.find("pitch") is not None]
    direction=ET.Element("direction",placement="below")
    dt=ET.SubElement(direction,"direction-type")
    ET.SubElement(ET.SubElement(dt,"dynamics"),"mf")
    bar.insert(list(bar).index(pitched[1]),direction)
    source=tmp_path/"authored-midbeat-dynamic.musicxml"
    source.write_text(ET.tostring(root,encoding="unicode"))
    piece=load_musicxml(source,bpm=80)
    original=ExerciseVariant(
        "original",Phrase(1,1,2,0,8,piece.notes),
        tuple(range(len(piece.notes))))
    baseline=OriginalTiming().transform(original)
    changed=list(baseline.events)
    idx=next(i for i,n in enumerate(original.notes)
             if n.hand=="right" and abs(n.start-1)<1e-7)
    changed[idx]=replace(changed[idx],exercise_start=1.5,exercise_end=2)
    plan=TimingPlan("moved-dynamic",original,tuple(changed),8)
    stage=project_coda_score(
        piece,plan,reference_family="dotted-rhythms",bpm=80)
    assert piece.source_musicxml!=stage.piece.source_musicxml
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"dynamic"))
    xml=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    direction=xml.find("./part[@id='RH']/measure[@number='1']/direction")
    assert direction is not None
    assert direction.find(".//mf") is not None
    assert int(direction.findtext("offset"))==15120
    assert len(xml.findall(".//direction/direction-type/dynamics/mf"))==1
    model=artifacts.source_model(stage.selection)
    identity=original.notes[idx].source_id
    assert next(n for n in model["notes"] if n["id"]==identity)[
        "onset_beats"]==pytest.approx(1.5)
    assert original.notes[idx].start==1
    performed=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                          stage.tempo_map.seconds_at(n.end))
               for n in stage.variant.notes]
    assert stage.grade(performed).assessment.clean


def test_source_dynamic_cannot_move_to_another_measure(tmp_path):
    from piano_teacher.exercise_contracts import TimingPlan
    root=ET.fromstring(SOURCE.read_text())
    bar=root.findall("./part")[0].findall("./measure")[0]
    notes=[n for n in bar.findall("./note") if n.find("pitch") is not None]
    direction=ET.Element("direction")
    dt=ET.SubElement(direction,"direction-type")
    ET.SubElement(ET.SubElement(dt,"dynamics"),"p")
    bar.insert(list(bar).index(notes[-1]),direction)
    path=tmp_path/"crossing-direction.musicxml"
    path.write_text(ET.tostring(root,encoding="unicode"))
    piece=load_musicxml(path,bpm=80)
    original=ExerciseVariant("original",Phrase(1,1,2,0,8,piece.notes),
                             tuple(range(len(piece.notes))))
    baseline=OriginalTiming().transform(original)
    events=list(baseline.events)
    i=next(i for i,n in enumerate(original.notes)
           if n.hand=="right" and n.start==3)
    events[i]=replace(events[i],exercise_start=4.1,exercise_end=4.5)
    plan=TimingPlan("bad-direction-crossbar",original,tuple(events),8)
    with pytest.raises(ValueError,match="direction moved outside original source measure"):
        project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)


def test_coda_source_triplet_with_one_interior_rest_survives_other_hand_retime(tmp_path):
    from piano_teacher.research.coda_source_tuplets import (
        source_tuplet_groups,verify_projected_tuplets)
    source=ET.fromstring((Path(__file__).parent/
        "fixtures/research/coda_authored_triplet.musicxml").read_text())
    rh=source.findall("./part")[0]
    middle=[note for note in rh.findall("./measure/note")
            if note.find("time-modification") is not None][1]
    pitch=middle.find("pitch")
    assert pitch is not None
    middle.remove(pitch)
    middle.insert(0,ET.Element("rest"))
    fixture=tmp_path/"triplet-with-rest.musicxml"
    fixture.write_text(ET.tostring(source,encoding="unicode"))
    piece=load_musicxml(fixture,bpm=80)
    original=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    assert len(original.notes)==9
    transformed=CodaReferenceDotted(True).transform(
        original,boundaries=piece.bar_boundaries,quantization=12,
        source_musicxml=piece.source_musicxml)
    groups=source_tuplet_groups(piece,transformed.timing,factor=1)
    assert len(groups)==1
    assert len(groups[0].rests)==1
    assert groups[0].rests[0].onset==pytest.approx(1/3)
    assert groups[0].rests[0].end==pytest.approx(2/3)
    assert transformed.changed_sources
    assert set(groups[0].source_ids).isdisjoint(transformed.changed_sources)
    stage=project_coda_score(
        piece,transformed.timing,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/"rest-tuplet"))
    xml=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    assert len(xml.findall(".//tuplet[@type='start']"))==1
    assert len(xml.findall(".//tuplet[@type='stop']"))==1
    with_rest=[n for n in xml.findall(".//note")
               if n.find("rest") is not None and
               n.find("time-modification") is not None]
    assert any(n.findtext("time-modification/actual-notes")=="3"
               and n.findtext("time-modification/normal-notes")=="2"
               for n in with_rest)
    model=artifacts.source_model(stage.selection)
    assert len(model["notes"])==9
    assert any(e["kind"]=="rest" and abs(e["beat"]-1/3)<1e-6
               for e in model["notation_events"])
    performed=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                          stage.tempo_map.seconds_at(n.end))
               for n in stage.variant.notes]
    assert stage.grade(performed).assessment.clean


def test_coda_rest_tuplet_rejects_generated_wrong_rest_voice(tmp_path):
    from piano_teacher.notation.lesson import build_lesson_score,infer_piece_clefs
    from piano_teacher.research.coda_source_tuplets import (
        source_tuplet_groups,verify_projected_tuplets)
    root=ET.fromstring((Path(__file__).parent/
        "fixtures/research/coda_authored_triplet.musicxml").read_text())
    middle=[n for n in root.findall("./part")[0].findall("./measure/note")
            if n.find("time-modification") is not None][1]
    middle.remove(middle.find("pitch"))
    middle.insert(0,ET.Element("rest"))
    path=tmp_path/"marked-rest.musicxml"
    path.write_text(ET.tostring(root,encoding="unicode"))
    piece=load_musicxml(path,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    plan=OriginalTiming().transform(variant)
    stage=project_coda_score(piece,plan,reference_family="dotted-rhythms",bpm=80)
    built=build_lesson_score(
        stage.variant.phrase,boundaries=stage.piece.bar_boundaries,
        time_signatures=stage.piece.time_signatures,
        key_signatures=stage.piece.key_signatures,
        clef_changes=stage.piece.clef_changes,
        default_clefs=infer_piece_clefs(stage.piece.notes),
        source_musicxml=stage.piece.source_musicxml,
        retimed_source=True)
    groups=source_tuplet_groups(piece,plan,factor=1)
    root=ET.fromstring(built.musicxml)
    candidates=[n for n in root.findall(".//note") if
                n.find("rest") is not None and
                n.find("time-modification/actual-notes") is not None]
    assert len(candidates)>=1
    candidates[0].find("voice").text="999"
    with pytest.raises(ValueError,match="lost authored tuplet rest timing or voice"):
        verify_projected_tuplets(
            groups,ET.tostring(root,encoding="unicode"),
            built.note_bindings,boundaries=piece.bar_boundaries)


@pytest.mark.parametrize("actual,normal,quantization",[(5,4,20),(7,4,70)])
def test_coda_quintuplet_septuplet_interior_source_rest_keeps_clock_and_voice(
        actual,normal,quantization,tmp_path):
    from piano_teacher.research.coda_source_tuplets import source_tuplet_groups

    source=(Path(__file__).parent/"fixtures/research"/
            f"coda_group_{actual}_{normal}_interior_rest.musicxml")
    piece=load_musicxml(source,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    plan=CodaReferenceDotted(True).transform(
        variant,boundaries=piece.bar_boundaries,
        quantization=quantization,source_musicxml=piece.source_musicxml)
    group,=source_tuplet_groups(piece,plan.timing,factor=1)
    assert (group.actual,group.normal)==(actual,normal)
    assert len(group.rests)==1
    assert group.rests[0].onset==pytest.approx(normal/(2*actual))
    assert group.rests[0].end==pytest.approx(normal/actual)
    assert plan.changed_sources
    stage=project_coda_score(
        piece,plan.timing,reference_family="dotted-rhythms",bpm=80)
    artifacts=ScoreArtifacts(PreprocessingCache(tmp_path/f"rest-ratio-{actual}"))
    written=ET.fromstring(artifacts.notation_musicxml(stage.selection))
    authored=[n for n in written.findall(".//note")
              if n.find("rest") is not None and
              n.findtext("time-modification/actual-notes")==str(actual)]
    assert len(authored)==1
    assert authored[0].findtext("time-modification/normal-notes")==str(normal)
    model=artifacts.source_model(stage.selection)
    assert len(model["notes"])==len(piece.notes)
    assert set(n["id"] for n in model["notes"])=={
        note.source_id for note in piece.notes}
    played=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                       stage.tempo_map.seconds_at(n.end))
            for n in stage.variant.notes]
    assert stage.grade(played).assessment.clean


@pytest.mark.parametrize("rest_indices",[(0,1),(1,2)])
def test_coda_tuplet_rejects_endpoint_or_multiple_source_rests(
        rest_indices,tmp_path):
    from piano_teacher.research.coda_source_tuplets import source_tuplet_groups

    root=ET.fromstring((Path(__file__).parent/"fixtures/research"/
        "coda_group_5_4.musicxml").read_text())
    members=[n for n in root.findall("./part")[0].findall("./measure/note")
             if n.find("time-modification") is not None]
    assert len(members)==5
    for i in rest_indices:
        pitch=members[i].find("pitch")
        assert pitch is not None
        members[i].remove(pitch)
        members[i].insert(0,ET.Element("rest"))
    filename=tmp_path/"unsupported-tuplet-rests.musicxml"
    filename.write_text(ET.tostring(root,encoding="unicode"))
    piece=load_musicxml(filename,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,1,0,4,piece.notes),
                             tuple(range(len(piece.notes))))
    with pytest.raises(ValueError,match="only supports one interior tuplet rest"):
        source_tuplet_groups(piece,OriginalTiming().transform(variant),factor=1)
