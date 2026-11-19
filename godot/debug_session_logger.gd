extends RefCounted
const StateContract := preload("res://state_contract.gd")
## Sole read-only ownership of session debugging, diagnostics file lifecycle
## and bounded per-state logging. Does not access Main or alter playback.
var _debug_file: FileAccess = null
var _debug_checked := false
var _debug_key := ""
var _debug_target := ""
var _debug_beat_ms := 0
var _debug_inputs := -1
var _debug_unscored := ""
var _reported_contract_problems: Dictionary = {}

## Log each published contract violation exactly once.  Main is only a
## lifecycle/composition root and has no schema diagnostic state.
func check_contract(state: Dictionary) -> void:
    if not OS.is_debug_build() or not state.has("schema_version"):
        return
    for problem in StateContract.problems(state):
        if not _reported_contract_problems.has(problem):
            _reported_contract_problems[problem] = true
            push_error("STATE_CONTRACT: " + problem)


func record(state: Dictionary, now_ms: int, renderer,
        keyboard_visible: bool, guided_world: float, hold_world: float) -> void:
    if not _debug_checked:
        _debug_checked = true
        var path := OS.get_environment("PIANO_DEBUG_LOG")
        if not path.is_empty():
            _debug_file = FileAccess.open(path, FileAccess.WRITE)
    if _debug_file == null:
        return
    var heads: int = renderer.drawn_noteheads.size() if renderer != null else -1
    var staff: String = str(renderer.size) if renderer != null else "-"
    var world: float = float(renderer.stream_world_beat) if renderer != null else NAN
    var flow: Dictionary = state.get("flow", {}) if state.get("flow") is Dictionary else {}
    var stamp := "%9.3f" % (now_ms / 1000.0)
    var key := "%s|%s|rev%s|tr%s|%s|%s|bpm%s" % [state.get("mode"), state.get("phase"),
        state.get("revision"), state.get("transport_id"), state.get("lesson_step"),
        state.get("hand"), state.get("bpm")]
    if key != _debug_key:
        _debug_key = key
        _debug_file.store_line("%s STATE %s | %s | msg=%s | feedback=%s" % [stamp, key,
            flow.get("status", ""), flow.get("message", ""), state.get("feedback", "")])
    if renderer != null and str(renderer.unscored_take_status()) != _debug_unscored:
        _debug_unscored = str(renderer.unscored_take_status())
        _debug_file.store_line("%s DEFECT TAKE_WITHOUT_SCORE %s" % [stamp, _debug_unscored])
    var inputs := int(state.get("midi_input_count", 0))
    if inputs != _debug_inputs:
        _debug_inputs = inputs
        _debug_file.store_line("%s MIDI count=%d held=%s recent=%s device=%s" % [stamp, inputs,
            str(state.get("midi_held_pitches", [])), str(state.get("midi_recent_keys", [])).left(160),
            state.get("device", "")])
    var teaching: Variant = state.get("teaching")
    if teaching is Dictionary and str(state.get("mode", "")) == "learn":
        var pitches: Array = []
        for note in teaching.get("expected_notes", []):
            if note is Dictionary:
                pitches.append(int(note.get("pitch", 0)))
        var target := "%d/%d %s hint=%s" % [int(teaching.get("target_index", 0)),
            int(teaching.get("target_count", 0)), str(pitches), str(teaching.get("hint_visible"))]
        if target != _debug_target:
            _debug_target = target
            _debug_file.store_line("%s FREE target=%s heard=%s heads=%d world=%.2f guided_world=%.2f held=%s keyboard=%s staff=%s" % [
                stamp, target, str(teaching.get("heard_pitches", [])), heads, world,
                guided_world, str(hold_world), str(keyboard_visible), staff])
    if now_ms - _debug_beat_ms >= 1000:
        _debug_beat_ms = now_ms
        _debug_file.store_line("%s STAFF heads=%d world=%.2f passes=%d keyboard=%s staff=%s visible=%s" % [
            stamp, heads, world, renderer.stream_passes.size() if renderer != null else -1,
            str(keyboard_visible), staff, str(renderer.visible if renderer != null else false)])
    _debug_file.flush()
