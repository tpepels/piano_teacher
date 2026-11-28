"""Tests use artificial ratings only; no human evidence is generated."""
import importlib.util
from pathlib import Path
import pytest

SPEC = importlib.util.spec_from_file_location("d0_pilot",
    Path(__file__).resolve().parents[1]/"docs/difficulty-research/pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)
PLAN = pilot.load(pilot.HERE/"pilot-plan.json")


def fixture():
    packet = {"plan_digest": pilot.digest(PLAN), "units": [{"unit_id": str(i)} for i in range(40)]}
    packet["packet_id"] = pilot.digest(packet)
    sheets = []
    for r in range(3):
        rows = []
        for i in range(40):
            row = dict(packet_id=packet["packet_id"], unit_id=str(i), rater_id=str(r),
                       rater_background="artificial unit test", judgment_mode="score",
                       severity="0" if i < 20 else "3", confidence="high", evidence="test")
            row.update({c: "absent" if i < 20 else "present" for c in pilot.CATEGORIES})
            rows.append(row)
        sheets.append(rows)
    return packet, sheets


def test_ordinal_alpha_known_extremes():
    assert pilot.ordinal_alpha([[0,0,0],[3,3,3]]) == 1
    assert pilot.ordinal_alpha([[1,1,1],[1,1]]) is None
    assert pilot.ordinal_alpha([[0,3],[0,3]]) == pytest.approx(-0.5)
    assert pilot.ordinal_alpha([[0,0],[3,3,3],[]]) == 1


def test_perfect_artificial_pilot_does_not_certify_d0():
    packet,sheets = fixture()
    result = pilot.agreement(packet,sheets,PLAN)
    assert result["pilot_status"] == "pass"
    assert result["d0_status"].startswith("requires")
    assert result["metrics"]["ordinal_alpha"] == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate_rater", "wrong_packet", "blank"])
def test_invalid_evidence_rejected(fault):
    packet,sheets = fixture()
    if fault == "missing":
        sheets[0].pop()
    elif fault == "duplicate_rater":
        for row in sheets[1]:
            row["rater_id"]="0"
    elif fault == "wrong_packet":
        sheets[0][0]["packet_id"]="stale"
    else:
        sheets[0][0]["severity"]=""
    with pytest.raises(ValueError):
        pilot.agreement(packet,sheets,PLAN)


def test_unknown_and_absent_are_not_equivalent():
    packet,sheets = fixture()
    for sheet in sheets:
        for row in sheet:
            row["severity"]="unknown"
            row.update({c:"unknown" for c in pilot.CATEGORIES})
    result=pilot.agreement(packet,sheets,PLAN)
    assert result["pilot_status"]=="open"
    assert result["metrics"]["ordinal_alpha"] is None
    assert result["metrics"]["severity_coverage"]==0


def test_tampered_packet_rejected():
    packet,sheets=fixture()
    packet["units"][0]["unit_id"]="changed"
    with pytest.raises(ValueError, match="identity"):
        pilot.agreement(packet,sheets,PLAN)



def test_report_retains_exact_evidence_digests():
    packet,sheets=fixture()
    report=pilot.agreement(packet,sheets,PLAN)
    assert report["provenance"]["packet_id"]==packet["packet_id"]
    assert report["provenance"]["plan_digest"]==pilot.digest(PLAN)
    old=report["provenance"]["rating_digests"]
    sheets[0][0]["evidence"]="edited"
    assert pilot.agreement(packet,sheets,PLAN)["provenance"]["rating_digests"]!=old


def test_complete_inventory_review_packet_assessment(tmp_path, monkeypatch):
    """Real MIDI parsing and CSV/JSON round trip, artificial ratings only."""
    import hashlib
    import mido
    monkeypatch.setattr(pilot,"ROOT",tmp_path)
    midi=mido.MidiFile(ticks_per_beat=480)
    track=mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo",tempo=500000,time=0))
    for i in range(40):
        track.append(mido.Message("note_on",note=60+i%2,velocity=64,time=0))
        track.append(mido.Message("note_off",note=60+i%2,time=120))
    path=tmp_path/"pilot.mid"
    midi.save(path)
    raw=path.read_bytes()
    blob=hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
    corpus={"repertoire":[{"path":"pilot.mid","git_blob":blob,"ppq":480,
        "windows":[{"id":"real","start_tick":0,"end_tick":4800,
                    "context_before_ticks":1920,"context_after_ticks":1920}]}],
        "synthetic":[]}
    plan=dict(PLAN,source_windows=["real"],synthetic=[],hands=["R"],tempo_factors=[1])
    inventory,maps=pilot.inventory(corpus,plan)
    assert len(inventory)==40 and maps["real"]["ppq"]==480
    assert all(row["hand"]=="" for row in inventory)
    review=[dict(row, hand="R",finger="1",fingering_provenance="teacher",
                 edition="test fixture",reviewer="artificial",measure="1",voice="1")
            for row in inventory]
    review_path=tmp_path/"review.csv"
    pilot.write_csv(review_path,pilot.REVIEW_FIELDS,review)
    reviewed=pilot.checked_review(inventory,pilot.read_csv(review_path))
    directory=tmp_path/"packet"
    packet=pilot.make_packet(corpus,plan,reviewed,maps,directory)
    assert len(packet["units"])==40
    assert packet["corpus_digest"]==pilot.digest(corpus)
    assert packet["source_review_digest"]==pilot.digest(reviewed)
    for r in range(1,4):
        path=directory/f"ratings-{r}.csv"
        rows=pilot.read_csv(path)
        for i,row in enumerate(rows):
            row.update(rater_id=str(r),rater_background="artificial test",
                       judgment_mode="score",severity="0" if i<20 else "3",
                       confidence="high",evidence="artificial test")
            row.update({c:"absent" if i<20 else "present" for c in pilot.CATEGORIES})
        pilot.write_csv(path,pilot.RATING_FIELDS,rows)
    loaded=pilot.load(directory/"packet.json")
    sheets=[pilot.read_csv(directory/f"ratings-{r}.csv") for r in range(1,4)]
    result=pilot.agreement(loaded,sheets,plan,corpus=corpus)
    assert result["pilot_status"]=="pass"
    assert result["provenance"]["packet_id"]==packet["packet_id"]
    assert result["provenance"]["source_review_digest"]==pilot.digest(reviewed)
    with pytest.raises(ValueError,match="different frozen corpus"):
        pilot.agreement(loaded,sheets,plan,corpus=dict(corpus,version=2))
    review[0]["pitch"]=99
    pilot.write_csv(review_path,pilot.REVIEW_FIELDS,review)
    with pytest.raises(ValueError,match="Changed source facts"):
        pilot.checked_review(inventory,pilot.read_csv(review_path))
