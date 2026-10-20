#!/usr/bin/env python3
"""Review the actual native application at full desktop and compact resolution.

rtk proxy env PIANO_TEACHER_NATIVE_NOTATION=1 .venv/bin/python \
    scripts/review_art_direction.py --render --output /tmp/piano-art-direction

Owns a temporary HTTP server on 127.0.0.1:8765; refuses an occupied port. Without
--render it still checks real MIDI/native rendering headlessly. --geometry-only
uses production controls with supplied state, no server, and no screenshots.
PNG files are raw viewport captures, never resized or composed mock scenes.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
    require(report.get("native_environment") == "1", "Native environment was not asserted")
    require(report.get("viewport") == list(size), "Actual viewport differs from requested pixels")
    require(report.get("render") is render, "Unexpected screenshot mode")
    check_window_geometry(report.get("window_geometry", {}), "window")
    require(not report.get("failures", ["Missing failure evidence"]),
            "Composition failures: " + json.dumps(report.get("failures")))
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
        require(native.get("enabled") is True, f"{name}: application native flag is off")
        require(native.get("checked") is require_native, f"{name}: unexpected native evidence mode")
        if require_native:
            require(native.get("native_ready") is True and native.get("visible") is True,
                    f"{name}: native notation is not ready and visible")
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


def api(route: str, deadline: float, data: dict | None = None, *, timeout: float = 90) -> dict:
    request = Request("http://127.0.0.1:8765" + route,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=min(timeout, remaining(deadline))) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"{route}: HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    if not isinstance(result, dict) or "error" in result:
        raise RuntimeError(f"{route}: {result}")
    return result


def check_free_port() -> None:
    with socket.socket() as sock:
        # Match HTTPServer's reuse policy: recently closed test connections
        # may be in TIME_WAIT even when no other application is listening.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", 8765))
        except OSError as exc:
            raise RuntimeError("Port 8765 is occupied; this review must own its isolated backend") from exc


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
    validate_report(report, size, output=output, require_native=config["mode"] == "http",
                    render=config["render"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", "--output-dir", type=Path, default=Path("/tmp/piano-art-direction"))
    parser.add_argument("--render", action="store_true", help="Visible Godot windows and raw full-resolution PNGs")
    parser.add_argument("--geometry-only", action="store_true", help="Supplied state, no HTTP or native ink claim")
    parser.add_argument("--file", type=Path, default=ROOT / "midi/Ala_–_Joep_Beving.midi")
    parser.add_argument("--measure", type=int, default=9)
    parser.add_argument("--sizes", type=resolution, nargs="+", default=list(DEFAULT_SIZES),
                        help="Default: 1920x1080 800x600; optionally add 1280x800")
    parser.add_argument("--timeout", type=float, default=240, help="Total wall time budget in seconds (default 240)")
    args = parser.parse_args(argv)
    if os.environ.get("PIANO_TEACHER_NATIVE_NOTATION") != "1":
        parser.error("Set PIANO_TEACHER_NATIVE_NOTATION=1 explicitly")
    if not math.isfinite(args.timeout) or args.timeout < 10 or args.measure < 1:
        parser.error("--timeout must be finite and >=10; --measure must be positive")
    if args.render and args.geometry_only:
        parser.error("--render requires the real HTTP application")
    if len(args.sizes) > 3 or len(set(args.sizes)) != len(args.sizes):
        parser.error("Choose at most three distinct resolutions")
    godot = shutil.which("godot") or shutil.which("godot4")
    if godot is None:
        parser.error("Godot 4 is required")
    if not args.geometry_only and not args.file.is_file():
        parser.error(f"MIDI file not found: {args.file}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
           "XDG_DATA_HOME": str(output / "data"), "XDG_CONFIG_HOME": str(output / "config"),
           "XDG_CACHE_HOME": str(output / "cache"),
           "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    deadline = time.monotonic() + args.timeout
    summary = {"status": "running", "mode": "geometry" if args.geometry_only else "http",
               "native_environment": "1", "file": str(args.file.resolve()), "measure": args.measure,
               "render": args.render, "runs": []}
    backend = None
    backend_log = None
    try:
        if not args.geometry_only:
            check_free_port()
            music_dir = output / "music"
            music_dir.mkdir(exist_ok=True)
            fixture = music_dir / args.file.name
            if fixture.resolve() != args.file.resolve():
                shutil.copy2(args.file, fixture)
            backend_log = (output / "backend.log").open("w", encoding="utf-8")
            backend = subprocess.Popen([sys.executable, "-m", "piano_teacher.server", "--no-midi"],
                                       cwd=ROOT, env=env, stdout=backend_log, stderr=subprocess.STDOUT)
            startup_deadline = min(deadline, time.monotonic() + 15)
            while True:
                if backend.poll() is not None or time.monotonic() >= startup_deadline:
                    raise RuntimeError("Backend did not become ready; see backend.log")
                try:
                    api("/state", startup_deadline, timeout=1)
                    break
                except (OSError, URLError):
                    time.sleep(min(.1, remaining(startup_deadline)))
            api("/settings", deadline, {"fullscreen": False, "music_dir": str(music_dir)})
            api("/load", deadline, {"path": str(fixture)})
            api("/control", deadline, {"action": "tempo", "bpm": 120})
        for size in args.sizes:
            config = {"mode": summary["mode"], "size": list(size), "render": args.render,
                      "output": str(output / f"{size[0]}x{size[1]}")}
            if backend is not None:
                if backend.poll() is not None:
                    raise RuntimeError("Backend exited; see backend.log")
                api("/control", deadline, {"action": "stop"})
                state = api("/control", deadline, {"action": "open_at", "bar": args.measure, "mode": "practice"})
                model = api("/score/model", deadline)
                source = next((measure for measure in model.get("measures", [])
                               if measure.get("number") == args.measure), None)
                if source is None or state.get("selected_start_bar") != args.measure:
                    raise RuntimeError("Server did not select the requested source measure")
                if abs(float(state["play_from_beat"]) - float(source["start_beat"])) > 1e-7:
                    raise RuntimeError("Server playback origin differs from the semantic source measure")
                if state.get("revision") != model.get("revision"):
                    raise RuntimeError("Server state/model revisions differ before launch")
                config.update(measure=args.measure, play_from_beat=source["start_beat"], revision=state["revision"])
            report = run_capture(godot, size, config, env, deadline)
            summary["runs"].append(report)
        summary["status"] = "passed"
        print(f"ART_DIRECTION_PASS: {len(summary['runs']) * 6} views; {output / 'report.json'}")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        summary.update(status="failed", error=str(exc))
        print(f"ART_DIRECTION_FAIL: {exc}\nEvidence: {output}", file=sys.stderr)
        return 1
    finally:
        if backend is not None:
            backend.terminate()
            try:
                backend.wait(timeout=3)
            except subprocess.TimeoutExpired:
                backend.kill()
                backend.wait(timeout=3)
        if backend_log is not None:
            backend_log.close()
        (output / "report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
