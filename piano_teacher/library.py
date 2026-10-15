"""Local score library and small, atomically persisted desktop preferences.

Listing is intentionally metadata-only. Scores are parsed only when opened.
The client receives relative opaque keys and cannot open paths outside the library.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .warmups import catalog as built_in_warmups, is_warmup, materialize

FORMATS = {'.mid', '.midi', '.musicxml', '.xml', '.mxl'}
MAX_FILES = 5000


def default_music_dir() -> Path:
    return Path.home() / 'Music' / 'Piano Teacher'


def default_config_dir() -> Path:
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'piano-teacher'


class ScoreLibrary:
    """Build a navigable local library without modifying imported scores."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir) if config_dir is not None else default_config_dir()
        self.settings_path = self.config_dir / 'settings.json'
        self.settings = {'music_dir': str(default_music_dir()), 'fullscreen': True,
                         'last_piece': '', 'midi_device': '', 'metronome': True}
        if self.settings_path.exists():
            try:
                stored = json.loads(self.settings_path.read_text(encoding='utf-8'))
                if isinstance(stored, dict):
                    for key in self.settings:
                        if key in stored and isinstance(stored[key], type(self.settings[key])):
                            self.settings[key] = stored[key]
            except (OSError, ValueError):
                # Malformed preferences must never prevent the app starting.
                pass
        if config_dir is None and not self.settings_path.exists():
            # First run: create a predictable folder that the user can fill.
            default_music_dir().mkdir(parents=True, exist_ok=True)
        self._folder = self._normalize_folder(self.settings['music_dir'], require_exists=False)
        self.settings['music_dir'] = str(self._folder)

    @staticmethod
    def _normalize_folder(folder: str, *, require_exists: bool = True) -> Path:
        if not isinstance(folder, str) or not folder.strip():
            raise ValueError('Choose a music folder')
        path = Path(os.path.expandvars(folder)).expanduser().resolve()
        if require_exists and not path.is_dir():
            raise ValueError(f'Folder does not exist: {path}')
        if path.exists() and not path.is_dir():
            raise ValueError('Music folder must be a directory')
        return path

    def update(self, **changes) -> dict:
        allowed = {'music_dir', 'fullscreen', 'midi_device', 'metronome'}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError('Unknown preference: ' + ', '.join(sorted(unknown)))
        new = self.settings.copy()
        if 'music_dir' in changes:
            folder = self._normalize_folder(changes['music_dir'])
            if folder != self._folder and not is_warmup(str(new['last_piece'])):
                new['last_piece'] = ''
            new['music_dir'] = str(folder)
        if 'fullscreen' in changes:
            if not isinstance(changes['fullscreen'], bool):
                raise ValueError('Fullscreen must be true or false')
            new['fullscreen'] = changes['fullscreen']
        if 'midi_device' in changes:
            if not isinstance(changes['midi_device'], str):
                raise ValueError('Invalid MIDI device')
            new['midi_device'] = changes['midi_device']
        if 'metronome' in changes:
            if not isinstance(changes['metronome'], bool):
                raise ValueError('Metronome must be true or false')
            new['metronome'] = changes['metronome']
        self.settings = new
        self._folder = Path(new['music_dir'])
        self.save()
        return self.public_settings()

    def public_settings(self) -> dict:
        return self.settings.copy()

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=self.config_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(self.settings, stream, indent=2, ensure_ascii=False)
                stream.write('\n')
            os.replace(tmp, self.settings_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def scan(self) -> dict:
        root = self._folder
        items: list[dict] = []
        if not root.is_dir():
            return {'folder': str(root), 'pieces': [], 'warmups': built_in_warmups(), 'count': 0,
                    'error': 'Music folder is unavailable. Choose a folder in Settings.',
                    'last_piece': self.settings['last_piece']}
        try:
            for directory, dirs, files in os.walk(root, followlinks=False):
                # Symlinked folders are not traversed, even if the destination is inside root.
                dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink() and not d.startswith('.'))
                for filename in sorted(files):
                    path = Path(directory) / filename
                    if path.suffix.lower() not in FORMATS or path.is_symlink():
                        continue
                    try:
                        relative = path.relative_to(root).as_posix()
                        if not path.is_file():
                            continue
                        items.append({'id': relative, 'title': path.stem.replace('_', ' '),
                                      'folder': path.relative_to(root).parent.as_posix() if path.parent != root else '',
                                      'format': 'MIDI' if path.suffix.lower() in {'.mid', '.midi'} else 'MusicXML'})
                    except OSError:
                        continue
                    if len(items) >= MAX_FILES:
                        break
                if len(items) >= MAX_FILES:
                    break
        except OSError as exc:
            return {'folder': str(root), 'pieces': [], 'count': 0,
                    'error': str(exc), 'last_piece': self.settings['last_piece']}
        items.sort(key=lambda x: (x['title'].casefold(), x['id'].casefold()))
        return {'folder': str(root), 'pieces': items, 'warmups': built_in_warmups(), 'count': len(items),
                'truncated': len(items) == MAX_FILES, 'last_piece': self.settings['last_piece']}

    def resolve(self, identifier: str) -> Path:
        if not isinstance(identifier, str) or not identifier or '\x00' in identifier:
            raise ValueError('Invalid library entry')
        # Known built-ins bypass the personal music folder, but never accept
        # user-supplied paths or unknown warm-up identifiers.
        if identifier.startswith('warmup:'):
            return materialize(identifier, self.config_dir / 'warmups')
        candidate = Path(identifier)
        if candidate.is_absolute() or '..' in candidate.parts:
            raise ValueError('Library entry must stay inside the music folder')
        path = (self._folder / candidate).resolve()
        if not path.is_relative_to(self._folder) or path.suffix.lower() not in FORMATS or not path.is_file():
            raise ValueError('Library entry not found')
        if any((self._folder.joinpath(*candidate.parts[:i])).is_symlink() for i in range(1, len(candidate.parts) + 1)):
            raise ValueError('Symbolic links are not supported')
        return path

    def mark_opened(self, identifier: str) -> None:
        self.resolve(identifier)
        self.settings['last_piece'] = identifier
        self.save()
