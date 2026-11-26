"""Local score library and small, atomically persisted desktop preferences.

Listing is intentionally metadata-only. Scores are parsed only when opened;
each file is hashed once (cached by size and mtime) so saved progress, which
is keyed by the source fingerprint, can be shown beside it.
The client receives relative opaque keys and cannot open paths outside the library.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile


from .importing.pieces import SOURCE_FORMATS as FORMATS  # MIDI and MusicXML
MAX_FILES = 5000
# Preferences of removed features (only Practice Flow remains, owner
# decision 2026-11-23). A saved file holding them loads and is rewritten.
RETIRED_PREFERENCES = frozenset({
    'timing_strategy', 'tempo_strategy', 'exercise_strategy',
    'diagnosis_strategy', 'learner_strategy', 'mistake_response_strategy',
    'practice_flow_migrated'})
EVIDENCE_PREFERENCES = {
    'evidence_retention_days': (365, 7, 3650),
    'evidence_budget_mib': (256, 16, 4096),
}


def default_music_dir() -> Path:
    return Path.home() / 'Music' / 'Piano Teacher'


def default_config_dir() -> Path:
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'piano-teacher'


class ScoreLibrary:
    """Build a navigable local library without modifying imported scores."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir) if config_dir is not None else default_config_dir()
        self.settings_path = self.config_dir / 'settings.json'
        self._fingerprints: dict[str, tuple[int, int, str]] = {}
        migrated = False
        self.settings = {'music_dir': str(default_music_dir()), 'fullscreen': True,
                         'last_piece': '', 'midi_device': '', 'midi_key_ranges': {}, 'metronome': True,
                         'midi_offset_ms': 0,
                         'grade_note_holds': False,
                         **{key: bounds[0] for key, bounds in EVIDENCE_PREFERENCES.items()}}
        if self.settings_path.exists():
            try:
                stored = json.loads(self.settings_path.read_text(encoding='utf-8'))
                if isinstance(stored, dict):
                    migrated = bool(RETIRED_PREFERENCES & stored.keys())
                    for key in self.settings:
                        if key in stored and isinstance(stored[key], type(self.settings[key])):
                            self.settings[key] = stored[key]
            except (OSError, ValueError):
                # Malformed preferences must never prevent the app starting.
                pass
        if config_dir is None and not self.settings_path.exists():
            # First run: create a predictable folder that the user can fill.
            default_music_dir().mkdir(parents=True, exist_ok=True)
        # A previously selected MusicXML file is not a valid MIDI-only library entry.
        recent = self.settings['last_piece']
        if recent and Path(recent).suffix.lower() not in FORMATS:
            self.settings['last_piece'] = ''
        try:
            self._folder = self._normalize_folder(
                self.settings['music_dir'], require_exists=False)
        except (OSError, RuntimeError, ValueError):
            self._folder = self._normalize_folder(
                str(default_music_dir()), require_exists=False)
        self.settings['music_dir'] = str(self._folder)
        try:
            self.settings['midi_offset_ms'] = self._validate_midi_offset(
                self.settings['midi_offset_ms'])
        except ValueError:
            self.settings['midi_offset_ms'] = 0
        try:
            self.settings['midi_key_ranges'] = self._validate_key_ranges(
                self.settings['midi_key_ranges'])
        except ValueError:
            self.settings['midi_key_ranges'] = {}
        for key, (default, _lower, _upper) in EVIDENCE_PREFERENCES.items():
            try:
                self.settings[key] = self._validate_evidence_preference(key, self.settings[key])
            except ValueError:
                self.settings[key] = default
        if migrated:
            # Persist the data migration once; an unwritable folder must not
            # prevent the app starting (the migrated values still apply).
            try:
                self.save()
            except OSError:
                pass

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

    @staticmethod
    def _validate_midi_offset(offset: object) -> int:
        if type(offset) is not int or not 0 <= offset <= 250:
            raise ValueError('MIDI offset must be 0–250 milliseconds')
        return offset

    @staticmethod
    def _validate_key_ranges(ranges: object) -> dict:
        if type(ranges) is not dict or len(ranges) > 128:
            raise ValueError("MIDI keyboard ranges must be a device-to-range mapping")
        result = {}
        for device, value in ranges.items():
            if (type(device) is not str or not device or len(device) > 256
                    or not isinstance(value, (list, tuple)) or len(value) != 2
                    or any(type(p) is not int for p in value)):
                raise ValueError("Invalid MIDI keyboard device or key range")
            low, high = value
            if not 0 <= low < high <= 127:
                raise ValueError("Keyboard range must contain two ordered MIDI pitches")
            result[device] = [low, high]
        return result

    @staticmethod
    def _validate_evidence_preference(key: str, value: object) -> int:
        _default, lower, upper = EVIDENCE_PREFERENCES[key]
        if type(value) is not int or not lower <= value <= upper:
            label = 'Detail retention days' if key == 'evidence_retention_days' else 'Detail budget MiB'
            raise ValueError(f'{label} must be an integer from {lower} to {upper}')
        return value

    def propose_update(self, **changes) -> dict:
        """Validate a complete prospective configuration without persisting it."""
        allowed = {'music_dir', 'fullscreen', 'midi_device', 'midi_key_ranges', 'metronome', 'midi_offset_ms', 'grade_note_holds'}
        allowed.update(EVIDENCE_PREFERENCES)
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError('Unknown preference: ' + ', '.join(sorted(unknown)))
        new = self.settings.copy()
        if 'music_dir' in changes:
            folder = self._normalize_folder(changes['music_dir'])
            if folder != self._folder:
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
        if 'midi_key_ranges' in changes:
            new['midi_key_ranges'] = self._validate_key_ranges(changes['midi_key_ranges'])
        if 'metronome' in changes:
            if not isinstance(changes['metronome'], bool):
                raise ValueError('Metronome must be true or false')
            new['metronome'] = changes['metronome']
        if 'grade_note_holds' in changes:
            if type(changes['grade_note_holds']) is not bool:
                raise ValueError('Grade note holds must be true or false')
            new['grade_note_holds'] = changes['grade_note_holds']
        if 'midi_offset_ms' in changes:
            new['midi_offset_ms'] = self._validate_midi_offset(
                changes['midi_offset_ms'])
        for key in EVIDENCE_PREFERENCES:
            if key in changes:
                new[key] = self._validate_evidence_preference(key, changes[key])
        return new

    def update(self, **changes) -> dict:
        new = self.propose_update(**changes)
        # The filesystem replacement must succeed before publishing this
        # preference snapshot to the active engine and library browser.
        self.save(settings=new)
        self.settings = new
        self._folder = Path(new['music_dir'])
        return self.public_settings()

    def public_settings(self) -> dict:
        return dict(self.settings)

    def save(self, *, settings: dict | None = None) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=self.config_dir)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(self.settings if settings is None else settings,
                          stream, indent=2, ensure_ascii=False)
                stream.write('\n')
            os.replace(tmp, self.settings_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def scan(self) -> dict:
        root = self._folder
        items: list[dict] = []
        if not root.is_dir():
            return {'folder': str(root), 'pieces': [], 'count': 0,
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
                                      'format': 'MIDI'})
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
        return {'folder': str(root), 'pieces': items, 'count': len(items),
                'truncated': len(items) == MAX_FILES, 'last_piece': self.settings['last_piece']}

    def add_fingerprints(self, listing: dict) -> None:
        """Add each piece's source fingerprint. Reads the files (cached by
        size and mtime), so callers do this outside the engine lock."""
        root = Path(listing.get("folder", self._folder))
        for piece in listing.get("pieces", []):
            try:
                piece["fingerprint"] = self._fingerprint(root/piece["id"])
            except OSError:
                piece["fingerprint"] = ""

    def _fingerprint(self, path: Path) -> str:
        """The same sha256 the opened piece's progress is saved under."""
        stat = path.stat()
        key = str(path)
        cached = self._fingerprints.get(key)
        if cached and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            return cached[2]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self._fingerprints[key] = (stat.st_size, stat.st_mtime_ns, digest)
        return digest

    def resolve(self, identifier: str) -> Path:
        if not isinstance(identifier, str) or not identifier or '\x00' in identifier:
            raise ValueError('Invalid library entry')
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
