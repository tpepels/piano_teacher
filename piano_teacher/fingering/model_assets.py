"""Integrity checks for the unmodified Lumikey 0.3.0 models."""

from hashlib import sha256
from pathlib import Path

ONNX_RUNTIME_VERSION = "1.30.0"
MODEL_HASHES = {
    "left": "246f2fed013c27ca8c32ce9d070002afcc49da4f1dfb0c43e09a4a3f9f2fb86e",
    "right": "f931288302b87f5eec1c8af29a570ee0213a272a13eeb590991a285e1f1b67eb",
}


def verified_model_bytes(path: Path, hand: str) -> bytes:
    weights = path.read_bytes()
    if sha256(weights).hexdigest() != MODEL_HASHES[hand]:
        raise ValueError(f"Unexpected model weights: {hand}")
    return weights
