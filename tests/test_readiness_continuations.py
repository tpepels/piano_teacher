"""In-app continuation scenario (R1 F1, owner-approved regression).

Runs the real application (main.tscn, embedded engine, real framebuffer)
through tests/readiness/run_sweep.sh on The Entertainer in the `fullrest`
mode: Play on an empty strip -> mixed take 1 with Pause/Resume -> failed
take's automatic repeat -> Retry during the repeat -> clean repeat -> Pause
and Resume in the rest -> automatic tempo-step repeat. A simulated pianist
plays every graded take through a virtual ALSA MIDI port.

For every graded take it asserts, from the harness's frames.jsonl, events
and captures (tests/readiness/invariants.py): the take's own source strip is
bound and visible at its first graded beat and arrives at the playhead at the
graded run_at (<= 2 px), noteheads cross at their graded beat (<= 2 px),
exactly one full-bar count-in at the take's own tempo is spoken right before
it, and repeated copies show feedback colour wherever a capture shows them.

The run uses a private Xvfb server when xvfb-run exists: an unfocused or
occluded desktop window is throttled by the compositor to ~1 frame/s, which
makes the first graded beat of a short take unobservable. Without Xvfb the
desktop display is used and a throttled run is skipped with the reason.
Missing prerequisites skip with the reason, except under CI_FULL=1
(scripts/ci-full.sh), where they fail. About two minutes.
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
SECONDS = 90  # the tempo-step repeat after the rest pause is graded at ~75 s
THROTTLED_FRAME_MS = 50.0
XVFB = shutil.which("xvfb-run")


def _unavailable(reason: str):
    if os.environ.get("CI_FULL") == "1":
        pytest.fail(f"release gate cannot run the in-app scenario: {reason}")
    pytest.skip(reason)


def _missing_prerequisite() -> str | None:
    if not XVFB and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return "needs xvfb-run or a display: the scenario renders the real framebuffer"
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
    reason = _missing_prerequisite()
    if reason:
        _unavailable(reason)
    out = tmp_path_factory.mktemp("readiness") / "entertainer_fullrest"
    command = ["bash", str(READINESS / "run_sweep.sh"), str(PIECE), str(out),
               str(SECONDS), "1600x900", "fullrest"]
    if XVFB:
        command = [XVFB, "-a", "-s", "-screen 0 1920x1200x24", *command]
    result = subprocess.run(command, capture_output=True, text=True,
                            timeout=SECONDS + 180)
    log = (out / "godot.log").read_text(errors="replace") if (out / "godot.log").exists() else ""
    assert (out / "events.json").exists(), result.stdout + result.stderr + log[-4000:]
    assert "SCRIPT ERROR" not in log and "Parse Error" not in log, log[-4000:]
    assert "midi_not_connected" not in log, "the virtual MIDI keyboard never connected"
    sys.path.insert(0, str(READINESS))
    from invariants import check_run
    checked = check_run(out)
    (out / "invariants.json").write_text(json.dumps(checked, indent=1))
    frames = [json.loads(line) for line in
              (out / "frames.jsonl").read_text().splitlines() if line.strip()]
    unfocused = sum(1 for row in frames if row.get("foc") is False)
    throttled = (checked["frame_median_ms"] or 0.0) > THROTTLED_FRAME_MS
    if not XVFB and (throttled or unfocused > 0.2 * len(frames)):
        _unavailable(f"desktop window throttled (median frame {checked['frame_median_ms']} ms, "
                     f"{unfocused}/{len(frames)} frames unfocused); install xvfb-run")
    assert not throttled, (
        f"frames ran at {checked['frame_median_ms']} ms median under Xvfb; "
        "the first graded beat of a take cannot be observed")
    return out, checked


def test_scenario_reaches_every_kind_of_take(continuation_run):
    out, checked = continuation_run
    events = json.loads((out / "events.json").read_text())["events"]
    pressed = [e["button"] for e in events if e.get("kind") == "press"]
    for button in ("Pause", "Resume", "Retry", "Pause(rest)", "Resume(rest)"):
        assert button in pressed, pressed
    graded = [t for t in checked["takes"] if t["reached_first_beat"]]
    # take 1, its automatic repeat, the retried take, a clean repeat and
    # the tempo-step repeat after the paused rest
    assert len(graded) >= 5, checked["takes"]
    bpms = [t["bpm"] for t in graded]
    assert max(bpms) > min(bpms), f"no automatic tempo-step repeat was graded: {bpms}"


def test_every_graded_take_has_its_bound_source_at_the_graded_beat(continuation_run):
    _, checked = continuation_run
    for take in checked["takes"]:
        if not take["reached_first_beat"]:
            continue
        assert take["bound"] and take["visible_heads"] > 0, take
        assert take["sync_px_max"] is not None and take["sync_px_max"] <= 2.0, take
        assert take["onsets_measured"], take
        assert take["onset_px_max"] is None or take["onset_px_max"] <= 2.0, take


def test_every_graded_take_has_one_count_in_bar_at_its_tempo_right_before_it(continuation_run):
    _, checked = continuation_run
    for take in checked["takes"]:
        if take["reached_first_beat"]:
            assert take["count_in_ok"], take


def test_repeated_copies_show_feedback_colour(continuation_run):
    _, checked = continuation_run
    shown = [t for t in checked["takes"] if t["tid"] >= 2 and t["reached_first_beat"]
             and t.get("captures_after_first_beat", 0) > 0]
    assert shown, checked["takes"]
    for take in shown:
        assert take["coloured_heads"] > 0, take
