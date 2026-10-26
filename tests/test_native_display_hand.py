"""Native selection/editor policy keeps performing hand separate from staff.

One lightweight headless Godot serves the checks. A developer may reuse an
external session for a RED/GREEN cycle without starting a second Godot.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''extends SceneTree

func _initialize() -> void:
    call_deferred("_run")

func _checks(request: Dictionary) -> Array:
    # Reload the real source each request, allowing one-process RED/GREEN.
    var script := GDScript.new()
    script.source_code = FileAccess.get_file_as_string("res://notation/native/view.gd")
    if script.reload()!=OK:
        return ["Native source does not compile"]
    var renderer = script.new()
    renderer.size = Vector2(1000,620)
    var measure := {"number":1,"clefs":{"right":{"sign":"G","line":2,"octave_change":0},
        "left":{"sign":"F","line":4,"octave_change":0}}}
    renderer.timeline.measures = [measure]
    renderer.measure_by_number = {1:measure}
    var lower := {"id":"display-bass","source_id":"source-right-C2","measure":1,"beat":0.0,
        "kind":"note","staff":"left","hand":"right","voice":"register-bass","is_attack":true,
        "spelling":{"step":"C","alter":0,"octave":2},
        "fingering":{"source_id":"source-right-C2","hand":"right","finger":2,"origin":"automatic"}}
    var upper := {"id":"display-treble","source_id":"source-left-C5","measure":1,"beat":0.0,
        "kind":"note","staff":"right","hand":"left","voice":"register-treble","is_attack":true,
        "spelling":{"step":"C","alter":0,"octave":5}}
    var legacy := {"id":"legacy","source_id":"legacy-right","kind":"note","staff":"right","is_attack":true}
    renderer.expression_note_index = {"display-bass":lower,"display-treble":upper}
    var failures: Array = []
    # Actual menu text is a user-visible consumer, independent of colour.
    for event in [lower,upper,legacy]:
        var menu := PopupMenu.new()
        renderer.fingering_popup = menu
        renderer._fill_fingering_menu(menu,event)
        var expected: String = str(event.get("hand",event["staff"])).capitalize()+" hand"
        if not menu.get_item_text(0).begins_with(expected):
            failures.append("Editor reports display staff instead of performing hand: "+str(event["id"]))
        menu.free()
        renderer.fingering_popup = null
    # Literal musical positions: C2 is four staff spaces below bass centre;
    # C5 is half a space above treble centre. Hand must not enter geometry.
    if absf(renderer._event_y(lower,20.0)-(620.0*.69+80.0))>.001:
        failures.append("RH C2 did not use its displayed bass clef/staff")
    if absf(renderer._event_y(upper,20.0)-(620.0*.36-10.0))>.001:
        failures.append("LH C5 did not use its displayed treble clef/staff")
    if renderer._fingering_source(lower)!="source-right-C2" or renderer._fingering_assignment(lower)["hand"]!="right":
        failures.append("Fingering binding lost the original source/performing hand")
    if not renderer.has_method("_event_ink") or not renderer.has_method("_performing_hand"):
        failures.append("Native event selection has no separate performing-hand policy")
    else:
        for selected in ["right","left","both"]:
            renderer.active_hand = selected
            for event in [lower,upper,legacy]:
                var hand: String = str(event.get("hand",event["staff"]))
                var wanted: Color = renderer.NOTE_INK if selected in [hand,"both"] else Color(renderer.DIM_INK,.46)
                if renderer._event_ink(event)!=wanted:
                    failures.append("Event selection follows staff for "+str(event["id"])+" / "+selected)
        # Expressive models historically called their display lane 'hand'. A
        # note-linked mark must instead inherit its target's performer.
        for mark in [{"kind":"articulation","note_id":"display-bass","hand":"left"},
                {"before_note_id":"display-bass","hand":"left"}]:
            if renderer._performing_hand(mark)!="right":
                failures.append("Attached decoration lost its target's performing hand")
        if renderer._performing_hand(legacy)!="right":
            failures.append("Legacy staff-only model changed hand selection")
    var opening: Dictionary = measure.duplicate(true)
    opening.merge({"start_beat":0.0,"end_beat":.5,"meter":[1,8],"keys":{"right":0,"left":0}},true)
    var normal: Dictionary = opening.duplicate(true)
    normal.merge({"start_beat":.5,"end_beat":4.5,"meter":[4,4]},true)
    var silence: Dictionary = opening.duplicate(true)
    silence.merge({"start_beat":4.5,"end_beat":8.5,"duration_beats":4.0,
        "meter":[4,4],"source_meter":[1,8]},true)
    renderer.timeline.measures = [opening,normal]
    renderer.practice_timeline = {"gap":silence,"stride_beats":8.5}
    var previous: Dictionary = renderer._practice_context_before(8.5,8.5)
    if previous.get("meter")!=[4,4] or previous.get("start_beat")!=4.5 or previous.get("end_beat")!=8.5:
        failures.append("Copy-boundary predecessor lost the actual 4/4 gap context")
    if not renderer.has_method("_context_meter_x"):
        failures.append("Repeated pickup meter has no incoming-rule clearance")
    else:
        renderer.glyphs.bounds["time_1"] = [0.0,0.0,250.0,250.0]
        renderer.glyphs.bounds["time_8"] = [0.0,0.0,250.0,250.0]
        var meter_x: float = renderer._context_meter_x(opening,200.0,20.0,false,172.0)
        if meter_x+10.0>170.0:
            failures.append("Authentic pickup meter ink crosses its incoming barline")
        var json_opening: Dictionary = opening.duplicate(true)
        json_opening["meter"] = JSON.parse_string("[1,8]")
        if renderer._context_meter_x(json_opening,200.0,20.0,false,172.0)!=meter_x:
            failures.append("JSON float meter changed its engraved digit bounds")
    renderer.free()
    for path in request.get("fixtures",[]):
        failures.append_array(_fixture_checks(script,str(path)))
    return failures

func _fixture_checks(script: GDScript, path: String) -> Array:
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
    var assets: Dictionary = fixture["assets"]
    var renderer = script.new()
    renderer.size = Vector2(1216,455)
    root.add_child(renderer)
    var failures: Array = []
    var loaded: bool = renderer.set_verovio_glyphs(assets["native_glyphs"],assets["native_note_templates"],
        assets["native_tie_templates"],assets["native_chord_templates"],assets["native_beam_fragments"],
        assets["native_tuplet_fragments"],assets["native_slur_fragments"],assets["native_required_slur_pairs"],
        assets["native_slurs_complete"],assets["native_required_beam_groups"],assets["native_beams_complete"])
    if not loaded or not renderer.load_score(fixture["model"]):
        renderer.free()
        return ["Actual Peace Piece fixture failed native preparation"]
    var gap: float = renderer._gap()
    # Compare independently imported complete sprite bounds at simultaneous
    # anchors. A bass-staff shaft may not invade treble ink merely because
    # both individual sprites fit inside the outer viewport.
    var written_ink: Array = []
    for event in renderer.ordered_events:
        if event["kind"]!="note" or event["chord"] or renderer.beamed_note_ids.has(event["id"]):
            continue
        var box: Array
        if renderer.chord_members.has(event["id"]):
            box = assets["native_chord_templates"][renderer._chord_template_key(event)]["bounds"]
        else:
            var up: bool = renderer._chord_extents(event,gap)["up"]
            var key: String = "whole" if event["note_type"]=="whole" else str(event["note_type"])+("_up" if up else "_down")
            box = assets["native_note_templates"][key]["bounds"]
        var y: float = renderer._event_y(event,gap)
        written_ink.append({"staff":event["staff"],"beat":event["beat"],"id":event["id"],
            "top":y+float(box[1])*gap/250.0,"bottom":y+float(box[1]+box[3])*gap/250.0})
    var simultaneous := 0
    for upper in written_ink:
        for lower in written_ink:
            if upper["staff"]!="right" or lower["staff"]!="left" or upper["beat"]!=lower["beat"]:
                continue
            simultaneous += 1
            if float(lower["top"])-float(upper["bottom"])<3.0-.01:
                failures.append("Simultaneous authentic treble/bass ink intersects: "+str(upper["id"])+" / "+str(lower["id"])+
                    " clearance="+str(float(lower["top"])-float(upper["bottom"])))
    if simultaneous==0:
        failures.append("Interstaff positive control lacks simultaneous source ink")
    renderer.cached_head_offsets = renderer._engraved_head_offsets(gap)
    renderer.cached_accidental_offsets = renderer.Geometry.accidental_offsets(
        renderer.ordered_events,gap,renderer.cached_head_offsets,renderer.glyphs.bounds)
    renderer.active_hand = "right"
    var bass := 0
    var unisons := 0
    var targets: Array = []
    for event in renderer.ordered_events:
        if event["kind"]!="note":
            continue
        var original_hand: String = event["hand"]
        if renderer._event_ink(event)!=(renderer.NOTE_INK if original_hand=="right" else Color(renderer.DIM_INK,.46)):
            failures.append("Real source selection follows its display staff")
        if event["staff"]=="left" and original_hand=="right":
            bass += 1
            var up: bool = renderer._chord_extents(event,gap,renderer.cached_head_offsets)["up"]
            var stem: Array = renderer._source_stem_bounds(event,up)
            if event["note_type"]=="half" and stem!=renderer.glyphs.note_stem_bounds["half_up" if up else "half_down"]:
                failures.append("Remote half-note stem is not its authentic isolated template")
            for other in renderer.ordered_events:
                if other["kind"]=="note" and other["staff"]=="left" and other["hand"]=="left" and \
                        other["beat"]==event["beat"] and other["midi_pitch"]==event["midi_pitch"] and \
                        other["note_type"]=="quarter" and event["note_type"]=="half":
                    unisons += 1
                    var distance: float = absf(float(renderer.cached_head_offsets.get(event["id"],0.0))-
                        float(renderer.cached_head_offsets.get(other["id"],0.0)))
                    if distance<gap*.7:
                        failures.append("Hollow RH and filled LH unison heads share one column")
        if event["hand"]=="right" and event.get("fingering") is Dictionary and event["is_attack"]:
            if not targets.any(func(e: Dictionary) -> bool: return e["staff"]==event["staff"]):
                targets.append(event)
    renderer._layout_fingerings(gap)
    for target in targets:
        var matches: Array = renderer.fingering_layout.filter(func(item: Dictionary) -> bool:
            return target["id"] in item["event_ids"])
        if matches.size()!=1 or matches[0]["hand"]!="right" or absf(matches[0]["head"].y-renderer._event_y(target,gap))>.001:
            failures.append("RH fingering lost its source or displayed notehead")
        var requests: Array = []
        var menu := PopupMenu.new()
        renderer.fingering_popup = menu
        renderer._fill_fingering_menu(menu,target)
        renderer.fingering_change_requested.connect(func(source_id: String, finger: Variant):
            requests.append({"source_id":source_id,"finger":finger}),CONNECT_ONE_SHOT)
        menu.id_pressed.emit(5)
        if requests!=[{"source_id":target["source_id"],"finger":5}]:
            failures.append("Real display-staff fingering edit targeted a different source")
        menu.free()
        renderer.fingering_popup = null
    if bass==0 or targets.size()!=2:
        failures.append("Real source positive control lacks RH notes/fingerings on both staves")
    if fixture["first_bar"]==3 and unisons==0:
        failures.append("Real source positive control lacks the half/quarter unison")
    # Real source pixels supply the complete template, including its cap.
    # Probe the same isolated half-note policy at the lowest opposite-stem
    # unison and one step below, plus a high up-stem note. No source file or
    # grading model is changed; these are native vertical-fit contracts.
    var prototype: Dictionary = targets[0].duplicate(true)
    renderer.chord_members.clear()
    renderer.beam_groups.clear()
    renderer.beamed_note_ids.clear()
    renderer.notation_tuplets.clear()
    renderer.size = Vector2(1536,520)
    for probe in [{"staff":"left","spelling":{"step":"C","alter":0,"octave":2},"factor":4.0,"up":false},
            {"staff":"left","spelling":{"step":"B","alter":0,"octave":1},"factor":4.5,"up":false},
            {"staff":"right","spelling":{"step":"B","alter":0,"octave":6},"factor":-7.0,"up":true}]:
        var event: Dictionary = prototype.duplicate(true)
        event.merge({"id":"vertical-fit-probe","kind":"note","note_type":"half","chord":false,
            "staff":probe["staff"],"spelling":probe["spelling"],"accidental":null,"dots":0},true)
        renderer.ordered_events = [event]
        renderer.voice_stem_up_by_note = {"vertical-fit-probe":probe["up"]}
        renderer.cached_staff_gap = -1.0
        renderer.cached_gap_height = -1.0
        var fitted: float = renderer._gap()
        var box: Array = assets["native_note_templates"]["half_up" if probe["up"] else "half_down"]["bounds"]
        var center: float = 520.0*(.69 if probe["staff"]=="left" else .36)
        var top: float = center+(float(probe["factor"])+float(box[1])/250.0)*fitted
        var bottom: float = center+(float(probe["factor"])+float(box[1]+box[3])/250.0)*fitted
        if top<3.0-.001 or bottom>517.0+.001:
            failures.append("Authentic complete half-note sprite leaves viewport inset: "+str(probe["spelling"])+
                " top="+str(top)+" bottom="+str(bottom))
    renderer.free()
    return failures

func _run() -> void:
    var directory: String = OS.get_cmdline_user_args()[0]
    var last := ""
    FileAccess.open(directory.path_join("ready"),FileAccess.WRITE).store_string("ready")
    while true:
        var path: String = directory.path_join("request.json")
        if FileAccess.file_exists(path):
            var request: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
            if request is Dictionary and str(request.get("id",""))!=last:
                last = str(request["id"])
                if request.get("action")=="quit":
                    quit()
                    return
                var failures: Array = _checks(request)
                FileAccess.open(directory.path_join(last+".json"),FileAccess.WRITE).store_string(JSON.stringify(failures))
        await create_timer(.02).timeout
'''


def _start(directory):
    binary = shutil.which('godot') or shutil.which('godot4')
    if not binary:
        pytest.skip('Godot 4 unavailable')
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / 'display-hand-contract.gd'
    script.write_text(HARNESS)
    log = (directory / 'godot.log').open('w')
    process = subprocess.Popen([binary, '--headless', '--path', str(ROOT / 'godot'),
        '--audio-driver', 'Dummy', '--script', str(script), '--', str(directory)],
        stdout=log, stderr=subprocess.STDOUT)
    return process, log


def _request(directory, action, *, fixtures=()):
    identity = uuid4().hex
    temporary = directory / 'request.tmp'
    temporary.write_text(json.dumps({'id': identity, 'action': action, 'fixtures': list(map(str, fixtures))}))
    temporary.replace(directory / 'request.json')
    return directory / (identity + '.json')


def _wait_for(path, directory):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(.02)
    pytest.fail('Native display-hand contract timed out:\n' + (directory / 'godot.log').read_text())


@pytest.fixture(scope='module')
def display_hand_session(tmp_path_factory):
    external = os.environ.get('NATIVE_DISPLAY_HAND_SESSION')
    directory = Path(external) if external else tmp_path_factory.mktemp('native-display-hand')
    owned = None if external else _start(directory)
    try:
        _wait_for(directory / 'ready', directory)
        yield directory
    finally:
        if owned:
            _request(directory, 'quit')
            process, log = owned
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()


def test_native_display_staff_does_not_change_performing_hand(display_hand_session):
    reply = _request(display_hand_session, 'check')
    _wait_for(reply, display_hand_session)
    assert json.loads(reply.read_text()) == []


def test_real_peace_registers_unisons_and_source_fingering_edits(display_hand_session, tmp_path):
    from hashlib import sha256
    from piano_teacher.fingering import FingeringService, project_model
    from piano_teacher.importing.pieces import import_piece
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    path = ROOT / 'midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'
    piece, _ = import_piece(path)
    plan = FingeringService(tmp_path / 'plans').prepare(piece, sha256(path.read_bytes()).hexdigest())
    paths = []
    for first, last in ((1, 2), (3, 4)):
        data, _ = fixture(AuditCase('display-hand', str(path), first, last, 'right'), piece=piece)
        data['model'] = project_model(data['model'], plan, source_musicxml=piece.source_musicxml)
        payload = tmp_path / f'fixture-{first}.json'
        payload.write_text(json.dumps(data))
        paths.append(payload)
    reply = _request(display_hand_session, 'check', fixtures=paths)
    _wait_for(reply, display_hand_session)
    assert json.loads(reply.read_text()) == []


if __name__ == '__main__':
    assert sys.argv[1] == '--serve'
    process, log = _start(Path(sys.argv[2]))
    try:
        raise SystemExit(process.wait())
    finally:
        log.close()
