"""Verovio runtime and bundled font resources shared by native and legacy paths."""
from __future__ import annotations
import json
from pathlib import Path

def _verovio_resources(verovio_module) -> Path:
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


def _create_verovio_toolkit(verovio_module):
    """Load the bundled fonts explicitly before importing or engraving music."""
    resources = _verovio_resources(verovio_module)
    # Avoid the default font path baked into some wheels at build time.
    toolkit = verovio_module.toolkit(False)
    if not toolkit.setResourcePath(str(resources)):
        raise RuntimeError(f"Verovio could not load its Bravura/Leipzig fonts from {resources}")
    return toolkit


def _verovio_object(value, description: str):
    """Accept native Python results from the 5.x binding or older JSON strings."""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Verovio returned invalid {description}") from exc
    raise ValueError(f"Verovio returned unexpected {description} type: {type(value).__name__}")


