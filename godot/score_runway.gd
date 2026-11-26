extends Node
## Outgoing score layers. When a new score revision replaces the shown one,
## the old renderer keeps its already-visible ink scrolling on the same
## world until its last strip leaves; the new renderer checks its ink
## against every still-live predecessor layer.
const NativeView := preload("res://notation/native/view.gd")
const ScoreSceneController := preload("res://score_scene_controller.gd")
signal renderer_promoted(new_renderer)

var stage
var score_session
var _scene_owner
# Every outgoing score owns its retained ink until its last clip leaves.
# Two quick lesson changes may overlap: there is no single-tail shortcut.
var _tails: Array = []
# During a revision change, this outgoing renderer temporarily owns the
# visible staff and playhead until replacement ink is published.
var _manual_staff_tail

func configure(_host: Node, practice_stage, session, _bus: Node) -> void:
    stage = practice_stage
    score_session = session
    _scene_owner = ScoreSceneController.new(stage,score_session)
    _scene_owner.renderer_promoted.connect(
        func(view): renderer_promoted.emit(view))

func _link_existing_layers(incoming) -> void:
    # All renderer layers live on one visual world axis. Queue ownership
    # stays with the originating renderer; every new admission must check
    # the previously committed ink in ALL still-live predecessor layers.
    if not incoming is NativeView:
        return
    var predecessors: Array = _tails.duplicate()
    if stage != null and stage.renderer != null:
        predecessors.append(stage.renderer)
    for previous in predecessors:
        if previous != incoming and previous is NativeView and \
                is_instance_valid(previous):
            incoming.register_stream_predecessor(previous)

func _retain_tail(old, keep_staff: bool = false) -> void:
    if old == null or not is_instance_valid(old) or _tails.has(old):
        return
    # Lesson changes retract the maximal never-seen future suffix before
    # handing off the old renderer. Already-visible notes remain immutable.
    old.trim_future_queue("lesson_handoff")
    old.runway_overlay = not keep_staff
    if is_instance_valid(old.retained_annotations):
        old.retained_annotations.queue_redraw()
    old.runway_cutoff_beat = INF
    old.set_transport_overlay_enabled(keep_staff)
    old.mouse_filter = Control.MOUSE_FILTER_IGNORE
    old.queue_redraw()
    # Leave outgoing ink below the fixed HUD. Moving a tail to the end of
    # score_frame makes it paint over the count-in and note feedback.
    if stage.renderer != old and old.get_parent() == stage.score_frame and \
            is_instance_valid(stage.renderer) and \
            old.get_index() > stage.renderer.get_index():
        stage.score_frame.move_child(old,stage.renderer.get_index())
    _tails.append(old)
    if keep_staff:
        _manual_staff_tail = old

func staff_renderer():
    return _manual_staff_tail if is_instance_valid(_manual_staff_tail) else null

func active_revision_published(_revision: int) -> void:
    # Called by ScoreAssetSession only once the replacement has completed
    # authentic engraving. This is the handoff of staff/cursor ownership.
    if _manual_staff_tail == null:
        return
    if is_instance_valid(_manual_staff_tail):
        _manual_staff_tail.runway_overlay = true
        _manual_staff_tail.set_transport_overlay_enabled(false)
        _manual_staff_tail.queue_redraw()
    _manual_staff_tail = null
    if stage != null and is_instance_valid(stage.renderer):
        stage.renderer.runway_overlay = false
        stage.renderer.set_transport_overlay_enabled(true)
        stage.renderer.queue_redraw()

func _advance_tails(global_beat: float) -> void:
    # The renderer layers are ONE ordered FIFO of successive score sources.
    # Every layer projects on the same global clock; a later renderer can
    # never be freed ahead of an older layer still displaying notation.
    for tail in _tails:
        if tail != null and is_instance_valid(tail):
            tail.present_flow(global_beat,{},0.0,false)
    while not _tails.is_empty():
        var first = _tails[0]
        if first == null or not is_instance_valid(first):
            _tails.pop_front()
            continue
        if first == _manual_staff_tail or first.stream_pass_count() > 0:
            break
        # The source queue has already journaled all withdrawn/expired ink.
        first.queue_free()
        _tails.pop_front()

func preserve_unprepared_revision(state: Dictionary) -> bool:
    # Every new revision uses the same forward-only stream. Swap the asset
    # destination BEFORE ScoreAssetSession.update_context() resets it.
    # Otherwise reset_assets() clears still-visible outgoing noteheads.
    if not bool(state.get("loaded",false)) or stage == null or \
            not score_session.is_ready() or not is_instance_valid(stage.renderer):
        return false
    if score_session.matches_ready_state(state):
        return false
    var outgoing = stage.renderer
    var incoming = NativeView.new()
    incoming.external_backdrop = outgoing.external_backdrop
    incoming.active_hand = str(state.get("hand","both"))
    incoming.set_density(float(outgoing.configured_density))
    incoming.runway_overlay = true
    incoming.set_transport_overlay_enabled(false)
    _link_existing_layers(incoming)
    stage.score_frame.add_child(incoming)
    stage.score_frame.move_child(incoming,outgoing.get_index()+1)
    incoming.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    incoming.visible = false
    if not _scene_owner.activate_unprepared(outgoing,incoming,state):
        incoming.queue_free()
        return false
    # Even an empty outgoing staff owns the playhead until publication.
    _retain_tail(outgoing,true)
    return true

func present_frame(_state: Dictionary, global_beat: float) -> void:
    _advance_tails(global_beat)
