"""One request to the offline Lumikey ONNX worker."""

import json
import sys
from pathlib import Path

from ..python_worker import exit_on_parent_death


def main():
    exit_on_parent_death(int(sys.argv[1]))
    # Start supervising parent death before loading the ONNX runtime.
    from .inference import predict_assignments

    models = Path(__file__).with_name("models")
    model_paths = {hand: models / f"fingering_transformer_{hand}.onnx"
                   for hand in ("left", "right")}
    request = json.load(sys.stdin)
    assignments = predict_assignments(request["notes"], model_paths)
    json.dump({"assignments": assignments}, sys.stdout)
