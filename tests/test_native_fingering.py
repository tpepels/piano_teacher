"""Real Godot framebuffer proof for provider-neutral fingering and corrections."""
import json
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
from http.server import ThreadingHTTPServer
from threading import Event, Thread
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run_godot(command, *, timeout):
    """Keep a rendering regression from exhausting the developer/CI machine."""
    stopped = Event()
    exceeded = []
    with subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        def guard():
            while not stopped.wait(.1):
                try:
                    status = Path(f'/proc/{process.pid}/status').read_text()
                    rss = next(int(line.split()[1]) for line in status.splitlines() if line.startswith('VmRSS:'))
                except (FileNotFoundError, StopIteration):
                    continue
                if rss > 1536*1024:
                    exceeded.append(rss)
                    process.kill()
                    return
        watcher = Thread(target=guard, daemon=True)
        watcher.start()
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(command, timeout, stdout.encode(), stderr.encode())
        finally:
            stopped.set()
            watcher.join()
        assert not exceeded, f'Godot exceeded 1536 MiB RSS: {exceeded}; output: {stdout[-1500:]} {stderr[-1500:]}'
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _godot():
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return [binary]
    xvfb = shutil.which("xvfb-run")
    if xvfb:
        return [xvfb, "-a", "-s", "-screen 0 1920x1080x24", binary]
    pytest.skip("Actual framebuffer requires a desktop or xvfb-run")


def _fixture(folder):
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    from piano_teacher.score import import_piece
    from piano_teacher.fingering.service import FingeringService
    from piano_teacher.fingering.projection import project_model

    tree = ET.parse(ROOT / "tests/fixtures/native_pixel_pitch_probe.musicxml")
    rh = tree.find("part[@id='RH']")
    # A ledger chord, accidental, articulation, two-voice unison and tie.
    first = rh[0].find("note")
    first.find("pitch/step").text = "C"
    first.find("pitch/octave").text = "6"
    chord = ET.fromstring(ET.tostring(first))
    chord.insert(0, ET.Element("chord"))
    chord.find("pitch/step").text = "E"
    rh[0].insert(list(rh[0]).index(first) + 1, chord)
    second = rh[0].findall("note")[2]
    ET.SubElement(second.find("pitch"), "alter").text = "1"
    ET.SubElement(second, "accidental").text = "sharp"
    ET.SubElement(ET.SubElement(ET.SubElement(second, "notations"),
                               "articulations"), "staccato")
    # Two eighths provide a genuine extracted beam.
    second.find("duration").text = "2"
    second.find("type").text = "eighth"
    ET.SubElement(second, "beam", number="1").text = "begin"
    eighth = ET.fromstring(ET.tostring(second))
    eighth.find("pitch/step").text = "A"
    eighth.find("pitch").remove(eighth.find("pitch/alter"))
    eighth.remove(eighth.find("accidental"))
    eighth.remove(eighth.find("notations"))
    eighth.find("beam").text = "end"
    rh[0].insert(list(rh[0]).index(second) + 1, eighth)
    last = rh[0].findall("note")[-1]
    continuation = rh[1].find("note")
    for note, kind in ((last, "start"), (continuation, "stop")):
        note.find("pitch/step").text = "D"
        note.find("pitch/octave").text = "5"
        ET.SubElement(note, "tie", type=kind)
        ET.SubElement(ET.SubElement(note, "notations"), "tied", type=kind)
    # Keep a separate source identity for one physically shared key.
    ET.SubElement(ET.SubElement(rh[0], "backup"), "duration").text = "16"
    unison = ET.fromstring(ET.tostring(first))
    unison.find("voice").text = "2"
    rh[0].append(unison)
    rh[0].append(ET.fromstring("<note><rest/><duration>12</duration>"
                              "<voice>2</voice><type>half</type><dot/></note>"))
    source = folder / "fingering.musicxml"
    tree.write(source)
    piece, _ = import_piece(source)
    plan = FingeringService(folder / "fingering-cache").prepare(piece, sha256(source.read_bytes()).hexdigest())
    assert plan.summary()["assigned"] > 0, plan.summary()
    assert plan.provider, "Framebuffer evidence must use the installed production provider"
    data, _ = fixture(AuditCase("fingering", str(source), 1, 2, "both"), piece=piece)
    data["model"] = project_model(data["model"], plan)
    expected = {}
    shared = []
    for event in data["model"]["notation_events"]:
        if event["kind"] != "note":
            continue
        if event["is_attack"] and event.get("fingering"):
            expected[event["id"]] = dict(event["fingering"], beat=event["beat"])
        elif not event["is_attack"]:
            # Deliberately malformed projection: tied continuations still
            # must not acquire a second visible assignment.
            event["fingering"] = dict(finger=2, hand=event["staff"],
                                       source_id=event["source_id"], origin="automatic")
        if event["staff"] == "right" and event["beat"] == 0 and not event["chord"]:
            shared.append(event["id"])
    assert len(shared) == 2
    assert any(not e["is_attack"] and e["kind"] == "note"
               for e in data["model"]["notation_events"])
    data["expected"] = expected
    data["shared"] = shared
    data["unknown_id"] = next(i for i in expected if i not in shared)
    data["summary"] = plan.summary()
    data["expected_count"] = len({(e["beat"],e["staff"],e["midi_pitch"],e["fingering"]["finger"])
        for e in data["model"]["notation_events"] if e["id"] in expected})
    return data


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    command = _godot()
    folder = tmp_path_factory.mktemp("native-fingering")
    data = _fixture(folder)
    payload = folder / "fixture.json"
    payload.write_text(json.dumps(data))
    result = _run_godot([*command, "--path", str(ROOT / "godot"),
        "--audio-driver", "Dummy", "--rendering-method", "gl_compatibility",
        "--script", str(ROOT / "tests/godot/native_fingering.gd"),
        "--", str(payload), str(folder)], timeout=90)
    output = result.stdout + result.stderr
    (folder / "godot.log").write_text(output)
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    return folder, data, json.loads((folder / "report.json").read_text())


