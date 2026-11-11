"""Contact sheets of R1 captures for visual review.

Usage: .venv/bin/python tests/readiness/preview.py <run dir> <out.png> <shot glob>... [--full] [--width N]
Crops each capture to the notation stage (from its JSON sidecar), labels it
with its file name and stacks them vertically.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    full = "--full" in sys.argv
    width = 1280
    for a in sys.argv:
        if a.startswith("--width="):
            width = int(a.split("=")[1])
    run, out, patterns = Path(args[0]), Path(args[1]), args[2:]
    shots = []
    for pattern in patterns:
        shots.extend(sorted((run / "shots").glob(pattern)))
    tiles = []
    for png in shots:
        side = json.loads(png.with_suffix(".json").read_text())
        image = Image.open(png).convert("RGB")
        scale = float(side.get("scale", 1.0))
        ox, oy = side.get("offset", [0, 0])
        if full:
            crop = image
        else:
            rx, ry, rw, rh = side["renderer_rect"]
            crop = image.crop((int(ox), int((ry - 4) * scale + oy), image.width,
                               int((ry + rh + 50) * scale + oy)))
        crop = crop.resize((width, max(1, int(crop.height * width / crop.width))))
        draw = ImageDraw.Draw(crop)
        label = f"{png.name}  tb={side.get('tb', 0):.2f} phase={side.get('phase')} engine={side['state'].get('phase')}"
        draw.rectangle((0, 0, 9 * len(label), 16), fill=(0, 0, 0))
        draw.text((3, 2), label, fill=(255, 255, 0))
        tiles.append(crop)
    if not tiles:
        print("no shots")
        return
    sheet = Image.new("RGB", (width, sum(t.height for t in tiles)), (40, 40, 40))
    y = 0
    for tile in tiles:
        sheet.paste(tile, (0, y))
        y += tile.height
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
