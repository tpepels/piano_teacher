"""A deleted Godot resource must not silently break desktop startup.

Python contracts and isolated clock tests do not load main.gd. This
inexpensive, source-only check catches missing static GDScript preloads
before a release; it does not replace Godot's actual --check-only parser.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / "godot"
PRELOAD = re.compile(r"""\bpreload\s*\(\s*["']res://([^"']+)["']\s*\)""")


def test_all_static_godot_preloads_resolve_inside_the_project():
    missing = []
    references = 0
    for script in ROOT.rglob("*.gd"):
        source = script.read_text(encoding="utf-8")
        for match in PRELOAD.finditer(source):
            references += 1
            resource = ROOT / match.group(1)
            if not resource.is_file():
                missing.append(f"{script.relative_to(ROOT)} -> res://{match.group(1)}")
    assert references > 40, "The preload guard found unexpectedly few resource references"
    assert not missing, "Broken GDScript preload(s):\n" + "\n".join(sorted(missing))


def test_application_entrypoint_uses_only_unified_presentation_clock():
    source = (ROOT / "main.gd").read_text(encoding="utf-8")
    assert 'preload("res://visual_transport_clock.gd")' in source
    assert "RetryCameraClock" not in source
    assert "retry_camera_clock" not in source
    assert "visual_transport_clock.score_beat(" in source
    assert "visual_transport_clock.visual_beat(" in source
    assert "visual_transport_clock.retry_preparing(" in source
    assert "visual_transport_clock.retry_count_in_beat(" in source
