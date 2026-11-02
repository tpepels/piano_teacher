"""Fukuda SMC2015 MIDI-only reproduction contracts.

All three simplification rules, score/performance MIDI DTW, mistake
mapping, exact source identities, and whole-piece lessons are exercised.
"""
from dataclasses import replace
from pathlib import Path

import mido
import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.fukuda_midi import (
    align_midi_dtw,detect_midi_mistakes,rule_chord_outer,
    rule_fast_thinning,rule_octave_leaps,fukuda_midi_variants,
)
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_generators import FukudaMidiLessonGenerator
from piano_teacher.music import Note,Phrase,load_midi
from piano_teacher.practice import PlayedNote


def phrase(pitches, times, duration=.2, hands=None):
    notes=tuple(Note(t,t+duration,p,0,0,
                     hands[i] if hands else "right",
                     f"midi-{i}","v0")
                for i,(t,p) in enumerate(zip(times,pitches)))
    return Phrase(1,1,2,0,8,notes)


def original(p):
    return ExerciseVariant("original",p,tuple(range(len(p.notes))))


def test_chord_reduction_keeps_bass_and_melody_and_source_ownership():
    p=phrase([48,55,60,64,67,62],[0,0,0,0,0,1])
    v=rule_chord_outer(original(p))
    assert v is not None
    assert tuple(n.pitch for n in v.notes)==(48,67,62)
    assert v.source_indices==(0,4,5)
    assert rule_chord_outer(original(p),mistakes=frozenset({"midi-5"})) is None
    assert rule_chord_outer(original(p),mistakes=frozenset({"midi-2"}))==v


def test_fast_thinning_avoids_striking_melody_peak():
    p=phrase([60,62,76,64,65,66,67,68],
             [0,.20,.40,.60,.80,1,1.2,1.4],duration=.18)
    v=rule_fast_thinning(original(p),bpm=120)
    assert v is not None
    assert 76 in [n.pitch for n in v.notes]
    assert 60 in [n.pitch for n in v.notes]
    assert 68 in [n.pitch for n in v.notes]
    assert len(v.notes)<len(p.notes)
    assert rule_fast_thinning(original(p),bpm=120,
                              mistakes=frozenset({"midi-0"})) is None


def test_returning_leap_removes_outlier_but_not_stable_context():
    p=phrase([60,77,62,64,65],[0,1,2,3,4])
    v=rule_octave_leaps(original(p),bpm=90)
    assert v is not None
    assert v.level=="fukuda-midi-return-leap"
    assert 77 not in [n.pitch for n in v.notes]
    assert tuple(n.pitch for n in v.notes)==(60,62,64,65)
    assert rule_octave_leaps(original(p),bpm=90,
                            mistakes=frozenset({"midi-4"})) is None


def test_three_rule_family_progression_has_original_terminal():
    p=phrase([48,55,60,64,67,60,77,61,62,63,64,65],
             [0,0,0,0,0,.5,.75,1,1.25,1.5,1.75,2],duration=.20)
    stages=fukuda_midi_variants(original(p),bpm=130)
    assert stages[-1].level=="original"
    assert stages[-1].notes==p.notes
    assert len({stage.level for stage in stages})==len(stages)
    for s in stages:
        assert tuple(p.notes[i] for i in s.source_indices)==s.notes
    assert any("chord" in s.level for s in stages)
    assert any("leap" in s.level for s in stages)


def test_dtw_aligns_expressive_midi_without_audio_transcription():
    p=phrase([60,62,64,65],[0,1,2,3],duration=.5)
    played=[PlayedNote(note.pitch,(note.start)*.82+.12,
                       (note.end)*.82+.12) for note in p.notes]
    aligned=align_midi_dtw(p,played,bpm=80)
    assert len(aligned)==4
    assert [x.score_beat for x in aligned]==[0,1,2,3]
    assert [x.performed_seconds for x in aligned]==pytest.approx(
        [n.onset for n in played])
    report=detect_midi_mistakes(p,played,bpm=80)
    assert not report.mismatches
    assert not report.extra_pitches


def test_wrong_pitch_exact_midi_octave_is_not_suppressed():
    p=phrase([60,64,67],[0,1,2],duration=.5)
    played=[PlayedNote(60,0,.4),PlayedNote(76,.75,1.15),
            PlayedNote(67,1.5,1.9)]
    result=detect_midi_mistakes(p,played,bpm=80)
    assert any(m.pitch==64 and m.kind in ("wrong","missed")
               for m in result.mismatches)
    # Unlike acoustic NMF, a wrong MIDI octave is a real wrong note.
    assert "midi-1" in result.problematic_source_ids


