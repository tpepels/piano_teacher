"""Extract complete untimed grace groups relative to the principal notehead."""
from xml.etree import ElementTree as ET

from ...source_svg import isolate_elements, parse_svg_geometry
from .vector_art import local_vector_art


def grace_fragments(pages, model):
    pending = {item["before_note_id"]: item
               for item in model.get("grace_notes", ()) if item.get("group_ids")}
    fragments = {}
    for page in pages:
        if not pending:
            break
        root = ET.fromstring(page)
        by_id = {node.get("id"): node for node in root.iter() if node.get("id")}
        groups = {key: item for key, item in pending.items()
                  if key in by_id and all(identifier in by_id for identifier in item["group_ids"])}
        if not groups:
            continue
        ledgers = {}
        geometry = parse_svg_geometry(root, ledger_paths=ledgers)
        parents = {child: parent for parent in root.iter() for child in parent}
        for node in root.iter():
            if node.get("opacity") == "0.48":
                del node.attrib["opacity"]
        for anchor, item in groups.items():
            ids = item["group_ids"]
            x, y, system = geometry.elements[anchor]
            selected = {by_id[slur] for slur in item["slur_ids"]}
            for identifier in ids:
                node = by_id[identifier]
                parent = parents[node]
                # A beam includes its stems, every pitch and accidental.
                # Include it only when the beam belongs entirely to the ornament.
                while parent.get("class") in ("beam", "chord"):
                    members = [child.get("id") for child in parent.iter()
                               if child.get("class") == "note"]
                    if not all(member in ids for member in members):
                        break
                    node = parent
                    parent = parents[node]
                selected.add(node)
                selected.update(ledgers.get(identifier, ()))
            lines = geometry.staff_systems[system]["staff_lines"]
            fragment = local_vector_art(isolate_elements(root, selected), lines[1]-lines[0],
                                        (x, y), "verovio-engraved-graces")
            if fragment:
                fragments[anchor] = fragment
                del pending[anchor]
    if pending:
        raise ValueError("Missing Verovio grace group before " + ", ".join(pending))
    return fragments
