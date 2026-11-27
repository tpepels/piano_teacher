extends RefCounted
## Sole delivery, deduplication and acknowledgement owner for live note
## feedback. Backend events carry their own take identities; stale UI
## snapshots never suppress or regrade a physically received event.
const FeedbackEventInbox := preload("res://feedback_event_inbox.gd")
const LiveMidiFeedback := preload("res://live_midi_feedback.gd")

var _inbox = FeedbackEventInbox.new()
var _reactions = LiveMidiFeedback.new()
var _bus
var _stage
var _clock

func configure(bus, stage, clock) -> void:
    _bus = bus
    _stage = stage
    _clock = clock

func source_invalidated() -> void:
    _reactions.clear()

func layout_published(attacks: Dictionary, revision: int) -> void:
    _reactions.bind_attacks(attacks,revision)

func poll(now_ms: int, matching_revision: int) -> void:
    if _bus == null or not _bus.is_ready():
        return
    ingest(_bus.take_feedback_events(),now_ms,matching_revision)
    _bus.request_feedback_events(_inbox.acknowledged)

func ingest(reply: Variant, now_ms: int, matching_revision: int) -> void:
    for event in _inbox.accept(reply):
        _deliver(event,now_ms,matching_revision)
        # Acknowledge only after both consumers have returned. The backend
        # retains a repeated event until then, so no feedback is lost on a
        # delayed or obsolete visual state poll.
        _inbox.acknowledge(int(event["sequence"]))

func _deliver(event: Dictionary, now_ms: int, matching_revision: int) -> void:
    _stage.feedback.ingest(event)
    if str(event.get("kind","")) != "attack":
        return
    var age_ms := 0.0
    if _clock.has_backend_offset and event.has("received_at"):
        age_ms = float(now_ms) - (
            float(event["received_at"])*1000.0 + _clock.backend_offset_ms)
    _reactions.react(event,_stage,matching_revision,age_ms)