def test_missing_and_extra_events_are_not_swallowed_by_alignment():
    p=phrase([60,62,64,65],[0,1,2,3],duration=.5)
    played=[PlayedNote(60,0,.3),PlayedNote(64,1.5,1.7),
            PlayedNote(65,2.25,2.6),PlayedNote(80,3,3.2)]
    result=detect_midi_mistakes(p,played,bpm=80)
    assert "midi-1" in result.problematic_source_ids
    assert any(pitch==80 for _,pitch in result.extra_pitches)


def test_empty_performance_marks_all_source_notes_missing():
    p=phrase([60,62,64],[0,1,2],duration=.5)
    out=detect_midi_mistakes(p,[],bpm=80)
    assert len(out.mismatches)==3
    assert all(x.kind=="missed" for x in out.mismatches)


def test_invalid_midi_dtws_are_rejected():
    p=phrase([60,61],[0,1])
    with pytest.raises(ValueError):
        align_midi_dtw(p,[PlayedNote(61,-.2,None)])
    with pytest.raises(ValueError):
        align_midi_dtw(p,[PlayedNote(61,0,None)],bpm=-10)
    with pytest.raises(ValueError):
        align_midi_dtw(p,[PlayedNote(61,0,None)],maximum_onsets=1)


def make_midi(path:Path):
    file=mido.MidiFile(type=1,ticks_per_beat=480)
    track=mido.MidiTrack()
    track.append(mido.MetaMessage("track_name",name="Right Hand",time=0))
    track.append(mido.MetaMessage("time_signature",numerator=4,denominator=4,time=0))
    events=[]
    notes=[
      (0,48),(0,55),(0,60),(0,67),
      (480,60),(720,78),(960,61),(1200,63),
      (1440,64),(1560,65),(1680,67),(1800,69),
      (1920,60),(2160,62),(2400,64),(2640,65),
      (2880,67),(3120,69),(3360,71),(3600,72),
    ]
    for tick,pitch in notes:
        events.extend(((tick,True,pitch),(tick+90,False,pitch)))
    last=0
    for tick,is_on,pitch in sorted(events,key=lambda e:(e[0],e[1])):
        track.append(mido.Message("note_on" if is_on else "note_off",
            note=pitch,velocity=80 if is_on else 0,time=tick-last))
        last=tick
    track.append(mido.MetaMessage("end_of_track",time=3900-last))
    file.tracks.append(track)
    file.save(path)


def test_fukuda_whole_piece_generator_uses_all_rule_families(tmp_path):
    path=tmp_path/"fukuda.mid"
    make_midi(path)
    piece=load_midi(path)
    plan=LearningPlan(piece,exercise_strategy="fukuda-midi")
    assert isinstance(plan.lesson_generator,FukudaMidiLessonGenerator)
    assert plan.lesson_definition.generator_name=="fukuda-midi"
    assert plan.lesson_steps
    assert all(step.key.startswith("course:4:fukuda-midi:")
               for step in plan.lesson_steps)
    assert any("fukuda-midi-chord" in s.level for s in plan.lesson_steps)
    assert any("fukuda-midi-fast" in s.level for s in plan.lesson_steps)
    assert any("leap" in s.level for s in plan.lesson_steps)
    for ex in plan.exercises:
        for hand in plan.hands if ex is plan.exercise else ("right",):
            if (ex.key,hand) not in plan.lesson_definition.stage_sequences:
                continue
            stages=plan.lesson_definition.stages(ex,hand)
            assert stages[-1].variant.level=="original"
            assert all(tuple(ex.phrase.notes[i] for i in s.variant.source_indices)
                       ==s.variant.notes for s in stages)
    assert plan.exercises[-1].kind=="perform"
    assert any(step.kind=="perform" and step.level=="original"
               for step in plan.lesson_steps)


def test_incompatible_audio_musicxml_input_and_extra_rules_are_rejected(tmp_path):
    from piano_teacher.exercise_strategies import available_strategies,resolve_strategy
    path=tmp_path/"midi.mid";make_midi(path)
    p=load_midi(path)
    assert "fukuda-midi" in {x["id"] for x in available_strategies()}
    assert resolve_strategy("fukuda-midi",piece=p).name=="fukuda-midi"
    with pytest.raises(ValueError,match="MIDI piece"):
        resolve_strategy("fukuda-midi")
    from dataclasses import replace
    with pytest.raises(ValueError,match="MIDI piece"):
        LearningPlan(replace(p,source_format="musicxml"),
                     exercise_strategy="fukuda-midi")


