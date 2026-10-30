"""Own source-bound Listen jobs, readiness and count-in preparation.

Rendering runs outside the supplied application lock. Results publish under
that lock as captured audio facts; the application consumes failures and owns
its transport transitions. No engine, learning plan or callback is retained.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from threading import RLock, Thread
import uuid

from ..demo import DemoAudioCache
from ..exercise_generator import ExerciseVariant
from ..exercise_contracts import TempoMap
from ..lesson_timing import lead_in_beats, preparation_meter
from ..measure_grid import phrase_grid
from ..music import source_note_id


@dataclass(frozen=True)
class ListenSelection:
    variant: ExerciseVariant
    bpm: float
    stage_key: str
    revision: int
    bar_boundaries: tuple[float, ...]
    time_signatures: tuple[tuple[float, int, int], ...]
    tempo_map: TempoMap | None = None


@dataclass(frozen=True)
class ListenStart:
    count_in_bar_beats: float
    count_in_meter: tuple[int, int]
    count_in_beats: float
    delay_seconds: float


class ListenSession:
    def __init__(self, cache_dir: Path, *, cache=None, lock=None):
        self.cache_dir = Path(cache_dir)
        self.cache = cache
        self.thread: Thread | None = None
        self._lock = lock if lock is not None else RLock()
        self.cancel()

    def cancel(self) -> None:
        with self._lock:
            self._selection: ListenSelection | None = None
            self._info: dict | None = None
            self._audio = None
            self._score_ready = False
            self._started = False
            self._failure: str | None = None

    def prepare(self, selected: ListenSelection) -> str:
        with self._lock:
            self.cancel()
            self._selection = selected
            if self.cache is None:
                self.cache = DemoAudioCache(self.cache_dir)
            variant = selected.variant
            audio_end = max(variant.phrase.end,
                max((note.end for note in variant.notes), default=variant.phrase.end))
            token = uuid.uuid4().hex
            self._info = {
                "token": token, "url": "", "audio_available": False,
                "instrument": "Preparing piano audio",
                "duration_seconds": (selected.tempo_map.duration_seconds
                                     if selected.tempo_map is not None
                                     else (audio_end-variant.phrase.start)*60/selected.bpm),
                "ready": False, "stage_key": selected.stage_key,
                "source_ids": [f"{selected.stage_key}:{index}" for index in variant.source_indices],
                "canonical_source_ids": [source_note_id(note, index)
                    for index, note in enumerate(variant.notes)],
            }
            self.thread = Thread(target=self._render, args=(self.cache, selected, token),
                                 name="piano-demo-render", daemon=True)
            self.thread.start()
            return token

    def _render(self, cache, selected: ListenSelection, token: str) -> None:
        try:
            variant = selected.variant
            if selected.tempo_map is not None:
                tempo_map = selected.tempo_map
                offset = variant.phrase.start
                # Audio synthesis takes fixed-BPM notes. Warp note positions
                # through the exact tempo map while retaining source IDs.
                warped_notes = tuple(replace(note,
                    start=offset+tempo_map.seconds_at(note.start-offset)*selected.bpm/60,
                    end=offset+tempo_map.seconds_at(note.end-offset)*selected.bpm/60)
                    for note in variant.notes)
                warped = replace(variant.phrase, notes=warped_notes,
                    end=offset+tempo_map.duration_seconds*selected.bpm/60)
                variant = replace(variant, phrase=warped)
            audio = cache.render(variant, selected.bpm)
        except Exception as exc:
            with self._lock:
                if self._info is not None and self._info["token"] == token:
                    self._failure = f"Listen audio could not be prepared: {exc}"
                    self._info["error"] = self._failure
            return
        with self._lock:
            if self._info is not None and self._info["token"] == token:
                self._audio = audio
                self._info.update(url=f"/demo.wav?token={token}", audio_available=True,
                    duration_seconds=audio.duration_seconds, instrument=audio.instrument,
                    sampled=audio.instrument != "Basic synthesized piano")

    def snapshot(self) -> dict | None:
        with self._lock:
            return deepcopy(self._info)

    def audio_path(self, token: str) -> Path:
        with self._lock:
            if self._info is None or token != self._info["token"] or self._audio is None:
                raise ValueError("This audio example is no longer current")
            return self._audio.path

    def take_failure(self) -> str | None:
        with self._lock:
            failure, self._failure = self._failure, None
            return failure

    def retarget_score(self, revision: int) -> None:
        with self._lock:
            if self._selection is not None and not self._started:
                self._selection = replace(self._selection, revision=revision)
                self._score_ready = False

    def acknowledge_score(self, revision: int) -> bool:
        with self._lock:
            if (self._selection is None or self._info is None or "error" in self._info
                    or revision != self._selection.revision):
                return False
            self._score_ready = True
            return True

    def acknowledge_audio(self, token: str) -> bool:
        with self._lock:
            if self._info is None or self._info["token"] != token or not self._info["audio_available"]:
                return False
            self._info["ready"] = True
            return True

    def begin_playback(self, revision: int) -> ListenStart | None:
        with self._lock:
            selected = self._selection
            if (selected is None or self._info is None or self._audio is None or self._started
                    or revision != selected.revision or not self._score_ready or not self._info["ready"]):
                return None
            phrase = selected.variant.phrase
            grid = phrase_grid(phrase, selected.bar_boundaries)
            bar_beats = grid[1]-grid[0]
            meter = next(((num, den) for beat, num, den in
                sorted(selected.time_signatures, reverse=True) if beat <= phrase.start+1e-7), None)
            meter = preparation_meter(meter, selected.time_signatures, phrase.start)
            count_meter = meter if meter is not None else (max(1, round(bar_beats)), 4)
            if meter is not None:
                bar_beats = meter[0]*4/meter[1]
            count_beats = lead_in_beats(bar_beats, selected.bpm)
            self._started = True
            return ListenStart(bar_beats, count_meter, count_beats, count_beats*60/selected.bpm)

    def finished(self, *, now: float, run_at: float) -> bool:
        with self._lock:
            return bool(self._started and self._info is not None
                        and now >= run_at+self._info["duration_seconds"])