def _rgb(folder, filename):
    return np.asarray(Image.open(folder / filename).convert("RGB")).astype(int)


def _verify_numbers(folder, frame, expected_count):
    base = _rgb(folder, frame["base"])
    numbered = _rgb(folder, frame["file"])
    changed = np.max(np.abs(numbered - base), axis=2) > 12
    labels = frame["labels"]
    assert len(labels) == expected_count, "Every assigned attack needs visible fingering"
    claimed = np.zeros(changed.shape, dtype=bool)
    for label in labels:
        x, y, w, h = label["rect"]
        x0, y0, x1, y1 = int(x), int(y), int(np.ceil(x+w)), int(np.ceil(y+h))
        assert 30 <= x0 < x1 < base.shape[1] and 0 < y0 < y1 < base.shape[0]
        pixels = changed[y0:y1, x0:x1]
        assert pixels.sum() > 12, "Missing fingering ink in the actual framebuffer"
        # Independent reference text rendered by Godot, compared as masks.
        atlas = _rgb(folder, label["reference"])
        width = atlas.shape[1] // 5
        reference = atlas[:, (label["finger"]-1)*width:label["finger"]*width]
        reference_mask = reference.max(axis=2) > 100
        crop = numbered[y0:y1, x0:x1].max(axis=2) > 100
        assert crop.shape == reference_mask.shape
        scores = [(crop & (atlas[:,i*width:(i+1)*width].max(axis=2)>100)).sum() /
                  max(1,(crop | (atlas[:,i*width:(i+1)*width].max(axis=2)>100)).sum())
                  for i in range(5)]
        assert np.argmax(scores)+1 == label["finger"], (label,scores)
        assert scores[label["finger"]-1] > .80, (label,scores)
        assert scores[label["finger"]-1] - max(s for i,s in enumerate(scores) if i != label["finger"]-1) > .12
        # Full text cell plus a margin must clear all pale source notation.
        assert not (base[max(0,y0-2):y1+2, max(0,x0-2):x1+2].max(axis=2) > 145).any(), label
        head = label["head"]
        if label["hand"] == "right":
            assert y1 < head[1], "Right-hand fingers belong above their heads"
        else:
            assert y0 > head[1], "Left-hand fingers belong below their heads"
        claimed[y0:y1, x0:x1] = True
    assert not (changed & ~claimed).any(), "Unexpected extra ink (including tied continuations)"


def test_real_framebuffer_fingers_clear_source_ink_and_scroll_with_notes(captured):
    folder, data, report = captured
    count = data["expected_count"]
    for frame in report["frames"][:2]:
        _verify_numbers(folder, frame, count)
        for label in frame["labels"]:
            for identifier in label["event_ids"]:
                assert label["finger"] == data["expected"][identifier]["finger"]
    before, after = report["frames"][:2]
    a = {tuple(v["event_ids"]): v for v in before["labels"]}
    b = {tuple(v["event_ids"]): v for v in after["labels"]}
    assert a.keys() == b.keys()
    for key in a:
        assert b[key]["rect"][0] - a[key]["rect"][0] == pytest.approx(-report["density"]*.25, abs=.01)
        assert b[key]["head"][0] - a[key]["head"][0] == pytest.approx(-report["density"]*.25, abs=.01)
        assert b[key]["rect"][1] == a[key]["rect"][1]
    assert report["malformed_matches_base"], "Invalid/unknown fingers must never invent digits"


