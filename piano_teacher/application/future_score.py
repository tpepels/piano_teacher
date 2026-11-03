"""Pre-engrave the next two MIDI lesson stages on one bounded worker.

The physical MIDI clock owns neither this queue nor its serialization. A
source/revision-keyed result is published only when the genuine Verovio
geometry and semantic model have both completed. Two small lookahead slots
are retained; navigation cannot publish results from an old source piece.
"""
from __future__ import annotations

from collections import OrderedDict, deque
import json
from threading import Lock, Thread

from .score_artifacts import ScoreArtifacts, ScoreSelection
from ..preprocessing_cache import PreprocessingCache

MAX_LOOKAHEAD = 2
MAX_QUEUED = 2


def _reply(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class FutureScore:
    def __init__(self, cache_folder):
        self._folder = cache_folder
        self._guard = Lock()
        self._source = None
        self._pending = deque()
        self._active = False
        self._working = None
        # key -> (prepared reply bytes, ScoreArtifacts)
        self._ready = OrderedDict()
        self._errors = OrderedDict()

    def _enqueue(self, selection: ScoreSelection, number: int,
                 label: str, *, primary: bool) -> None:
        scope = (id(selection.piece), selection.fingerprint)
        if self._source != scope:
            self._source = scope
            self._ready.clear()
            self._errors.clear()
            self._pending.clear()
        key = selection.identity
        if key not in self._ready and key not in self._errors and key != self._working:
            if not any(pending[0].identity == key for pending in self._pending):
                if primary:
                    self._pending.appendleft((selection, number, label, scope))
                else:
                    self._pending.append((selection, number, label, scope))
                while len(self._pending) > MAX_QUEUED:
                    self._pending.pop()
        if not self._active and self._pending:
            self._active = True
            Thread(target=self._build, daemon=True,
                   name="PianoTeacherFutureScore").start()

    def ensure(self, selection: ScoreSelection, *, number: int,
               label: str) -> bytes:
        """Return an already serialized reply, never encode glyphs on MIDI worker."""
        with self._guard:
            self._enqueue(selection, number, label, primary=True)
            key = selection.identity
            if key in self._ready:
                return self._ready[key][0]
            if key in self._errors:
                return _reply({"status": "error", "error": self._errors[key],
                               "step_number": number})
            return _reply({"status": "preparing", "step_number": number})

    def warm(self, selection: ScoreSelection, *, number: int,
             label: str) -> None:
        """Queue stage +2 behind the already requested stage +1."""
        with self._guard:
            self._enqueue(selection, number, label, primary=False)

    def ready(self, selection: ScoreSelection) -> bool:
        with self._guard:
            return selection.identity in self._ready

    def adopt(self, selection: ScoreSelection) -> ScoreArtifacts | None:
        with self._guard:
            item = self._ready.get(selection.identity)
            return item[1] if item is not None else None

    def _build(self) -> None:
        while True:
            with self._guard:
                if not self._pending:
                    self._active = False
                    self._working = None
                    return
                selection, number, label, scope = self._pending.popleft()
                self._working = selection.identity
            try:
                assets = ScoreArtifacts(PreprocessingCache(self._folder))
                layout = assets.geometry(selection)
                model = assets.semantic_score(selection)
                payload = _reply({
                    "status": "ready", "step_number": number,
                    "stage_key": selection.stage_key,
                    "hand": selection.hand, "stage_label": label,
                    "revision": selection.revision,
                    "fingerprint": selection.fingerprint,
                    "layout": layout, "model": model,
                })
                error = ""
            except Exception as exc:
                assets = None
                payload = None
                error = f"{type(exc).__name__}: {exc}"
            with self._guard:
                self._working = None
                if self._source != scope:
                    continue
                key = selection.identity
                if error:
                    self._errors[key] = error
                    self._errors.move_to_end(key)
                    while len(self._errors) > MAX_LOOKAHEAD:
                        self._errors.popitem(last=False)
                else:
                    self._ready[key] = (payload, assets)
                    self._ready.move_to_end(key)
                    while len(self._ready) > MAX_LOOKAHEAD:
                        self._ready.popitem(last=False)
