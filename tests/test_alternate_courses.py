"""Supported alternatives are selected explicitly; these are not default-flow rules."""
from pathlib import Path

from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_generators import lesson_hands
from piano_teacher.teaching_course import manual_progress
from piano_teacher.practice import Recorder, evaluate, note_dimensions

ROOT = Path(__file__).resolve().parents[1]


def test_selected_coda_course_eventually_returns_each_hand_to_original_source():
    piece = import_piece(ROOT / "midi" / "J_S_Bach_-_Invention_No_1_(BWV_772).midi")
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    assert plan.lesson_steps and plan.lesson_steps[0].required_notes > 0
    assert plan.exercises[-1].kind == "perform"
    source = {n.source_id: n for n in piece.notes}
    for exercise in plan.exercises:
        for hand in lesson_hands(exercise):
            variants = plan.stage_variants(exercise, hand)
            original = variants[-1]
            assert original.level == "original"
            expected = [n for n in exercise.phrase.notes if hand == "both" or n.hand == hand]
            assert [(n.source_id, n.start, n.end, n.pitch, n.hand) for n in original.notes] == [
                (n.source_id, n.start, n.end, n.pitch, n.hand) for n in expected]
            for variant in variants:
                # A simplified exercise can alter onsets, but never invent a pitch or hand.
                assert all(n.source_id in source and n.pitch == source[n.source_id].pitch
                           and n.hand == source[n.source_id].hand for n in variant.notes)
    final = plan.exercises[-1].phrase
    assert {n.source_id for n in final.notes} == set(source)
    assert max(n.end for n in final.notes) == max(n.end for n in piece.notes)


def test_source_progression_tools_allow_manual_tempo_and_selected_step():
    piece = import_piece(ROOT / "tests" / "fixtures" / "musical_fidelity" / "midi_mixed_meter.mid")
    plan = LearningPlan(piece, exercise_strategy="source-progression")
    first = plan.lesson_step_number

    def manual(action, **values):
        # The same pure lesson decision the session installs for learner tools.
        course = manual_progress(plan.course_state(), action, **values)
        plan.apply_teaching_progress(course.progress, definition=course.definition,
                                     expected=plan.teaching_progress())

    manual("tempo", bpm=72)
    assert plan.bpm == 72
    assert plan.lesson_step_number == first
    manual("select_step", number=len(plan.lesson_steps))
    assert {n.source_id for n in plan.active_phrase.notes} == {n.source_id for n in piece.notes}
    manual("select_step", number=first)
    assert plan.bpm == 72
    assert not plan.mastered


def test_generic_source_progression_records_short_release_as_a_failed_take():
    piece = import_piece(ROOT / "tests" / "fixtures" / "musical_fidelity" / "midi_four_four.mid")
    plan = LearningPlan(piece, exercise_strategy="source-progression")
    phrase = plan.active_phrase
    recorder = Recorder()
    for note in phrase.notes:
        onset = (note.start - phrase.start) * 60 / piece.bpm
        recorder.add(note.pitch, True, onset)
        recorder.add(note.pitch, False, onset + .01)
    result = evaluate(phrase, plan.hand, piece.bpm, recorder.presses,
                      grade_note_holds=True)
    assert not result.passed
    assert all(note_dimensions(n)["onset"] == "on_time" for n in result.notes)
    assert any(note_dimensions(n)["release"] == "short" for n in result.notes)


def test_all_builtin_warmups_open_as_real_two_hand_music_outside_the_personal_folder(practice_session):
    session = practice_session(bars=1)
    original = session.path.read_bytes()
    warmups = session.ask("library.catalog")["warmups"]
    assert warmups
    fingerprints = set()
    for exercise in warmups:
        state = session.ask("library.open", id=exercise["id"])
        assert state["warmup"] and state["kind"] == "warmup"
        assert state["original_bpm"] == exercise["bpm"]
        assert state["clean_runs_required"] == 3
        model = session.ask("score.semantic")
        assert model["notes"] and all(note["duration_beats"] > 0 for note in model["notes"])
        assert {note["hand"] for note in model["display_notes"]} == {"left","right"}
        fingerprints.add(session.ask("learning.status")["current_fingerprint"])
        session.command("start")
        started = session.ready_score()
        assert started["running"] and started["count_in_beats"] > 0
        session.command("stop")
    assert len(fingerprints) == len(warmups)
    assert list(session.music.iterdir()) == [session.path]
    assert session.path.read_bytes() == original

def test_warmup_step_picker_cannot_skip_unmastered_hands_or_stages(practice_session):
    """Direct lesson commands must obey the same three-pass unlock as the UI."""
    import json

    session = practice_session(bars=1)
    warmup = session.ask("library.catalog")["warmups"][0]
    session.ask("library.open",id=warmup["id"])
    state = session.snapshot()
    overview = session.ask("lesson.overview")
    steps = overview["steps"]
    assert len(steps) >= 2
    assert steps[0]["available"] and not steps[1]["available"]
    assert state["warmup"] and not state["controls"]["path_skip"]["enabled"]
    assert not state["controls"]["hands"].get("left",{}).get("enabled",False)
    initial_step = state["lesson_step"]
    # Both the numeric step selector and the alternate hand picker submit
    # real practice.command requests, not internal curriculum mutations.
    for action in ({"action":"select_step","number":2},
                   {"action":"hand","hand":"left"}):
        status, body = session.commands.request("practice.command",json.dumps(action))
        assert status != 0, (action,body)
        unchanged = session.snapshot()
        assert unchanged["lesson_step"] == initial_step
        assert unchanged["mastered"] == 0
    assert session.ask("lesson.overview")["steps"][1]["available"] is False


def test_manual_navigation_remains_available_for_non_warmup_course(practice_session):
    """The warm-up mastery gate must not lock imported MIDI exploration."""
    session = practice_session(bars=3)
    overview = session.ask("lesson.overview")
    assert len(overview["steps"]) >= 2
    assert all(step["available"] for step in overview["steps"])
    before = session.snapshot()
    selected = session.command("select_step",number=2)
    assert selected["lesson_step"] == 2
    assert selected["mastered"] == before["mastered"]
