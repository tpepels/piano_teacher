"""Strict stationary staff evidence composed from actual independent PNGs.

The full-score audit photographs a fixed native five-line staff while movable
beam/flag/note ink passes over it. A single photographed frame can obscure the
thin-core rail detector, so use multiple *different* source clocks to isolate
the unchanged rails. The current photograph is always intersected again:
reference images cannot authorize a deleted or changed current rail.

All line positions, intensities, staff gaps, source pitch and negative controls
remain subject to the existing strict pixel_proof.detect_staff_lines oracle.
No Godot/native geometry or stored score-layout metadata enters this owner.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .pixel_proof import detect_staff_lines


class PhotographedStaffRails:
    """One verifier call owns one bounded reference (never a global cache)."""

    def __init__(self, folder: Path, *, anchors=(), captured_clocks=None):
        directory = Path(folder)
        if anchors:
            clocks = sorted({float(t) for t in anchors})
            if len(clocks) < 2:
                raise ValueError("Independent rail evidence needs two distinct source clocks")
        else:
            clocks = []
            # A caller that already scanned the capture folder passes its
            # clocks so one verifier call lists the directory exactly once.
            if captured_clocks is not None:
                clocks = list(captured_clocks)
            else:
                for path in directory.glob("native-*.png"):
                    try:
                        clocks.append(float(path.stem.removeprefix("native-")))
                    except ValueError:
                        continue
            clocks = sorted(set(clocks))
            if len(clocks) >= 3:
                clocks = [clocks[0], clocks[len(clocks)//2], clocks[-1]]
        self.reference = None
        if len(clocks) >= 2:
            photos = []
            for clock in clocks:
                with Image.open(directory / f"native-{clock:.5f}.png") as raw:
                    photos.append(np.asarray(raw.convert("RGB"), dtype=np.uint8))
            if len({array.shape for array in photos}) != 1:
                raise ValueError("Staff photographs have different framebuffer dimensions")
            self.reference = np.minimum.reduce(photos)

    def detect(self, image: Image.Image):
        if self.reference is None:
            return detect_staff_lines(image)
        current = np.asarray(image.convert("RGB"), dtype=np.uint8)
        if current.shape != self.reference.shape:
            raise AssertionError("Staff witness dimensions changed")
        return detect_staff_lines(Image.fromarray(np.minimum(self.reference, current)))
