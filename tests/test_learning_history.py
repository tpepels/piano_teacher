"""The history shown/exported to a learner must describe actual retained takes."""
import json

import pytest

from piano_teacher.inprocess import INVALID
from session_inputs import write_midi, take


def tempo(session):
    session.finish_listen()
    session.finish_free()
    return session.ready_score()


def test_empty_history_reports_unknown_accuracy_and_timing(practice_session):
    session = practice_session(bars=1)
    report = session.ask("learning.statistics")
    assert report["attempts"]["count"] == 0
    assert report["assessments"]["acceptance_rate"] is None
    assert report["pitch"]["accuracy"] is None
    assert report["timing"]["onset"]["mean_seconds"] is None
    assert report["timing"]["onset"]["sample_count"] == 0
    assert not report["mastery"]["episodes"]


def test_statistics_keep_signed_timing_and_distinguish_misses_from_unknowns(practice_session):
    session = practice_session(bars=1)
    state = tempo(session)
    start = take(state)["deadline_ms"]/1000
    for at, pitch in ((start+.01, 72), (start+2.25-.02, 79)):
        session.clock.at = at
        session.key(pitch, after=0)
        session.key(pitch, False, after=.1)
    from test_midi_journeys import play
    state = session.play_take(correct=False)
    assert state["bpm"] == 80 and state["streak"] == 1
    play(session,state,missing=(1,))  # Recorded partial failure, not AFK silence.
    session.command("stop")
    report = session.ask("learning.statistics", scope="full")
    assert report["assessments"]["accepted"] == 1
    assert report["assessments"]["rejected"] == 1
    assert report["assessments"]["acceptance_rate"] == .5
    assert report["pitch"]["correct_required_pitches"] == 3
    assert report["pitch"]["omitted"] == 1
    assert report["pitch"]["accuracy"] == .75
    assert report["timing"]["onset"]["sample_count"] == 3
    assert report["timing"]["onset"]["mean_seconds"] == pytest.approx(-.01/3)
    assert report["timing"]["onset"]["mean_absolute_seconds"] == pytest.approx(.01)
    assert report["timing"]["onset"]["minimum_seconds"] == pytest.approx(-.02)
    assert report["timing"]["onset"]["maximum_seconds"] == pytest.approx(.01)
    assert report["pitch"]["unobserved_suffix_obligations"] is None
    assert all(not episode["mastered"] for episode in report["mastery"]["episodes"])
    assert session.ask("learning.statistics", hand="left")["attempts"]["count"] == 0
    target = session.ask("learning.statistics", scope="full", bpm_min=80, bpm_max=80)
    assert target["assessments"]["accepted"] == 1
    assert target["assessments"]["rejected"] == 1
    assert all(row["performed_bpm"] == 80 for row in target["assessment_strata"])


def test_history_paging_is_stable_while_new_takes_arrive(practice_session):
    session = practice_session(bars=1)
    tempo(session)
    from test_midi_journeys import play
    session.play_take()
    play(session,session.snapshot(),missing=(1,))
    original = session.ask("learning.statistics", scope="full")["query"]["attempt_ids"]
    page = session.ask("learning.statistics", scope="full", limit=1)
    assert page["query"]["has_more"]
    session.play_take()
    found = list(page["query"]["attempt_ids"])
    while page["query"]["has_more"]:
        page = session.ask("learning.statistics", scope="full", limit=1,
                           cursor=page["query"]["next_cursor"])
        found += page["query"]["attempt_ids"]
    assert found == original
    assert len(set(found)) == len(found)
    assert len(session.ask("learning.statistics", scope="full")["query"]["attempt_ids"]) > len(found)


def test_bounded_detail_preserves_counts_without_fabricating_zero_errors(practice_session):
    session = practice_session(bars=1)
    tempo(session)
    from test_midi_journeys import play
    session.play_take()
    play(session,session.snapshot(),missing=(1,))
    full = session.ask("learning.statistics", scope="full")
    bounded = session.ask("learning.statistics", scope="full", detail_budget_bytes=1)
    assert bounded["assessments"]["accepted"] == full["assessments"]["accepted"]
    assert bounded["assessments"]["rejected"] == full["assessments"]["rejected"]
    assert bounded["mistakes"]["status_counts"] == full["mistakes"]["status_counts"]
    assert bounded["coverage"]["detail_budget_truncated_attempts"] > 0
    assert not bounded["coverage"]["detail_history_complete"]
    assert bounded["timing"]["onset"]["sample_count"] == 0
    assert bounded["timing"]["onset"]["mean_seconds"] is None
    assert bounded["pitch"]["accuracy"] is None
    assert bounded["pitch"]["unknown_obligations"] == 4


