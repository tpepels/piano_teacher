"""One Verovio runtime and bundled music fonts for native engraving."""
from __future__ import annotations
from copy import deepcopy
import json
from xml.etree import ElementTree as ET
from pathlib import Path

def verovio_resources(verovio_module) -> Path:
    """Resolve fonts next to the installed Python module, not a build-time path.

    The Verovio Python wheel includes Bravura and Leipzig in verovio/data.
    """
    module_file = getattr(verovio_module, "__file__", None)
    if not module_file:
        raise RuntimeError("Verovio installation has no module location; cannot find its music fonts")
    path = Path(module_file).resolve().parent / "data"
    missing = [name for name in ("Bravura.xml", "Leipzig.xml") if not (path / name).is_file()]
    if missing:
        raise RuntimeError(
            f"Verovio music fonts are missing from {path}: {', '.join(missing)}. "
            "Reinstall the complete Python wheel with "
            "python -m pip install --force-reinstall --no-cache-dir 'verovio>=5,<6'"
        )
    return path


def create_verovio_toolkit(verovio_module):
    """Load the bundled fonts explicitly before importing or engraving music."""
    resources = verovio_resources(verovio_module)
    # Avoid the default font path baked into some wheels at build time.
    toolkit = verovio_module.toolkit(False)
    if not toolkit.setResourcePath(str(resources)):
        raise RuntimeError(f"Verovio could not load its Bravura/Leipzig fonts from {resources}")
    return toolkit


def unbroken_toolkit():
    import verovio

    toolkit = create_verovio_toolkit(verovio)
    if not toolkit.setOptions({"inputFrom": "xml", "breaks": "none", "svgViewBox": True,
                               "adjustPageHeight": True, "adjustPageWidth": True}):
        raise RuntimeError("Verovio rejected continuous excerpt engraving options")
    return toolkit


def measure_excerpt(root, part, start, end):
    """Copy a single part's measures with its inherited written context."""
    subset = ET.Element("score-partwise", version="4.0")
    part_list = ET.SubElement(subset, "part-list")
    info = root.find(f"part-list/score-part[@id='{part.get('id')}']")
    part_list.append(deepcopy(info))
    excerpt = ET.SubElement(subset, "part", id=part.get("id"))
    measures = part.findall("measure")
    context = {}
    for measure in measures[:start]:
        for attr in measure.findall("attributes/*"):
            context[attr.tag, attr.get("number")] = attr
    excerpt.extend(deepcopy(measure) for measure in measures[start:end + 1])
    if context:
        inherited = ET.Element("attributes")
        inherited.extend(deepcopy(attr) for attr in context.values())
        excerpt[0].insert(0, inherited)
    return subset


def verovio_object(value, description: str):
    """Accept native Python results from the 5.x binding or older JSON strings."""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Verovio returned invalid {description}") from exc
    raise ValueError(f"Verovio returned unexpected {description} type: {type(value).__name__}")


