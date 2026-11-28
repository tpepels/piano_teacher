"""Extract complete untimed grace groups relative to the principal notehead."""
from xml.etree import ElementTree as ET

from ...source_svg import isolate_elements, parse_svg_geometry
from .vector_art import local_vector_art


def grace_fragments(pages, model, musicxml):
    pending = {item["before_note_id"]: item
               for item in model.get("grace_notes", ()) if item.get("group_ids")}
    fragments = _page_fragments(pages, pending)
    if pending:
        from .runtime import measure_excerpt, unbroken_toolkit

        # A printed system or page break can separate an ornament from
        # its slur contour. Re-engrave only that exact authored measure.
        root = ET.fromstring(musicxml)
        toolkit = unbroken_toolkit()
        for part in root.findall("part"):
            for index, measure in enumerate(part.findall("measure")):
                if not any(note.get("id") in pending for note in measure.findall("note")):
                    continue
                subset = measure_excerpt(root, part, index, index)
                if toolkit.loadData(ET.tostring(subset, encoding="unicode")):
                    fragments.update(_page_fragments([toolkit.renderToSVG(1)], pending))
    if pending:
        raise ValueError("Missing Verovio grace ink before " + ", ".join(pending))
    return fragments


def _page_fragments(pages, pending):
    fragments = {}
    for page in pages:
        if not pending:
            break
        root = ET.fromstring(page)
        by_id = {node.get("id"): node for node in root.iter() if node.get("id")}
        groups = {key: item for key, item in pending.items()
                  if key in by_id and all(identifier in by_id for identifier in
                                          (*item["group_ids"], *item["slur_ids"]))}
        if not groups:
            continue
        ledgers = {identifier: [] for item in groups.values() for identifier in item["group_ids"]}
        geometry = parse_svg_geometry(root, ledger_paths=ledgers)
        parents = {child: parent for parent in root.iter() for child in parent}
        for node in root.iter():
            if node.get("opacity") == "0.48":
                del node.attrib["opacity"]
        for anchor, item in groups.items():
            ids = item["group_ids"]
            if anchor not in geometry.elements:
                continue
            x, y, system = geometry.elements[anchor]
            if not all(identifier in geometry.elements and geometry.elements[identifier][2] == system
                       for identifier in ids):
                continue
            selected = {by_id[slur] for slur in item["slur_ids"]}
            if not all(_slur_on_system(node, parents, system) for node in selected):
                continue
            selected.update(_ornament_nodes(ids, by_id, parents, ledgers))
            lines = geometry.staff_systems[system]["staff_lines"]
            fragment = local_vector_art(isolate_elements(root, selected), lines[1]-lines[0],
                                        (x, y), "verovio-engraved-graces")
            if fragment:
                fragments[anchor] = fragment
                del pending[anchor]
    return fragments


def _ornament_nodes(ids, by_id, parents, ledgers):
    selected = set()
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
    return selected


def _slur_on_system(node, parents, system):
    if not any(child.get("d") for child in node.iter()):
        return False
    while node in parents:
        node = parents[node]
        if node.get("class") == "system":
            return node.get("id") == system
    return False
