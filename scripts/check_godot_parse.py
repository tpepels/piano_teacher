#!/usr/bin/env python3
"""Bounded Godot parsing that treats diagnostics as failures, even after exit 0."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default=shutil.which('godot') or shutil.which('godot4'))
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1]/'godot')
    parser.add_argument('--script', default='res://main.gd')
    parser.add_argument('--timeout', type=float, default=25)
    args = parser.parse_args()
    if not args.godot or args.timeout <= 0:
        parser.error('Godot executable and positive timeout are required')
    try:
        result = subprocess.run([args.godot, '--headless', '--path', str(args.project),
                                 '--check-only', '--script', args.script],
                                capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(f'Godot parse timed out after {args.timeout:g}s', file=sys.stderr)
        return 124
    except OSError as exc:
        print(f'Cannot run Godot parse: {exc}', file=sys.stderr)
        return 127
    output = result.stdout+result.stderr
    print(output, end='')
    diagnostics = ('SCRIPT ERROR:', 'Parse Error:', 'ERROR:')
    if result.returncode:
        return result.returncode if result.returncode > 0 else 128-result.returncode
    return int(any(marker in output for marker in diagnostics))


if __name__ == '__main__':
    raise SystemExit(main())
