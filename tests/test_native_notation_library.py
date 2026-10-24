"""The canonical comparison must retain difficult and silent source cases."""
from dataclasses import replace
from pathlib import Path

import mido
import pytest

from scripts import check_native_verovio_overlay as audit
from piano_teacher.music import Note, Phrase
from piano_teacher.exercise_generator import ExerciseVariant


def test_corpus_discovers_both_midi_extensions_without_a_seven_piece_allowlist(tmp_path):
    for name in ("hard.MID", "easy.midi", "ignore.txt"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "directory.mid").mkdir()
    assert [p.name for p in audit.library_sources(tmp_path)] == ["easy.midi", "hard.MID"]


def test_empty_library_and_unmatched_selection_are_errors(tmp_path):
    with pytest.raises(ValueError, match="MIDI"):
        audit.library_sources(tmp_path)
    (tmp_path / "one.mid").write_bytes(b"")
    with pytest.raises(ValueError, match="match"):
        audit.library_sources(tmp_path, only="absent")


def test_observed_extra_ink_and_missing_frames_fail_without_fabricating_global_certainty():
    coverage = dict(full_absence_status='unverified',
                    frames=2, measured_frames=2,
                    initial_viewport=True, terminal_viewport=True,
                    motion_status='verified', clock_gaps=[], motion_errors=[],
                    missing_source_clocks=[], binding_errors=[],
                    expected_heads=1, bound_heads=1, expected_rests=0, bound_rests=0)
    report = dict(complete=False, coverage=coverage,
        measured=[dict(frame='native-0.00000.png', clock=0., region='viewport',
                       status='verified', reason='Owned source ink', evidence={}),
                  dict(frame='native-1.00000.png', clock=1., region='viewport',
                       status='mismatch', reason='An extra detached notehead',
                       evidence={'unexpected': ['head']})])
    errors = audit.absence_evidence_errors(report)
    assert any('native-1.00000.png' in error and 'extra detached notehead' in error
               for error in errors)
    # Unclassified antialiasing/header ink is an explicit limitation, not
    # evidence that a second note was rendered or proof that none was.
    report['measured'][1].update(status='unverified', reason='Unowned ink',
                                  evidence={'unowned_pixels':8})
    assert not audit.absence_evidence_errors(report)
    assert report['coverage']['full_absence_status'] == 'unverified'
    report['coverage']['measured_frames'] = 1
    assert audit.absence_evidence_errors(report)
    report['coverage']['measured_frames'] = 2
    report['measured'] = []
    assert audit.absence_evidence_errors(report)


def test_every_bundled_midi_is_in_the_canonical_corpus():
    paths = audit.library_sources()
    assert len(paths) == 17
    assert any(p.name.startswith("Le_Pianiste") for p in paths)
    assert any(p.name.startswith("Clair_de_Lune") for p in paths)


