"""Launch the native Godot application through the existing product launcher."""
import os
from pathlib import Path
import sys


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    launcher = project / "run.sh"
    if not launcher.is_file() or not (project / "godot/main.gd").is_file():
        raise SystemExit("The native Godot application requires a project checkout "
                         "containing run.sh and godot/main.gd. Use an editable checkout.")
    os.execv(str(launcher), [str(launcher), *sys.argv[1:]])


if __name__ == "__main__":
    main()

