"""Pre-engrave the next MIDI lesson stage on one bounded in-process worker.

A complete, source-identity-checked score bundle is published only after
its semantic model, Verovio assets and required source geometry agree.
The current MIDI callback/transport never waits for that work.
"""
from __future__ import annotations

import json
from threading import Lock, Thread

from .score_artifacts import ScoreArtifacts, ScoreSelection
from ..preprocessing_cache import PreprocessingCache


def _reply(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class FutureScore:
    def __init__(self, cache_folder):
        self._folder = cache_folder
        self._guard = Lock()
        self._key = None
        self._pending = None
        self._active = False
        self._result = None
        self._payload: bytes | None = None
        self._artifacts = None
        self._error = ""

    def ensure(self, selection: ScoreSelection, *, number: int,
               label: str) -> bytes:
        key = selection.identity
        with self._guard:
            if self._key != key:
                self._key = key
                self._pending = (selection, number, label)
                self._result = None
                self._payload = None
                self._artifacts = None
                self._error = ""
            if not self._active and self._pending is not None:
                self._active = True
                Thread(target=self._build, daemon=True,
                       name="PianoTeacherFutureScore").start()
            if self._payload is not None:
                return self._payload
            if self._error:
                return _reply({"status": "error", "error": self._error,
                               "step_number": number})
            return _reply({"status": "preparing", "step_number": number})

    def ready(self, selection: ScoreSelection) -> bool:
        with self._guard:
            return self._key == selection.identity and self._result is not None

    def adopt(self, selection: ScoreSelection) -> ScoreArtifacts | None:
        with self._guard:
            if self._key != selection.identity or self._result is None:
                return None
            return self._artifacts

    def _build(self) -> None:
        while True:
            with self._guard:
                request = self._pending
                self._pending = None
                if request is None:
                    self._active = False
                    return
            selection, number, label = request
            try:
                # Separate, bounded score owner: no mutation of the active
                # lesson or native UI, and no second MIDI/transport engine.
                assets = ScoreArtifacts(PreprocessingCache(self._folder))
                layout = assets.geometry(selection)
                model = assets.semantic_score(selection)
                result = {"step_number": number,
                          "stage_key": selection.stage_key,
                          "hand": selection.hand,
                          "stage_label": label,
                          "revision": selection.revision,
                          "fingerprint": selection.fingerprint,
                          "layout": layout, "model": model}
                # Build the heavy JSON reply on the background worker, never
                # during a MIDI assessment or authoritative clock tick.
                payload = _reply({"status": "ready", **result})
                error = ""
            except Exception as exc:
                result = None
                payload = None
                assets = None
                error = f"{type(exc).__name__}: {exc}"
            with self._guard:
                if self._key == selection.identity:
                    self._result = result
                    self._payload = payload
                    self._artifacts = assets
                    self._error = error
