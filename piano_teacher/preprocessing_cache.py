"""Versioned, bounded, on-disk preprocessed music and engraving cache.

Cache files contain source-identity-bound compressed JSON, never pickle.
The original MIDI is authoritative; old or corrupt entries are cache misses.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .music import BarlineChange, ClefChange, KeySignature, Note, Phrase, Piece

# Bump this whenever the importer, exercise generation, musical notation
# contract or engraving algorithm changes. All historical entries then miss.
CACHE_VERSION = "2026-11-28-authored-attacks-v7"
MAX_CACHE_BYTES = 256 * 1024 * 1024
MAX_ENTRY_BYTES = 20 * 1024 * 1024


def _note(data: dict) -> Note:
    values = dict(data)
    if values.get("spelling") is not None:
        values["spelling"] = tuple(values["spelling"])
    return Note(**values)


def _import_document(piece: Piece) -> dict:
    # Phrase membership refers to the original attacks. Duplicating their
    # complete written notes here made cold import and warm restore expensive.
    result = asdict(replace(piece, notes=(), phrases=()))
    result["notes"] = [note.score_document() for note in piece.notes]
    result["phrases"] = [{**vars(phrase), "notes": [n.source_id for n in phrase.notes]}
                         for phrase in piece.phrases]
    return result


def _piece_from_json(data: dict) -> Piece:
    notes = tuple(_note(n) for n in data["notes"])
    by_id = {note.source_id: note for note in notes}
    return Piece(
        title=str(data["title"]),
        bpm=int(data["bpm"]),
        notes=notes,
        phrases=tuple(Phrase(
            number=int(p["number"]), first_bar=int(p["first_bar"]),
            last_bar=int(p["last_bar"]), start=float(p["start"]),
            end=float(p["end"]), notes=tuple(by_id[sid] for sid in p["notes"]))
            for p in data["phrases"]),
        split_pitch=int(data["split_pitch"]),
        bar_boundaries=tuple(data["bar_boundaries"]),
        time_signatures=tuple(tuple(t) for t in data["time_signatures"]),
        key_signatures=tuple(KeySignature(**item)
                             for item in data["key_signatures"]),
        clef_changes=tuple(ClefChange(**item)
                           for item in data["clef_changes"]),
        import_warnings=tuple(data["import_warnings"]),
        barlines=tuple(BarlineChange(**item)
                       for item in data.get("barlines", [])),
        source_format=data["source_format"],
        midi_ticks_per_beat=int(data.get("midi_ticks_per_beat",0)),
        authored_fingerings=tuple((str(sid), int(finger))
                                  for sid, finger in data.get("authored_fingerings", [])),
    )


class PreprocessingCache:
    """Lossless source import + BPM/hand/phrase-specific engraving reuse."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.enabled = os.environ.get("PIANO_TEACHER_DISABLE_CACHE") != "1"
        self.namespace = hashlib.sha256(CACHE_VERSION.encode()).hexdigest()[:12]

    def key(self, kind: str, *parts: object) -> str:
        blob = json.dumps((self.namespace, kind, parts),
                          ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def _path(self, kind: str, key: str, extension: str) -> Path:
        return self.root / self.namespace / kind / f"{key}.{extension}"

    def _read(self, kind: str, key: str, extension: str) -> bytes | None:
        if not self.enabled:
            return None
        path = self._path(kind, key, extension)
        try:
            if not path.is_file() or path.stat().st_size > MAX_ENTRY_BYTES:
                return None
            return path.read_bytes()
        except OSError:
            return None

    def _write(self, kind: str, key: str, extension: str, data: bytes) -> None:
        if not self.enabled or len(data) > MAX_ENTRY_BYTES:
            return
        target = self._path(kind, key, extension)
        temporary = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".pending-",
                                             dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except OSError:
            # Read-only home directories and full disks must not block lessons.
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def read_json(self, kind: str, key: str) -> dict | None:
        blob = self._read(kind, key, "json.gz")
        if blob is None:
            return None
        try:
            data = json.loads(gzip.decompress(blob))
            if (isinstance(data, dict) and
                    data.get("cache_version") == CACHE_VERSION and
                    isinstance(data.get("payload"), dict)):
                return data["payload"]
        except (OSError, ValueError, TypeError, EOFError):
            pass
        return None

    def write_json(self, kind: str, key: str, payload: dict) -> None:
        try:
            blob = json.dumps({"cache_version": CACHE_VERSION, "payload": payload},
                              separators=(",", ":"), ensure_ascii=False,
                              allow_nan=False).encode("utf-8")
            self._write(kind, key, "json.gz", gzip.compress(blob, compresslevel=3))
        except (TypeError, ValueError):
            pass

    def load_import(self, source: Path, data: bytes) -> tuple[str, Piece]:
        """Return the cached canonical MIDI Piece.

        The original MIDI bytes and canonical source-note IDs always govern
        native notation. A cache hit never creates a second source model.
        """
        from .importing.pieces import import_piece

        fingerprint = hashlib.sha256(data).hexdigest()
        # Discard the old import keys, whose path was reopened after hashing.
        key = self.key("source", "snapshot-v2", fingerprint, source.name)
        cached = self.read_json("source", key)
        if cached is not None:
            try:
                piece = _piece_from_json(cached)
                print("PREPROCESS_SOURCE_CACHE_HIT:", source.name)
                return fingerprint, piece
            except (TypeError, ValueError, KeyError, AttributeError):
                pass
        piece = import_piece(source, data=data)
        if self.enabled:
            self.write_json("source", key, _import_document(piece))
        return fingerprint, piece

    def prune(self) -> None:
        """Bound disk usage; evict oldest cached artifacts across versions."""
        if not self.enabled or not self.root.is_dir():
            return
        try:
            entries = [p for p in self.root.glob("*/*/*") if p.is_file()]
            total = sum(p.stat().st_size for p in entries)
            if total <= MAX_CACHE_BYTES:
                return
            for path in sorted(entries, key=lambda p: p.stat().st_mtime):
                total -= path.stat().st_size
                path.unlink(missing_ok=True)
                if total <= MAX_CACHE_BYTES:
                    break
        except OSError:
            pass
