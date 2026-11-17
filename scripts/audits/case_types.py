"""Serializable case identity shared by the public CLI and spawned workers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditCase:
    name: str
    filename: str
    first_bar: int
    last_bar: int
    hand: str = "both"
    max_density: float = 640.0
    max_tiny_rests: int = 8
    max_dots: int = 2
    features: tuple[str, ...] = ()
    min_lookahead_beats: float = 0.0
    # Logical score area and the window's UI scale (main.gd
    # _configure_ui_scaling). The default is the historical 1536x520 at 1.0;
    # (1358, 611) at 1.35 is the practice score on a 1920x1080 screen.
    viewport: tuple[int, int] = (1536, 520)
    ui_scale: float = 1.0



DEFAULT_DISPLAY = {"viewport": (1536, 520), "ui_scale": 1.0}


def case_fields(case: AuditCase) -> dict:
    """Serialized identity; the display fields appear only when not default.

    Captures recorded before the display fields existed keep their identity.
    """
    from dataclasses import asdict
    row = asdict(case)
    for key, default in DEFAULT_DISPLAY.items():
        if tuple(row[key]) == default if isinstance(default, tuple) else row[key] == default:
            row.pop(key)
    return row
