"""Guard the zero-network desktop transport and its native extension source.

The Python dispatcher is tested dynamically elsewhere. This inexpensive
test ensures the experimental native launch never silently re-introduces
a server/UDP bridge and the in-process bridge files stay wired together.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
SRC = ROOT / "native" / "src"


def test_native_launch_starts_one_godot_process_without_network_backend():
    launcher = (ROOT / "run-inprocess.sh").read_text()
    assert "python_teacher.server &" not in launcher
    assert "piano_teacher.server &" not in launcher
    assert "8765" not in launcher
    assert " --in-process" in launcher
    assert "exec " in launcher


def test_embedded_worker_queue_has_no_socket_or_server_dependencies():
    cpp = (SRC / "piano_native.cpp").read_text()
    header = (SRC / "piano_native.hpp").read_text()
    assert "std::condition_variable" in header
    assert "std::deque<Command>" in header
    assert "std::deque<Reply>" in header
    assert "Py_InitializeFromConfig" in cpp
    assert "PyGILState_Ensure" in cpp
    assert "ClassDB::register_class<PianoNative>" in cpp
    assert not any(word in cpp for word in ("socket(", "sendto(", "recvfrom(", "HTTPClient", "listen("))


def test_embedded_godot_request_contract_is_complete():
    main = (GODOT / "main.gd").read_text()
    asset = (GODOT / "score_asset_http.gd").read_text()
    demo = (GODOT / "demo_player.gd").read_text()
    request = (GODOT / "inprocess_request.gd").read_text()
    assert "use_inprocess" in main
    assert "InProcessBus.new()" in main
    assert "inprocess_bus.poll_midi(" in main
    assert "inprocess_bus" in asset and "inprocess_bus" in demo
    for name in ("request_completed", "func request(", "func cancel_request(",
                 "func complete(", "download_file"):
        assert name in request


def test_release_uses_a_bundled_runtime_and_drops_mcp_network_plugin():
    build = (ROOT / "scripts" / "package-inprocess.sh").read_text()
    assert "PIANO_BUNDLED_PYTHON_HOME" in build
    assert "PIANO_BUNDLED_NODE" in build
    assert "PIANO_GODOT_BINARY" in build
    assert "runtime/python" in build
    assert 'rm -rf "$STAGE/godot/addons/godot_mcp_toolkit"' in build
