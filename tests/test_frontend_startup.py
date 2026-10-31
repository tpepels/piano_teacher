from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_decodes_invalid_engine_responses_without_json_parser_noise():
    main = (ROOT / "godot" / "main.gd").read_text(encoding="utf-8")
    assert "func _decode_json(body: PackedByteArray)" in main
    assert "if body.is_empty():" in main
    assert "document.parse(body.get_string_from_utf8()) != OK" in main
    assert "func _command_failure(code: int, body: PackedByteArray)" in main
    assert "HTTPRequest" not in main


def test_single_launcher_requires_embedded_engine_preflight():
    script = (ROOT / "run.sh").read_text()
    assert 'export PYTHONPATH=' in script
    assert "scripts/verify-native-bridge.sh" in script
    assert "piano-native-verified" in script
    assert 'exec "$GODOT"' in script
    assert "8765" not in script
