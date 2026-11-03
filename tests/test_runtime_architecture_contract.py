"""Static and semantic guards for the MIDI-only in-process application."""
from pathlib import Path

from piano_teacher.exercise_pipeline import ExerciseStage
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.lesson_stage_semantics import describe, teaching_sequence
from piano_teacher.music import Note, Phrase


ROOT = Path(__file__).resolve().parents[1]


def test_production_bridge_exposes_no_old_network_or_page_endpoints():
    source = (ROOT / "piano_teacher/inprocess.py").read_text()
    assert '"/load"' not in source
    assert '"/score.svg"' not in source
    assert '"/score.png"' not in source
    assert 'native_notes=raw' not in source
    assert 'engine.geometry()' in source
    for path in (
        ROOT / "godot/main.gd",
        ROOT / "godot/score_asset_session.gd",
        ROOT / "godot/inprocess_bus.gd",
        ROOT / "godot/inprocess_request.gd",
    ):
        text = path.read_text()
        assert "HTTPRequest.new(" not in text
        assert "HTTPClient.new(" not in text
        assert "PacketPeerUDP.new(" not in text
    assert '"score.native_layout"' in (
        ROOT / "godot/score_asset_session.gd").read_text()


def test_adaptive_catalog_does_not_import_author_specific_builders():
    source = (ROOT / "piano_teacher/adaptive_hybrid_curriculum.py").read_text()
    assert "from .application.coda_midi_curriculum import midi_coda_stages" not in source
    assert "from .fukuda_midi import fukuda_midi_variants" not in source
    assert "component.passage_stages(" in source
    assert "name: str = \"coda-fukuda-midi\"" in source


def test_shared_teaching_selection_is_independent_of_built_in_stage_names():
    for path in ("piano_teacher/lesson_stage_semantics.py",):
        text = (ROOT / path).read_text()
        assert 'startswith("fukuda-midi-")' not in text
        assert 'startswith("coda-")' not in text
    notes = (
        Note(0, 1, 60, 0, 0, "right", "source1"),
        Note(1, 2, 62, 0, 0, "right", "source2"),
        Note(2, 3, 64, 0, 0, "right", "source3"),
        Note(3, 4, 65, 0, 0, "right", "source4"),
    )
    whole = Phrase(1, 1, 1, 0, 4, notes)
    original = ExerciseStage(ExerciseVariant("original", whole,
                                            (0, 1, 2, 3)), origin="original")
    partial = ExerciseStage(
        ExerciseVariant("completely-opaque-17",
                        Phrase(1, 1, 1, 0, 4, (notes[0], notes[2])), (0, 2)),
        origin="future-piano-pedagogue",
        technique="sparse-harmonic-guide", display_name="Harmonic guide")
    selected = teaching_sequence((partial, original))
    assert selected == (partial, original)
    info = describe(partial, original)
    assert info["family"] == "Future Piano Pedagogue"
    assert info["label"] == "Harmonic guide"
    assert info["removed"] == 2
    assert info["meaningful"] is True


def test_grading_relevance_accepts_any_contributor_and_rejects_remote_reductions():
    from piano_teacher.adaptive_hybrid_curriculum import _selection
    notes = tuple(Note(float(i), float(i+0.5), 60+i, 0, 0,
                       "right", f"note{i}") for i in (0, 1, 2, 3, 7))
    source = Phrase(1, 1, 2, 0, 8, notes)
    baseline = ExerciseStage(ExerciseVariant("original", source, tuple(range(5))),
                             origin="original")
    def reduction(removed_index, origin):
        indices = tuple(i for i in range(5) if i != removed_index)
        selected = tuple(notes[i] for i in indices)
        return ExerciseStage(
            ExerciseVariant(f"opaque-{origin}",
                            Phrase(1, 1, 2, 0, 8, selected), indices),
            origin=origin, technique="note-reduction",
            display_name="Source reduction")
    relevant = reduction(0, "foreign-algorithm")
    distant = reduction(4, "different-algorithm")
    selected = _selection((distant, relevant, baseline),
                          {"note0": "wrong"}, kind="learn")
    assert selected == (relevant, baseline)
    assert selected[0].origin == "foreign-algorithm"
