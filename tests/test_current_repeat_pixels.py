"""Real pixel proof for current immutable repeat source + meter rest + header.

No historical looping-score/camera assumptions. The current native queue
renders the same source twice with a genuine full-measure rest in between.
The fixed playhead never moves; both source openings are photographed at it.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw

from piano_teacher.notation.pixel_ink import translating_ink
from piano_teacher.notation.pixel_proof import PLAYHEAD_FRACTION
from scripts.check_native_verovio_overlay import AuditCase, fixture

ROOT = Path(__file__).resolve().parents[1]


def _score_ink(image):
    return translating_ink(image)


def _similarity(left, right):
    union = np.count_nonzero(left | right)
    return (np.count_nonzero(left & right) / union) if union else 0.0


def test_replay_has_real_rest_and_new_source_header_in_forward_queue(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    assert godot, "Godot 4.7.2 required for real native pixels"
    case = AuditCase("modern-repeat-pixels",
        "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi",1,1,"both")
    data, _ = fixture(case)
    assert not data["source_errors"]
    payload = tmp_path / "source.json"
    payload.write_text(json.dumps(data))
    folder = tmp_path / "captures"
    folder.mkdir()
    run = subprocess.run([
        godot, "--path", str(ROOT/"godot"), "--audio-driver","Dummy",
        "--rendering-method","gl_compatibility",
        "--script",str(ROOT/"tests/godot/current_repeat_pixel_capture.gd"),
        "--",str(payload),str(folder),
    ],capture_output=True,text=True,timeout=110,
        env={**os.environ,"LIBGL_ALWAYS_SOFTWARE":"1"})
    (folder/"godot.log").write_text(run.stdout+run.stderr)
    assert run.returncode == 0, (run.stdout+run.stderr)[-6000:]

    witness = json.loads((folder/"repeat.json").read_text())
    assert not witness["errors"], witness
    assert witness["rest_duration"] > 0.0
    assert witness["replay_origin"] >= (
        witness["source_duration"] + witness["rest_duration"])
    first = Image.open(folder/"first.png").convert("RGB")
    pause = Image.open(folder/"rest.png").convert("RGB")
    replay = Image.open(folder/"replay.png").convert("RGB")
    assert first.size == pause.size == replay.size
    gap = witness["staff_gap"]
    x = round(first.width*PLAYHEAD_FRACTION)
    start, stop = max(0,round(x-15*gap)),max(0,round(x-gap))
    assert stop > start+gap, witness
    original_header = _score_ink(first)[:,start:stop]
    repeated_header = _score_ink(replay)[:,start:stop]
    header_ink = int(original_header.sum())
    similarity = _similarity(original_header,repeated_header)
    assert header_ink > 30, ("Original clef/key/meter header missing",header_ink)
    assert similarity >= .85, {
        "problem":"New repeat lacks the original source header",
        "pixels_original":header_ink,"header_similarity":similarity,
        "replay_pixels":int(repeated_header.sum()),
    }

    # The actual gap image must contain printed silence near the fixed
    # strike, rather than the noteheads of a silently rewound earlier copy.
    window = slice(max(0,round(x-2*gap)),min(first.width,round(x+2*gap)))
    rest_near_playhead = _score_ink(pause)[:,window]
    assert np.count_nonzero(rest_near_playhead) > 5, (
        "The replay boundary has no photographed full-measure rest")
    assert _similarity(_score_ink(first)[:,window],rest_near_playhead) < .75, (
        "Rest gap is indistinguishable from the initial source note at the playhead")

    # An independent corruption control must fail the SAME header predicate.
    changed = replay.copy()
    ImageDraw.Draw(changed).rectangle(
        (start,0,stop,changed.height-1),fill=changed.getpixel((0,0)))
    corrupted_header = _score_ink(changed)[:,start:stop]
    assert _similarity(original_header,corrupted_header) < .85
    (folder/"repeat-pixel-proof.json").write_text(json.dumps({
        "source":case.filename,
        "rest_duration":witness["rest_duration"],
        "source_duration":witness["source_duration"],
        "replay_origin":witness["replay_origin"],
        "header_original_pixels":header_ink,
        "header_replay_similarity":similarity,
        "rest_near_cursor_pixels":int(np.count_nonzero(rest_near_playhead)),
        "header_ablation_rejected":True
    },indent=2)+"\n")