def test_full_audit_exercises_all_original_sources_before_curriculum(tmp_path,monkeypatch):
    from concurrent.futures import Future
    paths=[]
    for name in ('first.mid','second.midi'):
        path=tmp_path/name
        midi=mido.MidiFile(ticks_per_beat=480)
        track=mido.MidiTrack([mido.Message('note_on',note=60,velocity=80),
                              mido.Message('note_off',note=60,time=1920)])
        midi.tracks.append(track)
        midi.save(path)
        paths.append(path)
    monkeypatch.setattr(audit,'library_sources',lambda **_:tuple(paths))
    calls=[]
    def job(case,source,variant,*_):
        calls.append((Path(case.filename).name,variant is None))
        return dict(errors=[],error_count=0,captured=True,symbols={},nonverified_symbols={})
    monkeypatch.setattr(audit,'_library_job',job)
    class LocalPool:
        def __init__(self,**_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def submit(self,fn,*args):
            future=Future()
            future.set_result(fn(*args))
            return future
    monkeypatch.setattr(audit,'ProcessPoolExecutor',LocalPool)
    summary=audit.audit_library(tmp_path/'output','godot',include_fixtures=False)
    first_stage=next(i for i,(_,original) in enumerate(calls) if not original)
    assert set(calls[:first_stage])=={(p.name,True) for p in paths}
    assert not any(original for _,original in calls[first_stage:])
    assert {name for name,original in calls[first_stage:] if not original}=={p.name for p in paths}
    assert summary['passed'] and summary['sources_checked']==summary['sources_expected']==2
    assert summary['measures_checked']==summary['measures_expected']==2
    assert summary['cases_checked']==summary['cases_expected']==len(calls)


def test_source_changes_during_capture_cannot_produce_a_passing_library(tmp_path,monkeypatch):
    from concurrent.futures import Future
    source=tmp_path/'changing.mid'
    midi=mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message('note_on',note=60,velocity=80),
                                      mido.Message('note_off',note=60,time=1920)]))
    midi.save(source)
    monkeypatch.setattr(audit,'library_sources',lambda **_:(source,))
    def job(*_):
        if mido.MidiFile(source).tracks[0][0].note==60:
            midi.tracks[0][0].note=61
            midi.tracks[0][1].note=61
            midi.save(source)
        return dict(errors=[],error_count=0,captured=True,symbols={},nonverified_symbols={})
    monkeypatch.setattr(audit,'_library_job',job)
    class LocalPool:
        def __init__(self,**_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def submit(self,fn,*args):
            result=Future();result.set_result(fn(*args));return result
    monkeypatch.setattr(audit,'ProcessPoolExecutor',LocalPool)
    summary=audit.audit_library(tmp_path/'output','godot',include_fixtures=False)
    assert not summary['passed']
    assert any('changed during' in failure for failure in summary['failures'])


@pytest.mark.parametrize('change',['added','removed'])
def test_library_membership_changes_during_capture_block_completeness(tmp_path,monkeypatch,change):
    from concurrent.futures import Future
    source=tmp_path/'first.mid'
    midi=mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message('note_on',note=60,velocity=80),
                                      mido.Message('note_off',note=60,time=1920)]))
    midi.save(source)
    discover=audit.library_sources
    monkeypatch.setattr(audit,'library_sources',lambda **options:discover(tmp_path,**options))
    def job(*_):
        if change=='added':midi.save(tmp_path/'added.mid')
        elif source.exists():source.unlink()
        return dict(errors=[],captured=True,symbols={},nonverified_symbols={})
    monkeypatch.setattr(audit,'_library_job',job)
    class LocalPool:
        def __init__(self,**_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def submit(self,fn,*args):
            future=Future();future.set_result(fn(*args));return future
    monkeypatch.setattr(audit,'ProcessPoolExecutor',LocalPool)
    summary=audit.audit_library(tmp_path/'output','godot',include_fixtures=False)
    assert not summary['passed']
    assert any('membership changed' in error for error in summary['failures'])


@pytest.mark.parametrize('stale',[False,True])
def test_retained_capture_recheck_recaptures_changed_inputs(tmp_path,monkeypatch,stale):
    directory=tmp_path/'source'/'case'
    directory.mkdir(parents=True)
    (directory/'capture-manifest.json').write_text('{}')
    monkeypatch.setattr(audit,'_library_piece',lambda *_:None)
    monkeypatch.setattr(audit,'fixture',lambda *_,**__:(None,None))
    calls=[]
    def compare(*_,**options):
        reuse=options.get('reuse_captures',False)
        calls.append(reuse)
        if reuse and stale:
            raise AssertionError('Cached renderer dependencies changed')
        return dict(errors=[],nonverified_symbols={},whole_window_coverage=dict(symbols={}))
    monkeypatch.setattr(audit,'run',compare)
    case=audit.AuditCase('case','example.mid',1,1)
    result=audit._library_job(case,None,None,directory,'godot',reuse_captures=True)
    assert result['captured'] and not result['errors']
    assert calls==([True,False] if stale else [True])


def test_variant_rejects_invented_duplicated_and_changed_source_notes():
    source = Phrase(1, 1, 1, 0, 4, (
        Note(0, 1, 60, 0, 0, "right", "source-a"),
        Note(1, 2, 64, 0, 0, "right", "source-b")))
    valid = ExerciseVariant("skeleton", replace(source, notes=(source.notes[0],)), (0,))
    assert not audit.variant_errors(source, valid)
    changed = replace(valid, phrase=replace(valid.phrase, notes=(replace(source.notes[0], pitch=61),)))
    assert audit.variant_errors(source, changed)
    duplicate = replace(valid, phrase=replace(valid.phrase, notes=(source.notes[0], source.notes[0])), source_indices=(0, 0))
    assert audit.variant_errors(source, duplicate)
    invented = replace(valid, source_indices=(99,))
    assert audit.variant_errors(source, invented)


def test_silent_measure_is_a_real_renderable_window(tmp_path):
    path = tmp_path / "silent-middle.mid"
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.extend((mido.Message("note_on", note=60, velocity=80),
                  mido.Message("note_off", note=60, time=480),
                  mido.Message("note_on", note=64, velocity=80, time=3360),
                  mido.Message("note_off", note=64, time=480)))
    midi.save(path)
    data, _ = audit.fixture(audit.AuditCase("silent", str(path), 2, 2))
    assert data["model"]["notes"] == []
    assert len(data["model"]["measures"]) == 1
    assert {e["staff"] for e in data["model"]["notation_events"] if e["kind"] == "rest"} == {"left", "right"}


def test_incomplete_required_symbol_evidence_fails_with_source_context():
    report = {"complete": False, "measured": [
        {"source_id": "n7", "measure": 3, "staff": "left", "voice": "2",
         "features": {"flag": {"status": "ambiguous", "reason": "shared ink"}}}]}
    errors = audit.feature_evidence_errors(report)
    assert len(errors) == 1
    assert all(term in errors[0] for term in ("n7", "3", "left", "flag", "shared ink"))


def test_complete_status_cannot_hide_a_failed_symbol():
    report = {"complete": True, "measured": [
        {"source_id": "n1", "measure": 1, "staff": "right",
         "features": {"stem": {"status": "mismatch", "reason": "detached"}}}]}
    assert audit.feature_evidence_errors(report)


def test_window_keeps_the_attack_context_of_incoming_sustained_notes():
    from types import SimpleNamespace
    piece = SimpleNamespace(bar_boundaries=(0, 4, 8, 12), notes=(
        Note(3, 9, 60, 0, 0, "right", "held"),
        Note(8, 9, 64, 0, 0, "right", "new")))
    assert audit.context_first_bar(piece, 3) == 1
    assert audit.context_first_bar(piece, 2) == 1
    assert audit.context_first_bar(piece, 1) == 1


def test_original_windows_cover_silence_and_every_hand(tmp_path):
    from types import SimpleNamespace
    piece = SimpleNamespace(bar_boundaries=(0, 4, 8, 12), notes=(
        Note(0, 1, 60, 0, 0, "right", "one"),))
    jobs = tuple(audit.original_cases(Path("example.mid"), piece, max_bars=1))
    assert len(jobs) == 9
    assert {(c.first_bar, c.last_bar, c.hand) for c in jobs} == {
        (bar, bar, hand) for bar in (1, 2, 3) for hand in ("right", "left", "both")}


def test_payload_is_checked_against_exact_selected_source_events():
    phrase = Phrase(1, 1, 1, 0, 4, (Note(0, 1, 60, 0, 0, "right", "source-a"),))
    model = {"notes": [{"id": "source-a", "midi_pitch": 61, "onset_beats": 0,
                        "duration_beats": 1, "velocity": 85, "hand": "right",
                        "track": 0, "channel": 0}],
             "active_hand": "both", "active_note_ids": ["source-a"]}
    assert audit.selected_source_errors(phrase, model)
    model["notes"][0]["midi_pitch"] = 60
    assert not audit.selected_source_errors(phrase, model)
    model["active_note_ids"] = []
    assert audit.selected_source_errors(phrase, model)


def test_capture_clocks_include_silent_bars_and_both_sides_of_transitions():
    xml = '''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name></score-part></part-list><part id="RH">
    <measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><rest/><duration>4</duration><type>whole</type></note></measure>
    <measure number="2"><note><rest/><duration>4</duration><type>whole</type></note></measure></part></score-partwise>'''
    assert audit.capture_clocks(xml) == [0.0, .0625, .125, 3.9375, 4.0, 4.0625, 8.0]


def test_legible_verovio_chord_stems_are_not_rejected_by_a_fixed_three_space_rule():
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    folder = Path(__file__).parent/"fixtures/native_structure_key"
    report = verify_note_feature_pixels((folder/"score.musicxml").read_text(), folder)
    stems = [row["features"]["stem"] for row in report["measured"]
             if row["staff"] == "right" and row["beat"] == 3.0]
    assert len(stems) == 3
    assert all(stem["status"] == "verified" for stem in stems), stems


def test_reference_stem_allowance_still_rejects_a_truncated_chord_stem(tmp_path):
    from shutil import copytree
    from PIL import Image, ImageDraw
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    folder = Path(__file__).parent/"fixtures/native_structure_key"
    copytree(folder, tmp_path, dirs_exist_ok=True)
    path = tmp_path/"native-3.00000.png"
    image = Image.open(path).convert("RGB")
    ImageDraw.Draw(image).rectangle((653, 90, 664, 167), fill="#102923")
    image.save(path)
    report = verify_note_feature_pixels((tmp_path/"score.musicxml").read_text(), tmp_path)
    stems = [row["features"]["stem"] for row in report["measured"]
             if row["staff"] == "right" and row["beat"] == 3.0]
    assert len(stems) == 3
    assert all(stem["status"] != "verified" for stem in stems)


def test_downward_32nd_flag_uses_the_font_attachment_origin():
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    folder = Path(__file__).parent/"fixtures/native_flag_down_32"
    xml = (folder/"score.musicxml").read_text()
    def selected(text):
        report = verify_note_feature_pixels(text, folder)
        return next(r for r in report["measured"] if r["beat"] == 5.5 and
                    r["staff"] == "right" and tuple(r["spelling"]) == ("D", 0, 6))["features"]["flag"]
    assert selected(xml)["status"] == "verified"
    assert selected(xml.replace("<type>32nd</type>", "<type>16th</type>"))["status"] != "verified"


def test_long_reference_uses_the_same_pagination_as_production():
    from piano_teacher.score import import_piece
    path = Path(__file__).parent/"fixtures/musical_fidelity/xml_long_multipage.musicxml"
    piece, _ = import_piece(path)
    assert len(piece.bar_boundaries)-1 > 12
    _, engraving = audit.fixture(audit.AuditCase("long-production", str(path),
        1, len(piece.bar_boundaries)-1), piece=piece)
    assert not engraving.layout["continuous_score"]
