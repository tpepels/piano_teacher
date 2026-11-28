"""CPU inference port of Lumikey 0.3.0 with Piano Teacher's physical constraints."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from itertools import groupby
from math import inf
from operator import attrgetter

import numpy as np
import onnxruntime as ort

from .model_assets import ONNX_RUNTIME_VERSION, verified_model_bytes
from .overlap import (
    BLACK_PITCH_CLASSES,
    EPS,
    FixedOverlapIndex,
    HandNote,
    chord_fingers,
    partial_allowed,
)

_FINGERS = range(1, 6)
_FIXED_CONFLICT = "Conflicting fixed fingering or unplayable overlap"
_UNPLAYABLE = "No physically available finger for these overlapping keys/constraints"


def _fill_tokens(tokens, notes, index, last_pitch, last_time):
    """Write the upstream 26×5 token layout, rounding on float32 assignment."""
    current = notes[index]
    reference = (current.pitch - 21) / 87.0
    for finger, (pitch, elapsed) in enumerate(zip(last_pitch, last_time, strict=True)):
        offset = (pitch - 21) / 87.0 - reference if pitch >= 0 else -1.0
        black_key = pitch % 12 in BLACK_PITCH_CLASSES if pitch >= 0 else -1.0
        age = max(0.0, min(elapsed, 10.0)) / 10.0
        tokens[finger] = offset, age, black_key, 0.0, -1.0
    pitch_class = (current.pitch - 21) % 12 / 11.0
    tokens[5] = pitch_class, 0.0, current.pitch % 12 in BLACK_PITCH_CLASSES, 0.5, -1.0
    lookahead = notes[index + 1:index + 21]
    for row, note in enumerate(lookahead, 6):
        offset = (note.pitch - 21) / 87.0 - reference
        elapsed = min((note.time - current.time) / 1000.0, 10.0) / 10.0
        finger_hint = (note.finger - 1) / 4.0 if note.finger is not None else -1.0
        black_key = note.pitch % 12 in BLACK_PITCH_CLASSES
        tokens[row] = offset, elapsed, black_key, 1.0, finger_hint
    tokens[6 + len(lookahead):] = -1.0


def _choose(note, chord, occupied, logits):
    candidates = chord_fingers(chord, note, occupied)
    if note.finger is not None:
        reason = "" if note.finger in candidates else _FIXED_CONFLICT
        return note.finger, note.finger, reason
    if not candidates:
        candidates = {
            finger for finger in _FINGERS if partial_allowed(note, finger, occupied)
        }
    if candidates:
        # The first maximum wins, as in the upstream Float32Array argmax.
        finger = max(sorted(candidates), key=lambda candidate: logits[candidate - 1])
        return finger, finger, ""
    # Rejected predictions still advance model history with the raw argmax.
    return None, int(logits.argmax()) + 1, _UNPLAYABLE


def _run_hand(notes, weights):
    if not notes:
        return []
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(weights, options, providers=["CPUExecutionProvider"])
    tensor = np.empty((1, 26, 5), dtype=np.float32)
    inputs = {"tokens": tensor}
    tokens = tensor[0]
    last_pitch, last_time = [-1] * 5, [inf] * 5
    held = []
    assignments = []
    overlap_index = FixedOverlapIndex(note for note in notes if note.finger is not None)
    index = 0
    for time, members in groupby(notes, key=attrgetter("time")):
        chord = tuple(members)
        group_fixed = list(dict.fromkeys(
            match for note in chord for match in overlap_index.overlapping(note)
        ))
        held = [note for note in held if note.end > time + EPS]
        for note in chord:
            _fill_tokens(tokens, notes, index, last_pitch, last_time)
            logits = session.run(["logits"], inputs)[0].reshape(-1)
            if logits.size != 5 or not np.isfinite(logits).all():
                raise ValueError("Invalid model logits")
            finger, history, reason = _choose(note, chord, held + group_fixed, logits)
            assignments.append({
                "source_id": note.source_id, "finger": finger, "reason": reason,
            })
            if finger is not None and note.end > time + EPS:
                held.append(replace(note, finger=finger))
            last_pitch[history - 1] = note.pitch
            last_time[history - 1] = -note.duration / 1000.0
            index += 1
            if index < len(notes):
                delta = (notes[index].time - time) / 1000.0
                last_time = [elapsed + delta for elapsed in last_time]
    return assignments


def predict_assignments(notes, model_paths):
    """Verify both models, then run each hand's sequential state independently."""
    if ort.__version__ != ONNX_RUNTIME_VERSION:
        raise ValueError(
            f"Expected ONNX Runtime {ONNX_RUNTIME_VERSION}, found {ort.__version__}"
        )
    hands = {"left": [], "right": []}
    for note in notes:
        hand = "left" if note["left"] else "right"
        hands[hand].append(HandNote(
            source_id=note["source_id"], pitch=note["note"], time=float(note["time"]),
            duration=float(note["duration"]), left=note["left"],
            finger=note.get("finger"),
        ))
    weights = {hand: verified_model_bytes(model_paths[hand], hand) for hand in hands}
    with ThreadPoolExecutor(max_workers=2) as executor:
        left, right = [
            executor.submit(
                _run_hand,
                sorted(hand_notes, key=attrgetter("time", "pitch")),
                weights[hand],
            )
            for hand, hand_notes in hands.items()
        ]
        return left.result() + right.result()
