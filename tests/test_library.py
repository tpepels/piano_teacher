from pathlib import Path
import json
import pytest

from piano_teacher.library import ScoreLibrary
from piano_teacher.server import PracticeEngine


def populated(tmp_path):
    music = tmp_path / 'My Scores'
    music.mkdir()
    (music / 'Bach.mid').write_bytes(b'midi example')
    (music / 'notes.txt').write_text('ignore')
    (music / 'Etudes').mkdir()
    (music / 'Etudes' / 'Chopin.musicxml').write_text('xml example')
    (music / '.drafts').mkdir()
    (music / '.drafts' / 'hidden.mid').write_bytes(b'ignore')
    library = ScoreLibrary(config_dir=tmp_path / 'config')
    library.update(music_dir=str(music))
    return library, music


def test_library_lists_supported_scores_recursively_without_parsing(tmp_path):
    library, _ = populated(tmp_path)
    listing = library.scan()
    assert listing['count'] == 2
    assert [p['id'] for p in listing['pieces']] == ['Bach.mid', 'Etudes/Chopin.musicxml']
    assert listing['pieces'][1]['format'] == 'MusicXML'
    assert listing['pieces'][1]['folder'] == 'Etudes'
    assert not listing.get('error')


def test_library_rejects_path_escape_unsupported_files_and_links(tmp_path):
    library, folder = populated(tmp_path)
    outside = tmp_path / 'outside.mid'
    outside.write_bytes(b'secret')
    (folder / 'bad.mid').symlink_to(outside)
    assert library.scan()['count'] == 2
    assert library.resolve('Bach.mid') == folder / 'Bach.mid'
    for path in ('../outside.mid', '/etc/passwd', 'notes.txt', 'bad.mid', '', 'Etudes/../../outside.mid'):
        with pytest.raises(ValueError):
            library.resolve(path)


def test_settings_persist_and_reset_recent_on_folder_change(tmp_path):
    library, folder = populated(tmp_path)
    library.mark_opened('Bach.mid')
    library.update(fullscreen=False, midi_device='USB Piano')
    again = ScoreLibrary(config_dir=tmp_path / 'config')
    assert again.public_settings()['fullscreen'] is False
    assert again.public_settings()['midi_device'] == 'USB Piano'
    assert again.scan()['last_piece'] == 'Bach.mid'
    new_folder = tmp_path / 'new pieces'
    new_folder.mkdir()
    again.update(music_dir=str(new_folder))
    assert again.scan()['count'] == 0
    assert again.public_settings()['last_piece'] == ''
    assert json.loads((tmp_path / 'config' / 'settings.json').read_text())['music_dir'] == str(new_folder)
    with pytest.raises(ValueError):
        again.update(music_dir=str(tmp_path / 'missing'))
    assert again.public_settings()['music_dir'] == str(new_folder)


def test_missing_folder_is_reported_without_exception(tmp_path):
    lib = ScoreLibrary(config_dir=tmp_path / 'config')
    info = lib.scan()
    assert info['count'] == 0
    assert 'error' in info


def test_backend_library_open_loads_only_selected_file(tmp_path, monkeypatch):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    music = tmp_path / 'My Music'
    music.mkdir()
    (music / 'Demo.mid').write_bytes(b'valid fake midi')
    engine.set_preferences(music_dir=str(music))
    opened = []
    monkeypatch.setattr(engine, 'load', lambda path: opened.append(path))
    engine.load_library('Demo.mid')
    assert opened == [str(music / 'Demo.mid')]
    assert engine.library_listing()['last_piece'] == 'Demo.mid'
    with pytest.raises(ValueError):
        engine.load_library('../other.mid')
    assert len(opened) == 1
    engine.db.close()


def test_bad_preferences_do_not_override_valid_saved_config(tmp_path):
    lib, _ = populated(tmp_path)
    with pytest.raises(ValueError):
        lib.update(fullscreen='yes')
    with pytest.raises(ValueError):
        lib.update(unexpected=True)
    assert lib.public_settings()['fullscreen'] is True
