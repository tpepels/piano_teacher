"""On-demand, non-blocking health check for a local piano music library.

Normal library listing stays metadata-only. This diagnostic uses the *same*
canonical importer as opening a piece and never writes to the source music.
It does not claim that later score engraving or piano MIDI feedback passed.
"""
from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread

from .library import ScoreLibrary
from .importing.pieces import import_piece


class LibraryHealth:
    def __init__(self, library: ScoreLibrary):
        self.library = library
        self._lock = Lock()
        self._generation = 0
        self._folder = ""
        self._cache: dict[tuple[str, str, int, int], dict] = {}
        self._state = self._empty()

    @staticmethod
    def _empty() -> dict:
        return {"started": False, "running": False, "checked": 0,
                "total": 0, "ok": 0, "warning": 0, "error": 0,
                "items": {}, "message": ""}

    def reset(self) -> None:
        with self._lock:
            self._generation += 1
            self._folder = ""
            self._cache.clear()
            self._state = self._empty()

    def snapshot(self) -> dict:
        folder = str(self.library.settings["music_dir"])
        with self._lock:
            if self._folder and folder != self._folder:
                self._generation += 1
                self._folder = ""
                self._cache.clear()
                self._state = self._empty()
            return {**self._state, "items": {
                identifier: dict(value) for identifier, value in self._state["items"].items()}}

    def start(self) -> dict:
        listing = self.library.scan()
        folder = str(self.library.settings["music_dir"])
        with self._lock:
            if self._folder != folder:
                self._generation += 1
                self._folder = folder
                self._cache.clear()
                self._state = self._empty()
            if self._state["running"]:
                return self.snapshot_unlocked()
            self._generation += 1
            generation = self._generation
            entries = [str(item["id"]) for item in listing.get("pieces", [])]
            self._state = {**self._empty(), "started": True,
                           "running": bool(entries), "total": len(entries)}
            if listing.get("error"):
                self._state["message"] = str(listing["error"])
                self._state["running"] = False
                return self.snapshot_unlocked()
            if entries:
                Thread(target=self._worker, args=(generation, folder, entries),
                       name="piano-library-health", daemon=True).start()
            return self.snapshot_unlocked()

    def snapshot_unlocked(self) -> dict:
        # Caller holds _lock.
        return {**self._state, "items": {
            identifier: dict(value) for identifier, value in self._state["items"].items()}}

    def _worker(self, generation: int, folder: str, entries: list[str]) -> None:
        for identifier in entries:
            with self._lock:
                if generation != self._generation:
                    return
            # Resolve each file again to reject symlinks and files removed
            # between the metadata scan and the background inspection.
            try:
                if str(self.library.settings["music_dir"]) != folder:
                    return
                path = self.library.resolve(identifier)
                stamp = path.stat()
                key = (folder, identifier, stamp.st_size, stamp.st_mtime_ns)
                with self._lock:
                    result = self._cache.get(key)
                if result is None:
                    piece, _ = import_piece(Path(path))
                    warnings = list(piece.import_warnings)
                    result = {
                        "status": "warning" if warnings else "ok",
                        "notes": len(piece.notes),
                        "measures": max(0, len(piece.bar_boundaries)-1),
                        "message": " ".join(warnings) if warnings else "Source imported successfully",
                    }
                    with self._lock:
                        if generation != self._generation:
                            return
                        self._cache[key] = result
            except Exception as exc:
                result = {"status": "error", "notes": 0, "measures": 0,
                          "message": str(exc) or type(exc).__name__}
            with self._lock:
                if generation != self._generation:
                    return
                self._state["items"][identifier] = dict(result)
                self._state["checked"] += 1
                self._state[result["status"]] += 1
        with self._lock:
            if generation == self._generation:
                self._state["running"] = False