def test_export_detail_is_explicit_redacted_and_a_failed_write_preserves_the_file(
        practice_session, tmp_path, monkeypatch):
    session = practice_session(bars=1)
    tempo(session)
    session.play_take()
    session.command("stop")
    summary_path, detail_path = tmp_path/"summary.json", tmp_path/"detail.json"
    session.ask("learning.export", path=str(summary_path))
    session.ask("learning.export", path=str(detail_path), include_detail=True)
    summary, detail = (json.loads(path.read_text()) for path in (summary_path, detail_path))
    assert not summary["include_detail"] and detail["include_detail"]
    assert all(attempt["detail"] is None for attempt in summary["attempts"])
    assert any(attempt["detail"] and attempt["detail"].get("observations")
               for attempt in detail["attempts"])
    assert {a["attempt_id"] for a in summary["attempts"]} == {
        a["attempt_id"] for a in detail["attempts"]}
    assert "Test piano" not in detail_path.read_text()
    assert str(session.path) not in detail_path.read_text()
    original = summary_path.read_bytes()

    def disk_full(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(type(summary_path), "replace", disk_full)
        status, body = session.commands.request("learning.export", json.dumps({"path": str(summary_path)}))
        assert status != 0 and "disk full" in body.decode()
    assert summary_path.read_bytes() == original
    assert not list(tmp_path.glob("summary.json.*.tmp"))
    assert session.ask("learning.statistics")["assessments"]["accepted"] == 1


def test_reset_preserves_history_and_confirmed_deletion_is_scoped(practice_session):
    session = practice_session(bars=1)
    tempo(session)
    session.play_take()
    first = session.ask("learning.status")["current_fingerprint"]
    other = write_midi(session.music/"other.mid", bars=1, bpm=100)
    session.ask("library.open", id=other.name)
    tempo(session)
    session.play_take()
    second = session.ask("learning.status")["current_fingerprint"]
    assert first != second
    first_ids = session.ask("learning.statistics", fingerprint=first)["query"]["attempt_ids"]
    second_ids = session.ask("learning.statistics", fingerprint=second)["query"]["attempt_ids"]
    assert first_ids and second_ids and not set(first_ids) & set(second_ids)
    session.command("reset_path", fingerprint=second, confirm=True)
    assert session.snapshot()["lesson_step"] == 1
    assert session.ask("learning.statistics", fingerprint=second)["query"]["attempt_ids"] == second_ids
    before = session.ask("learning.status")
    for operation, payload in (("learning.delete_piece", {"fingerprint": first, "confirm": True}),
                               ("learning.delete_piece", {"fingerprint": second}),
                               ("learning.delete_learner", {})):
        assert session.commands.request(operation, json.dumps(payload))[0] == INVALID
    assert session.ask("learning.status")["attempt_count"] == before["attempt_count"]
    session.ask("learning.delete_piece", fingerprint=second, confirm=True)
    assert session.ask("learning.statistics", fingerprint=second)["attempts"]["count"] == 0
    assert session.ask("learning.statistics", fingerprint=first)["query"]["attempt_ids"] == first_ids
    old_learner = session.ask("learning.status")["learner_id"]
    session.ask("learning.delete_learner", confirm=True)
    assert session.ask("learning.status")["learner_id"] != old_learner
    assert session.ask("learning.statistics")["attempts"]["count"] == 0
    session.ask("library.open", id=other.name)
    tempo(session)
    session.play_take()
    fresh = session.ask("learning.statistics")
    assert fresh["assessments"]["accepted"] == 1
    assert not set(fresh["query"]["attempt_ids"]) & set(first_ids+second_ids)


def test_mastery_statistics_report_the_actual_two_target_success_rule(practice_session):
    session = practice_session(bars=1)
    assert session.snapshot()["clean_runs_required"] == 2
    tempo(session)
    session.play_take()  # a sparse window already begins at target
    before = session.ask("learning.statistics")
    assert not any(episode["mastered"] for episode in before["mastery"]["episodes"])
    session.play_take()
    assert session.ask("lesson.overview")["steps"][0]["completed"]
    after = session.ask("learning.statistics")
    mastered = [episode for episode in after["mastery"]["episodes"] if episode["mastered"]]
    assert len(mastered) == 1
    assert mastered[0]["hand"] == "right"
    assert mastered[0]["accepted_eligible_target_attempts"] == 2
    assert mastered[0]["required_accepted_runs"] == 2
    assert mastered[0]["criterion_evidence_complete"]


def test_a_damaged_progress_database_is_set_aside_and_the_app_starts(practice_session, tmp_path):
    """A crash mid-write or a full disk can leave progress.db unreadable; the
    app still starts, keeps the damaged file and says so."""
    session = practice_session(bars=2)
    session.close()
    database = session.data/"progress.db"
    for suffix in ("-wal", "-shm"):
        database.with_name(database.name+suffix).unlink(missing_ok=True)
    database.write_bytes(b"\x00not a database\x00"*512)
    session.open()
    kept = list(session.data.glob("progress.db.damaged-*"))
    assert len(kept) == 1 and kept[0].read_bytes().startswith(b"\x00not a database")
    notice = session.ask("library.catalog")["notice"]
    assert notice.startswith("Saved progress could not be read")
    assert kept[0].name in notice
    assert session.snapshot()["screen"]["flash"]["text"] == notice
