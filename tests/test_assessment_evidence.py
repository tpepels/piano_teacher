"""Only actual graded note evidence reaches the adaptive history writer."""
from types import SimpleNamespace

from piano_teacher.application import assessment_evidence as module


def test_valid_graded_take_uses_original_stage_identity_and_bpm(monkeypatch):
    captured = []
    def make_evidence(stage, result, bpm):
        captured.append(("build", stage, result, bpm))
        return {"stage": stage, "bpm": bpm}
    monkeypatch.setattr(module.AssessmentEvidence, "from_result", make_evidence)
    def observe(fingerprint, evidence):
        captured.append(("observe", fingerprint, evidence))
        return "remediate"
    result = SimpleNamespace(notes=[SimpleNamespace(status="wrong")])
    recommendation = module.observe_assessed_take(
        fingerprint="piece", stage_key="rh-original", bpm=72,
        result=result, observe=observe)
    assert recommendation == "remediate"
    assert captured == [
        ("build", "rh-original", result, 72),
        ("observe", "piece", {"stage": "rh-original", "bpm": 72}),
    ]


def test_no_fingerprint_or_ungraded_records_do_not_persist():
    def forbidden(*args):
        raise AssertionError("ungraded results cannot be stored")
    for fingerprint, result in [
        ("", SimpleNamespace(notes=[SimpleNamespace(status="correct")])),
        ("piece", SimpleNamespace(notes=[])),
        ("piece", SimpleNamespace(notes=[object()])),
        ("piece", SimpleNamespace()),
    ]:
        assert module.observe_assessed_take(
            fingerprint=fingerprint, stage_key="original",
            bpm=60, result=result, observe=forbidden) is None
