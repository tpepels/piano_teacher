#!/usr/bin/env python3
"""Install the licensed Salamander Grand Piano SF2 outside the Git repository.

Source: FreePats, original recording by Alexander Holm, CC BY 3.0.
A large download is always explicit, never triggered by pressing Listen.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

from piano_teacher.sample_piano import DEFAULT_SOUNDFONT

SOURCE = ("https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/"
          "SalamanderGrandPiano-SF2-V3%2B20200602.tar.xz")
ATTRIBUTION = (
    "Salamander Grand Piano V3, sampled Yamaha C5.\n"
    "Original samples by Alexander Holm. Creative Commons Attribution 3.0 Unported.\n"
    "https://creativecommons.org/licenses/by/3.0/\n"
    "Download: https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html\n"
    "Source: https://archive.org/details/SalamanderGrandPianoV3\n"
)


def _copy_valid_sf2(archive: Path, destination: Path) -> int:
    found = False
    with tarfile.open(archive, mode="r:xz") as package:
        for member in package:
            if not member.isfile() or not member.name.lower().endswith(".sf2"):
                continue
            if found:
                raise ValueError("Archive contains multiple SoundFonts; refusing ambiguous install")
            if not 1024 * 1024 <= member.size <= 2_000_000_000:
                raise ValueError("Invalid piano sample bank size")
            reader = package.extractfile(member)
            if reader is None:
                raise ValueError("Cannot read SoundFont from downloaded archive")
            with reader, destination.open("wb") as output:
                header = reader.read(12)
                if header[:4] != b"RIFF" or header[8:12] != b"sfbk":
                    raise ValueError("Archive does not contain a valid SF2 SoundFont")
                output.write(header)
                shutil.copyfileobj(reader, output, length=2 * 1024 * 1024)
            if destination.stat().st_size != member.size:
                raise ValueError("SoundFont extraction was incomplete")
            found = True
    if not found:
        raise ValueError("No SF2 SoundFont found in downloaded piano samples")
    return destination.stat().st_size


def install(destination: Path, *, source: str = SOURCE, force: bool = False) -> Path:
    destination = destination.expanduser().resolve()
    if destination.is_file() and not force:
        raise FileExistsError(f"Already installed at {destination}; use --force to replace")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".piano-samples-", dir=destination.parent) as tmp:
        archive = Path(tmp) / "download.tar.xz"
        extracted = Path(tmp) / "instrument.sf2"
        print("Downloading CC BY 3.0 Salamander Grand Piano sample library...", flush=True)
        # Stream large archives to disk and never trust archive member paths.
        with urllib.request.urlopen(source, timeout=60) as reply, archive.open("wb") as out:
            shutil.copyfileobj(reply, out, length=2 * 1024 * 1024)
        size = _copy_valid_sf2(archive, extracted)
        os.replace(extracted, destination)
    (destination.parent / "SALAMANDER-ATTRIBUTION.txt").write_text(ATTRIBUTION)
    print(f"Installed {(size / (1024*1024)):.1f} MiB to {destination}", flush=True)
    print("Listen will now use the stereo sampled Yamaha C5 (libfluidsynth required).", flush=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_SOUNDFONT)
    parser.add_argument("--force", action="store_true", help="Replace an installed SoundFont")
    args = parser.parse_args()
    try:
        install(args.destination, force=args.force)
    except (OSError, ValueError, tarfile.TarError) as exc:
        parser.exit(1, f"Sample installation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
