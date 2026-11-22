"""A3: idempotent physical present responses remain bound to their live epoch."""
from dataclasses import replace

import pytest

from piano_teacher.application.playback_coordinator import PlaybackCoordinator, PlaybackState
from piano_teacher.application.playback_facts import PlaybackRuntimeFacts, PlaybackSourceFacts


def _authorized():
    source = PlaybackSourceFacts(
        fingerprint="original", stage_key="stage:right", revision=7,
        hand="right", bpm=80, end_beat=4.0,
        count_in_bar_beats=4.0, count_in_meter=(4, 4),
        tempo_segments=((0.0, 4.0, 80.0),))
    facts = PlaybackRuntimeFacts(
        source=source, now=100.0, mode="practice", running=True,
        paused=False, run_at=100.0, paused_at=0.0,
        play_from_beat=0.0, resume_grading_after=0.0,
        pause_context=None, preview_only=False, pending_result=False,
        transport_id=19)
    owner = PlaybackCoordinator(presentation_required=True)
    owner.state = PlaybackState.PLAYING
    owner.active_take_id = "take"
    owner.active_segment_id = "segment"
    owner.active_segment = {
        "mode": "practice",
        "source": {"fingerprint": source.fingerprint,
                   "stage_key": source.stage_key,
                   "revision": source.revision, "hand": source.hand,
                   "end_beat": source.end_beat},
        "transport_id": 19}
    receipt = {"intent_id": "intent", "attempt": 0, "take_id": "take",
               "segment_id": "segment", "authorized": True}
    owner._completed.append(("segment", receipt))
    return owner, facts, receipt


def _replay(owner, facts):
    return owner.present(
        facts, intent_id="intent", attempt=0, segment_id="segment",
        commit=lambda *_: pytest.fail("Committed physical take must not restart"),
        capture=lambda: pytest.fail("No second transport capture"),
        abort=lambda _: pytest.fail("No second abort"))


def test_retransmitted_present_receipt_is_idempotent_on_the_live_source():
    owner, facts, receipt = _authorized()
    assert _replay(owner, facts) == receipt
    assert owner.state == PlaybackState.PLAYING


@pytest.mark.parametrize("changed", [
    {"fingerprint": "other"},
    {"stage_key": "stage:left"},
    {"revision": 8},
    {"hand": "left"},
    {"end_beat": 3.0},
])
def test_retransmitted_present_cannot_reauthorize_another_source(changed):
    owner, facts, _ = _authorized()
    with pytest.raises(ValueError, match="superseded"):
        _replay(owner, replace(facts, source=replace(facts.source, **changed)))


def test_retransmitted_present_rejects_superseded_transport_epoch():
    owner, facts, _ = _authorized()
    with pytest.raises(ValueError, match="superseded"):
        _replay(owner, replace(facts, transport_id=20))
    owner.invalidate("Stop")
    with pytest.raises(ValueError, match="superseded"):
        _replay(owner, facts)


@pytest.mark.parametrize("state", [PlaybackState.COMPLETE,
                                   PlaybackState.FAILED, PlaybackState.IDLE])
def test_finished_or_failed_take_cannot_be_reauthorized_by_old_present(state):
    owner, facts, _ = _authorized()
    owner.state = state
    with pytest.raises(ValueError, match="superseded"):
        _replay(owner, facts)


def test_changed_playback_mode_cannot_reuse_old_present_receipt():
    owner, facts, _ = _authorized()
    with pytest.raises(ValueError, match="superseded"):
        _replay(owner, replace(facts, mode="listen"))
