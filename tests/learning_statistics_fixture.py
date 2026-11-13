"""Finite canonical-ledger fixture shared by resource/native analytics gates."""
from piano_teacher.progress_repository import ProgressRepository


def populate(path, count=5000, notes=24, fingerprint="fixture-source"):
    repository = ProgressRepository(path)
    ledger = repository.ledger
    ledger.start_session("measured-session", "measured-run", "2026-01-01T00:00:00Z", "UTC")
    rule = ledger.store_rules({"mastery": "accepted-full-target-v1", "lesson_settings": {"clean_runs_to_master": 3}})
    observations = [{"source_id": f"note-{n}", "source_beat": n/4, "source_measure": n//16+1,
                     "onset_group_id": f"onset-{n//2}", "authored_hand": "right", "omitted": False,
                     "status": "late" if n % 5 == 0 else "correct", "pitch_error": False,
                     "onset_residual": n*.001-.01, "duration_residual": -.02,
                     "local_seconds_per_beat": .5, "release_residual": -.01} for n in range(notes)]
    for i in range(count):
        identity = f"fixture-{i}"
        ledger.start_attempt(identity, "measured-session", {
            "fingerprint": fingerprint, "stage_key": f"stage-{i%5}", "rule_id": rule,
            "hand": "right", "scope": "full", "assistance": False,
            "from_beat": 0, "end_beat": notes/4, "performed_bpm": 60+(i%3)*30, "target_bpm": 120,
            "monotonic_start": i*10, "started_utc": "2026-01-01T00:00:01Z"})
        ledger.settle_attempt(identity, {"state": "completed", "reason": "deadline", "monotonic_end": i*10+6,
            "assistance_used": False, "assessment": {"bpm": 60+(i%3)*30,
                "statuses": [o["status"] for o in observations], "extra_notes": 0,
                "passed": True, "clean": False, "mastery_eligible": True}, "observations": observations})
    ledger.record_event("measured-session", "phase_intervals", {"intervals": [
        {"phase": "active", "start": 0, "end": count*10}]})
    ledger.close_session("measured-session", "shutdown")
    repository.close()