def test_popup_keeps_canonical_identities_and_corrected_pixels(captured):
    folder, data, report = captured
    assert report["editor_checks"] == [], report["editor_checks"]
    assert report["requests"] == [
        {"source_id": data["expected"][data["shared"][0]]["source_id"], "finger": 5},
        {"source_id": data["expected"][data["shared"][1]]["source_id"], "finger": None},
        {"source_id": data["expected"][data["unknown_id"]]["source_id"], "finger": 3},
    ]
    corrected = report["frames"][2]
    _verify_numbers(folder, corrected, report["corrected_count"])
    label = next(v for v in corrected["labels"] if data["shared"][0] in v["event_ids"])
    assert label["finger"] == 5


def test_compact_practice_canvas_keeps_chord_fingers_visible(captured):
    folder, data, report = captured
    _verify_numbers(folder,report["frames"][3],data["expected_count"])


def test_pixel_oracle_rejects_erased_wrong_and_colliding_fingering(captured):
    folder, data, report = captured
    frame = report["frames"][0]
    assert frame["labels"], "Positive control must actually contain finger numbers"
    original = _rgb(folder, frame["file"]).astype("uint8")
    label = frame["labels"][0]
    x, y, w, h = label["rect"]
    x0, y0, x1, y1 = int(x), int(y), int(np.ceil(x+w)), int(np.ceil(y+h))
    erased = original.copy()
    erased[y0:y1, x0:x1] = _rgb(folder, frame["base"])[y0:y1, x0:x1]
    Image.fromarray(erased).save(folder / "erased.png")
    with pytest.raises(AssertionError):
        _verify_numbers(folder, dict(frame, file="erased.png"), data["expected_count"])
    wrong = dict(frame, labels=[dict(v) for v in frame["labels"]])
    wrong["labels"][0]["finger"] = label["finger"] % 5 + 1
    with pytest.raises(AssertionError):
        _verify_numbers(folder, wrong, data["expected_count"])
    collision = dict(frame, labels=[dict(v) for v in frame["labels"]])
    collision["labels"][0]["rect"] = [label["head"][0]-w/2, label["head"][1]-h/2, w, h]
    with pytest.raises(AssertionError):
        _verify_numbers(folder, collision, data["expected_count"])


@pytest.mark.parametrize("source", ["xml", "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi",
    "Le_Pianiste_virtuose_-_Première_partie_(1-20)_-_C_L_Hanon.midi"],ids=["xml","chopin-midi","hanon-midi"])
def test_real_application_popup_posts_correction_and_reloads_revision(captured, source):
    from piano_teacher.server import PracticeEngine
    from piano_teacher.transport.http import Handler

    fixture_folder, _, _ = captured
    name = "xml" if source == "xml" else "chopin" if source.startswith("Chopin") else "hanon"
    folder = fixture_folder / ("application-"+name)
    folder.mkdir()
    source_path = fixture_folder / "fingering.musicxml" if source == "xml" else ROOT / "midi" / source
    engine = PracticeEngine(folder / "application-cache", enable_midi=False)
    engine.load(str(source_path))
    handler = type("FingeringHandler", (Handler,), {"engine":engine})
    try:
        server = ThreadingHTTPServer(("127.0.0.1",8765),handler)
    except OSError:
        engine.db.close()
        pytest.skip("Production loopback port is already in use")
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        try:
            result = _run_godot([*_godot(), "--path", str(ROOT / "godot"),
                "--audio-driver", "Dummy", "--rendering-method", "gl_compatibility",
                "--script", str(ROOT / "tests/godot/native_fingering_application.gd"),
                "--", str(folder)], timeout=100)
        except subprocess.TimeoutExpired as exc:
            (folder / "application.log").write_bytes((exc.stdout or b"")+(exc.stderr or b""))
            raise
        output = result.stdout+result.stderr
        (folder / "application.log").write_text(output)
        assert result.returncode == 0, output
        assert "NATIVE_FINGERING_APPLICATION_FAILURES:0" in output, output
        assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
        report = json.loads((folder / "app-report.json").read_text())
        assert report['path_steps']==len(engine.plan.lesson_steps)
        assert report['static_memory'] < 512*1024*1024, "Long lesson paths must share font resources"
        assert report["before"] != report["changed"]
        assignments = engine.fingering_status()["assignments"]
        assert report["source_id"] in assignments
        assert assignments[report["source_id"]]["manual"] is None
        assert np.any(_rgb(folder,"app-before.png") != _rgb(folder,"app-corrected.png"))
        x,y,w,h = report["finger_rect"]
        x0,y0,x1,y1 = int(x),int(y),int(np.ceil(x+w)),int(np.ceil(y+h))
        before = _rgb(folder,"app-before.png")[y0:y1,x0:x1]
        after = _rgb(folder,"app-corrected.png")[y0:y1,x0:x1]
        assert np.count_nonzero(np.max(np.abs(before-after),axis=2)>20) >= 5, "The actual MIDI finger digit must change in the framebuffer"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        engine.db.close()
