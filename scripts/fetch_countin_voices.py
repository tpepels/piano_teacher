#!/usr/bin/env python3
"""Fetch the four public-domain Japanese count-in words once for offline use.

The launcher calls this before Godot starts importing OGG resources. The game
never makes network requests or waits for a download during a practice session.
Run with --verify to check the four cached files without network access.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.request import Request, urlopen

DESTINATION = Path(__file__).resolve().parent.parent / "godot" / "assets" / "countin"
SOURCE = "https://commons.wikimedia.org/wiki/Special:Redirect/file/"
SAMPLES = {
    "ichi": "Ja-1-ichi.ogg",
    "ni": "Ja-2-ni.ogg",
    "san": "Ja-3-san.ogg",
    "shi": "Ja-4-shi_counting.ogg",
}
MAX_BYTES = 256 * 1024


def valid_ogg(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as audio:
        return audio.read(4) == b"OggS" and path.stat().st_size >= 2_000


def fetch_samples(*, offline: bool = False) -> bool:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, filename in SAMPLES.items():
        output = DESTINATION / (name + ".ogg")
        if valid_ogg(output):
            continue
        if offline:
            print(f"count-in voice missing: {output}")
            return False
        request = Request(
            SOURCE + filename,
            headers={"User-Agent": "PianoTeacher/1.0 (public-domain voice asset installer)"},
        )
        try:
            with urlopen(request, timeout=6) as response:
                data = response.read(MAX_BYTES + 1)
            if len(data) < 2_000 or len(data) > MAX_BYTES or not data.startswith(b"OggS"):
                raise ValueError("invalid or oversized Ogg Vorbis response")
            temp = output.with_suffix(".ogg.part")
            temp.write_bytes(data)
            os.replace(temp, output)
            print(f"Cached Japanese count-in voice: {name}")
        except (OSError, ValueError) as error:
            print(f"Spoken count-in unavailable ({name}): {error}")
            print("Metronome fallback remains available; retry next launch.")
            return False
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="Check cached audio without accessing the network")
    args = parser.parse_args()
    raise SystemExit(0 if fetch_samples(offline=args.verify) else 1)