def test_mistake_store_isolated_persisted_and_correct_notes_resolved(tmp_path):
    import sqlite3
    from piano_teacher.fukuda_mistake_store import FukudaMistakeStore
    from piano_teacher.practice import Assessment,NoteAssessment
    path=tmp_path/"mistakes.db"
    conn=sqlite3.connect(path)
    try:
        store=FukudaMistakeStore(conn)
        p=phrase([60,64,67],[0,1,2],duration=.25)
        failed=Assessment((NoteAssessment(p.notes[0],"missed"),
                           NoteAssessment(p.notes[1],"wrong"),
                           NoteAssessment(p.notes[2],"correct")),0)
        problems=store.observe("piece-hash",failed)
        assert problems==frozenset(("midi-0","midi-1"))
        assert store.problematic("another-piece")==frozenset()
        success=Assessment((NoteAssessment(p.notes[0],"correct"),
                            NoteAssessment(p.notes[1],"missed")),0)
        assert store.observe("piece-hash",success)==frozenset(("midi-1",))
        conn.close()
        conn=sqlite3.connect(path)
        reopened=FukudaMistakeStore(conn)
        assert reopened.problematic("piece-hash")==frozenset(("midi-1",))
        reopened.reset("piece-hash")
        assert not reopened.problematic("piece-hash")
    finally:
        conn.close()


def test_live_learning_plan_rebuilds_graded_midi_stages_without_mastery_transfer(tmp_path):
    path=tmp_path/"fukuda.mid"
    make_midi(path)
    piece=load_midi(path)
    plan=LearningPlan(piece,exercise_strategy="fukuda-midi",
        fukuda_mistakes=frozenset())
    original_key=plan.identity
    original_index=plan.variant_index
    assert not any(s.level.startswith("fukuda-midi-")
                   for s in plan.lesson_steps)
    mistakes=frozenset(n.source_id for n in piece.notes)
    assert plan.update_fukuda_mistakes(mistakes)
    assert any(s.level.startswith("fukuda-midi-")
               for s in plan.lesson_steps)
    assert plan.lesson_definition.generator_name=="fukuda-midi"
    assert not plan.update_fukuda_mistakes(mistakes)
    assert all(s.key not in plan.mastered for s in plan.lesson_steps)
    assert original_key in {s.key for s in plan.lesson_steps}
    assert plan.update_fukuda_mistakes(frozenset())
    assert not any(s.level.startswith("fukuda-midi-")
                   for s in plan.lesson_steps)
    assert original_key in {s.key for s in plan.lesson_steps}


def test_real_engine_records_assessed_original_midi_errors_and_restores(tmp_path):
    from piano_teacher.practice import Assessment,NoteAssessment
    from piano_teacher.server import PracticeEngine
    path=tmp_path/"phase4-engine.mid"
    make_midi(path)
    engine=PracticeEngine(tmp_path/"state",enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="fukuda-midi")
        engine.load(str(path))
        assert engine.plan.lesson_generator.name=="fukuda-midi"
        assert len(engine.plan.stages)==1
        source=engine.plan.active_variant.notes
        assert source
        # The normal grading pipeline owns these statuses. A MIDI
        # wrong/missing note is remembered by source ID, not fuzzy pitch.
        assess=Assessment(tuple(NoteAssessment(note,"missed")
                                for note in source),0)
        engine.pending_result=assess
        engine._commit_pending()
        assert engine.fukuda_mistakes.problematic(engine.fingerprint)==frozenset(
            n.source_id for n in source)
        assert len(engine.plan.stages)>1
        original_stage=next(x.variant for x in engine.plan.stages
                            if x.variant.level=="original")
        assert original_stage.notes==source
        engine.load(str(path))
        assert engine.plan.lesson_generator.mistakes
        assert len(engine.plan.stages)>1
        engine._reset_current_path(confirm=True,fingerprint=engine.fingerprint)
        assert not engine.fukuda_mistakes.problematic(engine.fingerprint)
        assert len(engine.plan.stages)==1
    finally:
        engine.listen.cancel()
        engine.db.close()
