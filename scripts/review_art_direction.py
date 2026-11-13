#!/usr/bin/env python3
"""Review the actual native application at full desktop and compact resolution.

rtk proxy .venv/bin/python \
    scripts/review_art_direction.py --render --output /tmp/piano-art-direction

Uses the production embedded engine. Without --render it checks real MIDI/native
rendering headlessly. --geometry-only uses supplied state and no screenshots.
PNG files are raw viewport captures, never resized or composed mock scenes.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIZES = ((1920, 1080), (800, 600))
CAPTURES = ("practice_ready", "practice_playing", "practice_paused",
            "library", "lesson_path", "settings")
ERROR_TOKENS = ("SCRIPT ERROR", "Parse Error", "ERROR:",
                "Native notation fallback:", "Native Verovio glyph fallback:")


def resolution(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use WIDTHxHEIGHT, for example 1920x1080") from exc
    if not (800 <= width <= 3840 and 600 <= height <= 2160):
        raise argparse.ArgumentTypeError("Resolution must be within 800x600 and 3840x2160")
    return width, height


def embedded_python_env() -> dict[str, str]:
    """Environment for the GDExtension's embedded CPython.

    It must see this checkout and the same interpreter and packages that run
    the Python side (see scripts/verify-native-bridge.sh).
    """
    import sysconfig
    paths = os.pathsep.join(filter(None, (
        str(ROOT), sysconfig.get_paths()["purelib"], os.environ.get("PYTHONPATH", ""))))
    env = {"PIANO_TEACHER_PYTHON_HOME": sys.base_prefix, "PYTHONPATH": paths}
    libdir = sysconfig.get_config_var("LIBDIR")
    if libdir:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, (
            libdir, os.environ.get("LD_LIBRARY_PATH", ""))))
    return env


def godot_command(godot: str, config: Path, size: tuple[int, int], *, render: bool) -> list[str]:
    return [godot, *([] if render else ["--headless"]),
            "--resolution", f"{size[0]}x{size[1]}", "--audio-driver", "Dummy",
            "--path", str(ROOT / "godot"), "--script",
            str(ROOT / "tests/godot/art_direction.gd"), "--", str(config)]


def validate_report(report: dict, size: tuple[int, int], *, output: Path,
                    require_native: bool, render: bool) -> None:
    """Fail closed on missing captures, native fallback, or reduced-size PNGs."""
    def require(condition: bool, detail: str) -> None:
        if not condition:
            raise RuntimeError(detail)

    def check_window_geometry(metrics: dict, name: str) -> None:
        expected_scale = max(1.0, min(size[0] / 1280, size[1] / 800))
        physical = metrics.get("physical_viewport", {})
        require(all(abs(physical.get(key, math.inf) - expected) <= 2 for key, expected in (
            ("x", 0), ("y", 0), ("width", size[0]), ("height", size[1]))),
            f"{name}: physical viewport does not match requested dimensions")
        scales = metrics.get("physical_scale", [])
        require(len(scales) == 2 and all(abs(scale - expected_scale) < .001 for scale in scales)
                and abs(metrics.get("content_scale", math.inf) - expected_scale) < .001,
                f"{name}: application scale differs from requested physical viewport")
        require(metrics.get("native_mode_checked") is (report.get("display_server") != "headless"),
                f"{name}: native window mode must only gate visible display servers")

    require(report.get("schema_version") == 1, "Missing composition report schema")
    require(report.get("viewport") == list(size), "Actual viewport differs from requested pixels")
    require(report.get("render") is render, "Unexpected screenshot mode")
    check_window_geometry(report.get("window_geometry", {}), "window")
    require(not report.get("failures", ["Missing failure evidence"]),
            "Composition failures: " + json.dumps(report.get("failures")))
    if report.get("exercise_controls"):
        require(type(report.get("native_input")) is bool, "Missing Practice input provenance")
        if report["native_input"]:
            require(render and report.get("display_server") == "X11", "Native popup input needs rendered X11 evidence")
        require(report.get("workflow_checks") == [
            "manual_minus_five", "manual_plus_five", "next_step", "previous_step",
            "picker_backwards", "right", "left", "both", "count_in", "pause",
            "paused_minus_five", "retry", "listen", "return_to_practice", "keyboard_play_pause",
        ], "Missing or incomplete real Practice control journey")
        workflows = report.get("workflow_captures", [])
        require([row.get("name") for row in workflows] == [
            "manual_minus_five", "right", "left", "both", "count_in", "listen", "keyboard_paused",
        ], "Missing Practice workflow capture evidence")
        for row in workflows:
            name = row["name"]
            require(row.get("revision", -1) >= 0 and row.get("bpm", 0) > 0 and row.get("step", 0) > 0,
                    f"{name}: missing workflow state")
            if name in ("right", "left", "both"):
                require(row.get("hand") == name and row.get("phase") == "ready", f"{name}: wrong hand evidence")
            if name == "listen":
                require(row.get("audio_playing") is True and row.get("pcm_bytes", 0) > 10000,
                        "Listen: missing actual PCM playback evidence")
            if render:
                require(row.get("screenshot") == f"workflow_{name}.png", f"{name}: missing workflow PNG")
                with (output / row["screenshot"]).open("rb") as file:
                    header = file.read(24)
                require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR" and
                        struct.unpack(">II", header[16:24]) == size, f"{name}: invalid or reduced workflow PNG")
            else:
                require(row.get("screenshot") is None, f"{name}: unexpected workflow PNG")
    samples = report.get("captures", [])
    require([sample.get("name") for sample in samples] == list(CAPTURES),
            "Expected exactly six ordered application captures")
    for sample in samples:
        name = sample["name"]
        expected_screen = "practice" if name.startswith("practice_") else (
            "lesson" if name == "lesson_path" else name)
        expected_phase = name.removeprefix("practice_") if expected_screen == "practice" else "paused"
        require(sample.get("screen") == expected_screen, f"{name}: wrong application screen")
        require(sample.get("phase") == expected_phase, f"{name}: wrong transport phase")
        require(bool(sample.get("controls")), f"{name}: no visible control geometry")
        check_window_geometry(sample.get("window_geometry", {}), name)
        captions = sample.get("captions", [])
        require(bool(captions), f"{name}: no visible caption measurements")
        for caption in captions:
            if caption.get("allows_truncation"):
                continue
            require(caption.get("content_width", -math.inf) + 2 >= caption.get("longest_word_width", math.inf),
                    f"{name}: caption is narrower than its longest word: {caption.get('text')}")
            if caption.get("wraps") and not caption.get("explicit_line_breaks"):
                require(caption.get("line_count", math.inf) <= caption.get("word_count", 0),
                        f"{name}: caption wraps individual characters: {caption.get('text')}")
        if name == "settings":
            rows = sample.get("settings_rows", {})
            require(set(rows) == {"target_tempo", "piano_volume"}, "Missing settings row measurements")
            for key, row in rows.items():
                caption = row.get("caption", {})
                require(caption.get("line_count") == 1 and
                        caption.get("content_width", -math.inf) + 2 >= caption.get("text_width", math.inf),
                        f"Settings {key}: caption must fit on one line")
                limit = row.get("height_limit", 0)
                heights = [rect.get("height", math.inf) for rect in (
                    row.get("row", {}), row.get("control", {}), caption.get("rect", {}))]
                require(math.isfinite(limit) and limit > 0 and all(0 < height <= limit + 2 for height in heights),
                        f"Settings {key}: row and control height must be bounded by text + padding")
        rects = sample.get("rects", {})
        for key in ("application", "score_stage", "score_frame", "transport", "primary_transport", "navigation"):
            rect = rects.get(key, {})
            require(all(isinstance(rect.get(field), (float, int)) and math.isfinite(rect[field])
                        for field in ("x", "y", "width", "height")), f"{name}: missing physical {key} rect")
            require(rect["width"] > 0 and rect["height"] > 0, f"{name}: empty {key} rect")
        if name == "practice_ready" and size[0] >= 1280 and size[1] >= 800:
            require(sample.get("score_height_ratio", 0) > .60, "Desktop score stage must dominate height (>60%)")
        native = sample.get("native", {})
        require(native.get("renderer_script") == "res://notation/native/view.gd",
                f"{name}: application renderer is not the native view")
        require(native.get("checked") is require_native, f"{name}: unexpected native evidence mode")
        if require_native:
            require(native.get("score_ready") is True and native.get("native_ready") is True
                    and native.get("visible") is True,
                    f"{name}: native notation is not ready and visible")
            require(native.get("retained_source_heads", 0) > 0,
                    f"{name}: no authentic retained source heads compiled")
            if name == "practice_playing":
                require(native.get("drawn_noteheads", 0) > 0 and native.get("visible_noteheads", 0) > 0,
                        f"{name}: no native noteheads drawn within the stage")
            require(not native.get("failure_reason"), f"{name}: native fallback")
            revision = native.get("revision", -1)
            require(revision >= 0 and all(native.get(key) == revision for key in (
                "state_revision", "layout_revision", "rendered_revision", "model_revision")),
                f"{name}: stale native assets/model/state")
            require(not native.get("action_pending") and not native.get("pending_action"),
                    f"{name}: transport action still pending")
        if render:
            require(sample.get("image_size") == list(size), f"{name}: actual capture dimensions differ")
            require(sample.get("screenshot") == name + ".png", f"{name}: screenshot is missing")
            path = output / sample["screenshot"]
            with path.open("rb") as file:
                header = file.read(24)
            require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR",
                    f"{name}: invalid PNG")
            require(struct.unpack(">II", header[16:24]) == size, f"{name}: PNG was not captured at full resolution")
        else:
            require(sample.get("screenshot") is None, f"{name}: unexpected screenshot")


def remaining(deadline: float) -> float:
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise RuntimeError("Art direction review exceeded its total time budget")
    return seconds


def run_capture(godot: str, size: tuple[int, int], config: dict, env: dict,
                deadline: float) -> dict:
    output = Path(config["output"])
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "art-direction.json"
    report_path.unlink(missing_ok=True)
    config_path = output / "config.json"
    # Leave time for subprocess termination and report/log collection.
    config["timeout_seconds"] = max(.1, min(100, remaining(deadline) - 3))
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    command = godot_command(godot, config_path, size, render=config["render"])
    with (output / "godot.log").open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                    stderr=subprocess.STDOUT,
                                    timeout=min(105, remaining(deadline)))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Godot exceeded its bound; see {output / 'godot.log'}") from exc
    transcript = (output / "godot.log").read_text(encoding="utf-8", errors="replace")
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    if result.returncode or any(token in transcript for token in ERROR_TOKENS):
        raise RuntimeError(f"Godot failed for {size[0]}x{size[1]}; see {output / 'godot.log'}; "
                           f"composition failures: {report.get('failures', 'no report')}")
    if report.get("exercise_controls", False) is not bool(config.get("exercise_controls", False)):
        raise RuntimeError("Godot did not run the requested Practice control journey")
    if report.get("native_input", False) is not bool(config.get("native_input", False)):
        raise RuntimeError("Godot did not run the requested native popup input")
    validate_report(report, size, output=output, require_native=config["mode"] == "embedded",
                    render=config["render"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", "--output-dir", type=Path, default=Path("/tmp/piano-art-direction"))
    parser.add_argument("--render", action="store_true", help="Visible Godot windows and raw full-resolution PNGs")
    parser.add_argument("--geometry-only", action="store_true", help="Supplied state, no engine commands or native ink claim")
    parser.add_argument("--exercise-controls", action="store_true", help="Exercise real Practice controls after the six views")
    parser.add_argument("--native-input", action="store_true", help="Use real X11 mouse/keyboard for the native lesson popup (xdotool)")
    parser.add_argument("--file", type=Path, default=ROOT / "midi/Ala_–_Joep_Beving.midi")
    parser.add_argument("--measure", type=int, default=9)
    parser.add_argument("--sizes", type=resolution, nargs="+", default=list(DEFAULT_SIZES),
                        help="Default: 1920x1080 800x600; optionally add 1280x800")
    parser.add_argument("--timeout", type=float, default=240, help="Total wall time budget in seconds (default 240)")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout < 10 or args.measure < 1:
        parser.error("--timeout must be finite and >=10; --measure must be positive")
    if args.render and args.geometry_only:
        parser.error("--render requires the real embedded application")
    if args.exercise_controls and args.geometry_only:
        parser.error("--exercise-controls requires the real embedded application")
    if args.native_input and (not args.exercise_controls or not args.render or not shutil.which("xdotool")):
        parser.error("--native-input requires --render --exercise-controls and xdotool")
    if len(args.sizes) > 3 or len(set(args.sizes)) != len(args.sizes):
        parser.error("Choose at most three distinct resolutions")
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        parser.error("Godot 4 is required")
    if not args.geometry_only and not args.file.is_file():
        parser.error(f"MIDI file not found: {args.file}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ,
           "HOME": str(output / "home"), "XDG_DATA_HOME": str(output / "data"), "XDG_CONFIG_HOME": str(output / "config"),
           "XDG_CACHE_HOME": str(output / "cache"), **embedded_python_env()}
    deadline = time.monotonic() + args.timeout
    summary = {"status": "running", "mode": "geometry" if args.geometry_only else "embedded",
               "file": str(args.file.resolve()), "measure": args.measure,
               "render": args.render, "runs": []}
    try:
        music_dir = output / "music"
        music_dir.mkdir(exist_ok=True)
        fixture = music_dir / args.file.name
        if not args.geometry_only and fixture.resolve() != args.file.resolve():
            shutil.copy2(args.file, fixture)
        for size in args.sizes:
            config = {"mode": summary["mode"], "size": list(size), "render": args.render,
                      "exercise_controls": args.exercise_controls,
                      "native_input": args.native_input,
                      "output": str(output / f"{size[0]}x{size[1]}")}
            if not args.geometry_only:
                config.update(file=fixture.name, music_dir=str(music_dir), measure=args.measure)
            # Each real application starts with its own preferences/progress.
            # A second resolution must not inherit the prior journey's resume
            # prompt and bypass the current source-measure picker.
            run_root = Path(config["output"])
            run_env = {**env, "HOME":str(run_root/"home"),
                       "XDG_DATA_HOME":str(run_root/"data"),
                       "XDG_CONFIG_HOME":str(run_root/"config"),
                       "XDG_CACHE_HOME":str(run_root/"cache")}
            report = run_capture(godot, size, config, run_env, deadline)
            summary["runs"].append(report)
        summary["status"] = "passed"
        print(f"ART_DIRECTION_PASS: {len(summary['runs']) * 6} views; {output / 'report.json'}")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        summary.update(status="failed", error=str(exc))
        print(f"ART_DIRECTION_FAIL: {exc}\nEvidence: {output}", file=sys.stderr)
        return 1
    finally:
        (output / "report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
