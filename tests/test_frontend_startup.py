from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_handles_empty_and_invalid_http_responses_without_logging_json_errors():
    script = (ROOT / 'godot' / 'main.gd').read_text(encoding='utf-8')
    assert 'func _decode_json(body: PackedByteArray)' in script
    assert 'if body.is_empty():' in script
    assert 'document.parse(body.get_string_from_utf8()) != OK' in script
    assert 'func _http_failure(code: int, body: PackedByteArray)' in script
    assert 'if code == 0:' in script
    assert not any('JSON.parse_string(' in line for line in script.splitlines()
                   if not line.strip().startswith('#'))


def test_linux_launcher_checks_backend_before_starting_godot():
    script = (ROOT / 'run.sh').read_text(encoding='utf-8')
    assert 'export PYTHONPATH=' in script
    assert 'import piano_teacher.server' in script
    assert 'BACKEND_READY=1' in script
    assert 'if [[ "$BACKEND_READY" -ne 1 ]]' in script
