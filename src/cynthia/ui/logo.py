"""The CYNTHIA wordmark — a figlet banner with a per-column pink->blue gradient."""
from __future__ import annotations

import pyfiglet
from rich.text import Text

from . import theme

FONT = "ansi_shadow"


def render_logo() -> Text:
    art = pyfiglet.figlet_format("CYNTHIA", font=FONT)
    lines = art.rstrip("\n").split("\n")
    width = max((len(line) for line in lines), default=1)

    out = Text()
    for line_idx, line in enumerate(lines):
        for col, ch in enumerate(line):
            color = theme.gradient_color(col / max(1, width - 1))
            out.append(ch, style=f"bold {color}")
        if line_idx != len(lines) - 1:
            out.append("\n")
    return out
