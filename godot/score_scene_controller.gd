extends RefCounted
## One atomic replacement port for the active renderer of a score stage.
## ScoreRunway owns the retained predecessor FIFO and prepared assets;
## ScoreAdmissionGateway owns physical admission. Neither mutates
## stage.renderer or the active asset session independently.
signal renderer_promoted(renderer)

var _stage
var _assets
var _generation := 0

func _init(stage, assets) -> void:
    if stage == null or assets == null:
        push_error("ScoreSceneController requires a stage and asset session")
    _stage = stage
    _assets = assets

func active_renderer():
    return _stage.renderer

func active_generation() -> int:
    return _generation

func owns_active(candidate) -> bool:
    return candidate != null and is_instance_valid(candidate) and \
        _stage.renderer == candidate

func _same_stage(candidate) -> bool:
    return candidate != null and is_instance_valid(candidate) and \
        candidate.get_parent() == _stage.score_frame

func activate_unprepared(outgoing, incoming, state: Dictionary) -> bool:
    if not owns_active(outgoing) or not _same_stage(incoming):
        return false
    if (int(state.get("revision",-1)) == _assets.revision and
            str(state.get("piece_fingerprint","")) == _assets.source_fingerprint()):
        return false
    _assets.replace_renderer(incoming)
    _stage.renderer = incoming
    _generation += 1
    renderer_promoted.emit(incoming)
    return true

func promote_admitted(outgoing, incoming, state: Dictionary,
        prepared_layout: Dictionary) -> bool:
    if not owns_active(outgoing) or not _same_stage(incoming) or \
            not incoming.has_armed_reservation():
        return false
    # Assets are installed only for the exact authorized destination.
    if int(state.get("revision",-1)) < _assets.revision:
        return false
    _assets.adopt_prepared(state,incoming,prepared_layout)
    _stage.renderer = incoming
    _generation += 1
    renderer_promoted.emit(incoming)
    return true
