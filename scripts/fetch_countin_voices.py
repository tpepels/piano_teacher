#!/usr/bin/env python3
"""Install four public-domain Japanese spoken-count-in clips.

The release bundles the resulting .ogg files. This installer is only used
for maintaining that bundle, never on the playback or game startup path.
Downloads respect Wikimedia throttling and are atomic per file.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DESTINATION = Path(__file__).resolve().parent.parent / "godot" / "assets" / "countin"
SOURCE = "https://upload.wikimedia.org/wikipedia/commons/"
SAMPLES = {
    "ichi": "7/7f/Ja-1-ichi.ogg",
    "ni": "3/3c/Ja-2-ni.ogg",
    "san": "8/83/Ja-3-san.ogg",
    "shi": "b/bf/Ja-4-shi_counting.ogg",
}
MAX_BYTES = 256 * 1024
MIN_BYTES = 2_000
MAX_RETRIES = 7


def valid_ogg(path: Path) -> bool:
    if not path.is_file() or not (MIN_BYTES <= path.stat().st_size <= MAX_BYTES):
        return False
    with path.open("rb") as audio:
        return audio.read(4) == b"OggS"


def _fetch_one(url: str) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "PianoTeacherAudioBundle/1.0 (open-source educational piano practice; admin via repository issues)",
            "Accept": "audio/ogg",
        },
    )
    with urlopen(req, timeout=12) as response:
        data = response.read(MAX_BYTES + 1)
    if not (MIN_BYTES <= len(data) <= MAX_BYTES and data.startswith(b"OggS")):
        raise ValueError("unexpected response; not a valid Ogg Vorbis recording")
    return data


def fetch_samples(*, offline: bool = False, sleep=time.sleep) -> bool:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    downloads = 0
    all_ok = True
    for name, filename in SAMPLES.items():
        output = DESTINATION / (name + ".ogg")
        if valid_ogg(output):
            continue
        if offline:
            print(f"count-in voice missing: {output}")
            all_ok = False
            continue
        if downloads:
            # Wikimedia blocks quick bursts even for these tiny 10KB files.
            sleep(4.0)
        downloads += 1
        url = SOURCE + filename
        for attempt in range(MAX_RETRIES):
            try:
                data = _fetch_one(url)
                tmp = output.with_suffix(".ogg.part")
                tmp.write_bytes(data)
                os.replace(tmp, output)
                print(f"Cached Japanese count-in voice: {name}")
                break
            except (HTTPError, URLError, OSError, ValueError) as error:
                if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                    print(f"Permanent download failure for {name}: {error}")
                    all_ok = False
                    break
                if attempt + 1 == MAX_RETRIES:
                    print(f"Voice download failed after retries for {name}: {error}")
                    all_ok = False
                    break
                # Bounded exponential backoff: never retry immediately
                # after Wikimedia's 429 throttling response.
                backoff = min(45.0, 5.0 * (2 ** attempt))
                if isinstance(error, HTTPError):
                    retry_after = error.headers.get("Retry-After")
                    if retry_after and retry_after.isdecimal():
                        backoff = max(backoff, min(60.0, float(retry_after)))
                print(f"Voice download {name} throttled ({error}); retrying after {backoff:g}s", flush=True)
                sleep(backoff)
    return all_ok and all(valid_ogg(DESTINATION / f"{name}.ogg") for name in SAMPLES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="Validate all bundled recordings without network access")
    args = parser.parse_args()
    raise SystemExit(0 if fetch_samples(offline=args.verify) else 1)
