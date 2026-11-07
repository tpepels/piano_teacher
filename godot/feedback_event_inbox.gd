extends RefCounted
## The single acknowledgement cursor for the backend FeedbackEventLog.
##
## The backend retains every event until it is acknowledged. A reply may
## repeat events (a request can be issued before the previous reply was
## processed); those are skipped by sequence. An event is acknowledged only
## after its consumer returned a final outcome for it (applied, buffered for
## a not-yet-bound engraving, or deliberately ignored). Nothing is dropped
## because a state snapshot happened to be stale.
var acknowledged := 0
var lost_through := 0
var gaps := 0

func accept(reply: Variant) -> Array:
    if not reply is Dictionary:
        return []
    var lost: int = int(reply.get("lost_through",0))
    if lost > acknowledged and lost > lost_through:
        # The backend overflowed its bounded log while the UI was not reading.
        lost_through = lost
        push_error("NOTE_FEEDBACK_EVENTS_LOST: through sequence %d" % lost)
    var fresh: Array = []
    var expected: int = maxi(acknowledged,lost_through)+1
    for candidate in reply.get("events",[]):
        if not candidate is Dictionary:
            continue
        var sequence: int = int(candidate.get("sequence",0))
        if sequence <= acknowledged:
            continue
        if sequence != expected:
            gaps += 1
            push_error("NOTE_FEEDBACK_SEQUENCE_GAP: expected %d, received %d" % [
                expected,sequence])
        expected = sequence+1
        fresh.append(candidate)
    return fresh

func acknowledge(sequence: int) -> void:
    acknowledged = maxi(acknowledged,sequence)
