"""Only embedded CPython and in-memory Godot queues are supported."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
SRC = ROOT / "native" / "src"


def test_single_launcher_starts_only_godot():
    launcher = (ROOT / "run.sh").read_text()
    assert "exec " in launcher and '--path godot' in launcher
    assert "8765" not in launcher
    assert " --in-process" not in launcher
    assert "python_teacher.server &" not in launcher
    assert "piano_teacher.server &" not in launcher
    assert not (ROOT / "run-inprocess.sh").exists()


def test_native_worker_queue_contains_no_network_api():
    cpp = (SRC / "piano_native.cpp").read_text()
    header = (SRC / "piano_native.hpp").read_text()
    for token in ("std::condition_variable", "std::deque<Command>", "std::deque<Reply>"):
        assert token in header
    for token in ("Py_InitializeFromConfig", "PyGILState_Ensure",
                  "RTLD_GLOBAL", "PYTHON_SHARED_OBJECT",
                  "ClassDB::register_class<PianoNative>"):
        assert token in cpp
    assert not any(token in cpp for token in (
        "socket(", "sendto(", "recvfrom(", "HTTPClient", "listen("))
    # Musical time advances on the one native worker even when Godot does
    # not request /state. No additional timer, service, or Python thread.
    assert "available_.wait_until" in cpp
    assert "tick_engine()" in cpp
    assert '"tick"' in cpp
    assert "std::chrono::steady_clock" in cpp
    assert "def tick(self)" in (ROOT/"piano_teacher/inprocess.py").read_text()


def test_only_one_godot_command_adapter_and_score_queue():
    main = (GODOT / "main.gd").read_text()
    queue = (GODOT / "score_asset_queue.gd").read_text()
    demo = (GODOT / "demo_player.gd").read_text()
    request = (GODOT / "inprocess_request.gd").read_text()
    assert "InProcessBus.new()" in main
    assert "inprocess_bus.poll_midi(" in main
    cpp = (SRC / "piano_native.cpp").read_text()
    bridge = (GODOT / "inprocess_bus.gd").read_text()
    assert '"/midi/live?since=%d"' in bridge
    assert 'native.call("live_events_json"' not in bridge
    assert "live_events_json" not in cpp
    assert 'res://score_asset_queue.gd' in main
    assert "use_inprocess" not in main
    for script in (main, queue, demo, request):
        assert "HTTPRequest" not in script
        assert "127.0.0.1" not in script
    assert not (GODOT / "score_asset_http.gd").exists()
    for name in ("request_completed", "func request(", "func cancel_request(",
                 "func complete(", "download_file"):
        assert name in request


def test_no_server_udp_or_dual_runtime_entrypoints():
    from importlib import import_module
    assert not (ROOT / "piano_teacher" / "transport" / "http.py").exists()
    assert not (ROOT / "piano_teacher" / "midi_visual_publisher.py").exists()
    module = import_module("piano_teacher.server")
    assert not hasattr(module, "Handler")
    assert not hasattr(module, "main")
    assert "piano_teacher.server:main" not in (ROOT / "pyproject.toml").read_text()


def test_release_bundles_python_node_and_godot():
    build = (ROOT / "scripts" / "package-inprocess.sh").read_text()
    for token in ("PIANO_BUNDLED_PYTHON_HOME", "PIANO_BUNDLED_NODE",
                  "PIANO_GODOT_BINARY", "runtime/python"):
        assert token in build
    assert 'rm -rf "$STAGE/godot/addons/godot_mcp_toolkit"' in build
