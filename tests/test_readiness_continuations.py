"""In-app continuation scenario (R1 F1, owner-approved regression).

Runs the real application (main.tscn, embedded engine, real framebuffer)
through tests/readiness/run_sweep.sh on The Entertainer: Play on an empty
strip -> mixed take 1 with Pause/Resume -> failed take's automatic repeat ->
Retry during the repeat -> clean continuations with automatic tempo steps.
A simulated pianist plays every graded take through a virtual ALSA MIDI port.

For every graded take it asserts, from the harness's frames.jsonl, events
and captures (tests/readiness/invariants.py): the take's own source strip is
bound and visible at its first graded beat and arrives at the playhead at the
graded run_at (<= 2 px), noteheads cross at their graded beat (<= 2 px),
exactly one full-bar count-in is spoken right before it, and repeated copies
show feedback colour. Needs a display, Godot and the ALSA sequencer; it is
skipped with the reason otherwise. About two and a half minutes.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READINESS = ROOT / "tests" / "readiness"
PIECE = ROOT / "midi" / "The_Entertainer_-_Scott_Joplin.midi"
SECONDS = 80  # take 4 (first tempo-step repeat) is graded at about 63 s


def _skip_reason() -> str | None:
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return "needs a display: the scenario renders the real framebuffer"
    if not (shutil.which("godot") or shutil.which("godot4")):
        return "Godot is not installed"
    if not Path("/dev/snd/seq").exists():
        return "needs the ALSA sequencer for the virtual MIDI keyboard"
    try:
        import rtmidi  # noqa: F401
    except ImportError:
        return "python-rtmidi is not installed"
    return None


@pytest.fixture(scope="module")
def continuation_run(tmp_path_factory):
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    out = tmp_path_factory.mktemp("readiness") / "entertainer_full"
    result = subprocess.run(
        ["bash", str(READINESS / "run_sweep.sh"), str(PIECE), str(out),
         str(SECONDS), "1600x900", "full"],
        capture_output=True, text=True, timeout=SECONDS + 150)
    log = (out / "godot.log").read_text(errors="replace") if (out / "godot.log").exists() else ""
    assert (out / "events.json").exists(), result.stdout + result.stderr + log[-4000:]
    assert "SCRIPT ERROR" not in log and "Parse Error" not in log, log[-4000:]
    frames = [json.loads(line) for line in
              (out / "frames.jsonl").read_text().splitlines() if line.strip()]
    unfocused = sum(1 for row in frames if row.get("foc") is False)
    if frames and unfocused > 0.2 * len(frames):
        # An unfocused window is throttled to ~1 frame/s by the compositor:
        # the presentation clock then cannot be sampled at frame accuracy.
        pytest.skip(f"window unfocused for {unfocused}/{len(frames)} frames "
                    "(compositor throttling); timing evidence is invalid")
    sys.path.insert(0, str(READINESS))
    from invariants import check_run
    checked = check_run(out)
    (out / "invariants.json").write_text(json.dumps(checked, indent=1))
    return out, checked


def test_scenario_reaches_repeat_retry_and_continuations(continuation_run):
    out, checked = continuation_run
    events = json.loads((out / "events.json").read_text())["events"]
    pressed = [e["button"] for e in events if e.get("kind") == "press"]
    assert "Pause" in pressed and "Resume" in pressed and "Retry" in pressed, pressed
    graded = [t for t in checked["takes"] if t["reached_first_beat"]]
    # take 1, its automatic repeat, the retried take, >= 1 clean continuation
    assert len(graded) >= 4, checked["takes"]
    bpms = [t["bpm"] for t in graded]
    assert max(bpms) > min(bpms), f"no automatic tempo-step repeat was graded: {bpms}"


def test_every_graded_take_has_its_bound_source_at_the_graded_beat(continuation_run):
    _, checked = continuation_run
    for take in checked["takes"]:
        if not take["reached_first_beat"]:
            continue
        assert take["bound"] and take["visible_heads"] > 0, take
        assert take["sync_px_max"] is not None and take["sync_px_max"] <= 2.0, take
        assert take["onset_px_max"] is None or take["onset_px_max"] <= 2.0, take


def test_every_graded_take_has_one_count_in_bar_right_before_it(continuation_run):
    _, checked = continuation_run
    for take in checked["takes"]:
        if take["reached_first_beat"]:
            assert take["count_in_ok"], take


def test_repeated_copies_show_feedback_colour(continuation_run):
    _, checked = continuation_run
    repeats = [t for t in checked["takes"] if t["tid"] >= 2 and t["reached_first_beat"]]
    # Captures land at fixed beats; a take interrupted by Retry may have no
    # capture after its first graded note, so require colour on most copies.
    coloured = [t["tid"] for t in repeats if t["coloured_heads"] > 0]
    assert repeats and len(coloured) >= max(2, len(repeats) - 1), repeats
