"""Fail-closed composition of independent source obligations and bound evidence.

This coordinator owns window selection, occurrence consumption and acceptance
ordering. XML agreement supplies correspondence, never visual proof."""
from __future__ import annotations

from collections import Counter
from .visual_binding import match_generated_events, measured_records
from .visual_contract import STATUSES
from .visual_curves import apply_connectors
from .visual_groups import apply_group_connectors
from .visual_inventory import read_visual_inventory, source_inventory
from .visual_ledgers import apply_ledgers
from .visual_notes import apply_note_features
from .visual_presence import pixel_status
from .visual_rests import apply_rest_evidence
from .visual_tuplets import apply_tuplet_semantics


__all__ = ("visual_elements", "source_inventory", "coverage_counts")


def visual_elements(original_xml: str | None, generated_xml: str, pitch_report: dict,
                    rest_report: dict, *, hand='both', first_bar=1,
                    last_bar=None, source_name='', feature_report: dict | None = None,
                    connector_report: dict | None = None, beam_report: dict | None = None,
                    tuplet_report: dict | None = None, ledger_report: dict | None = None,
                    semantic_report: dict | None = None) -> list[dict]:
    """Build a per-construct ledger for a generated source window.

    ``first_bar``/``last_bar`` are inclusive original measure *indices*, not
    MusicXML measure labels. Omitted ``last_bar`` uses generated window length.
    Original beats stay absolute in source bindings; generated clocks start at
    zero. Source/generated voice labels may normalize; each occurrence and
    measurement is consumed at most once. No report totals prove an element.
    Optional ``feature_report`` is from ``verify_note_feature_pixels`` on the
    exact captured ``generated_xml``. Omission preserves legacy feature statuses.
    Bound stem/flag/dot evidence may combine with the independent head record
    into rhythm evidence. Optional beam/tuplet reports also require complete
    ordered source groups, graphical witnesses and exact duration arithmetic.
    Optional ``connector_report`` supplies per-pair tie/slur observations;
    aggregate status never authorizes an original endpoint obligation.
    Optional ``ledger_report`` proves every source-required ledger step for
    each inventoried note, independently of the ordinary feature counts.
    ``semantic_report`` is a per-event generated/native contract. Deliberately
    hidden complete tuplet groups have semantic scope, never pixel evidence.
    """
    if isinstance(first_bar, bool) or not isinstance(first_bar, int) or first_bar < 1:
        raise ValueError("first_bar must be a positive measure index")
    generated = read_visual_inventory(generated_xml, hand, "generated", source_name if original_xml is None else "")
    if last_bar is None:
        last_bar = first_bar + generated.measure_count - 1
    if isinstance(last_bar, bool) or not isinstance(last_bar, int) or last_bar < first_bar:
        raise ValueError("last_bar must be an inclusive index at or after first_bar")
    original = read_visual_inventory(original_xml, hand, "original") if original_xml is not None else generated
    start, end = (first_bar, last_bar) if original_xml is not None else (1, generated.measure_count)
    offset = original.bars[start-1] if original.bars and start <= original.measure_count else 0
    output = [dict(row) for row in original.elements
              if start <= row["source"].get("measure_index", start) <= end]
    expected = {path: event for path, event in original.events.items()
                if start <= event["measure_index"] <= end}
    matched, used_generated = match_generated_events(expected, generated.events, offset)
    measurements = {"note": measured_records(pitch_report), "rest": measured_records(rest_report)}
    used_pixels = {"note": set(), "rest": set()}
    for row in output:
        if row["construct"] not in {"pitch", "rest"}:
            continue
        event = expected[row["source"]["xml_ordinal"]]
        if not event["timing_supported"]:
            row.update(status="unsupported", reason="Independent XML timing reader does not support this event")
            continue
        match = matched.get(event["xml_ordinal"])
        if match is None:
            row.update(status="unverified" if generated.reader_error else "mismatch",
                       reason="Generated XML timing cannot establish correspondence: " + generated.reader_error
                              if generated.reader_error else "Original visible event missing or changed in generated window")
            continue
        if event["kind"] == "rest" and match["note_type"] != event["note_type"]:
            row.update(status="mismatch", reason="Generated rest type differs from original written rest")
            continue
        status, reason, evidence = pixel_status(match, measurements[event["kind"]], used_pixels[event["kind"]])
        row.update(status=status, reason=reason,
                   evidence=dict(generated={key: match[key] for key in
                       ("id", "measure", "staff", "voice", "beat", "spelling", "note_type")},
                       pixel=evidence))
    apply_rest_evidence(output, expected, matched)
    if feature_report is not None:
        apply_note_features(output, expected, matched, generated, feature_report)
    if connector_report is not None:
        apply_connectors(output, original, matched, generated, connector_report)
    if beam_report is not None or tuplet_report is not None:
        apply_group_connectors(output, original, matched, generated, original_xml, generated_xml,
                                {"beam": beam_report, "tuplet": tuplet_report})
    if ledger_report is not None:
        apply_ledgers(output, expected, matched, generated, ledger_report)
    apply_tuplet_semantics(output, original, expected, matched, generated, original_xml, generated_xml,
                            semantic_report, feature_report)
    if original_xml is not None:
        authored_hands = {event["staff"] for event in original.events.values()}
        for path, event in generated.events.items():
            if path in used_generated:
                continue
            source = dict({k: v for k, v in event.items() if not k.startswith("_")}, origin="generated_extra")
            source.pop("timing_supported")
            source.pop("xml_id")
            scaffolding = event["kind"] == "rest" and event["staff"] not in authored_hands
            unsupported = scaffolding or not event["timing_supported"]
            output.append(dict(id=f"generated-extra:w{first_bar}-{last_bar}:{path}",
                               construct="staff_scaffolding" if scaffolding else
                                         "generated_event" if not event["timing_supported"] else
                                         "rest" if event["kind"] == "rest" else "pitch",
                               status="unsupported" if unsupported else "mismatch", source=source,
                               reason="Blank-hand rest scaffolding has no authored counterpart; its contour does not certify source notation"
                                      if scaffolding else "Independent timing reader cannot establish a source counterpart"
                                      if not event["timing_supported"] else "Generated visible event has no original source counterpart"))
    else:
        # Generated ordinals restart in every MIDI window. Namespace every row
        # while preserving the label and local generated source bindings.
        for row in output:
            row["id"] = f"w{first_bar}-{last_bar}:" + row["id"]
        output.append(dict(id=f"w{first_bar}-{last_bar}:midi-written-transcription",
                           construct="midi_written_transcription", status="unsupported",
                           source=dict(id="midi-written-transcription", source_name=source_name,
                                       origin="midi", measure=first_bar, staff=hand),
                           reason="MIDI has no unique original written score; this ledger covers only the generated written transcription"))
    return output


def coverage_counts(elements: list[dict]) -> dict:
    """Aggregator schema: every row contributes to exactly one status."""
    counts = Counter(row["status"] for row in elements)
    unknown = counts.keys() - STATUSES
    if unknown:
        raise ValueError(f"Unknown coverage statuses: {sorted(unknown)}")
    return dict(expected=len(elements), **{status: counts[status] for status in STATUSES})
