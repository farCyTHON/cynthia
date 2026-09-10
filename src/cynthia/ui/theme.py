"""Theme — the Gemini-inspired pink -> purple -> blue palette used everywhere.

Centralized so every screen (welcome, dashboard, help) shares one visual
identity instead of each module picking its own colors.
"""
from __future__ import annotations

# Gradient stops, pink through purple to cyan-blue.
GRADIENT = ["#ff4f9e", "#e34fd0", "#b455f5", "#8a63f7", "#5f8ff7", "#3cb4f0", "#22d3ee"]

PRIMARY = "#b455f5"
ACCENT = "#22d3ee"
MUTED = "#7d7d95"
DIM = "grey50"

TEXT = "#e6e6f0"
SUBTEXT = "#9a9ab0"

SUCCESS = "#3ce68c"
WARNING = "#f5c542"
CRITICAL = "#ff5c72"

STATUS_COLOR = {"healthy": SUCCESS, "warning": WARNING, "critical": CRITICAL}

# Distinct colors for the commit-type dot in history views, cycling by index.
COMMIT_DOTS = ["#b455f5", "#3cb4f0", "#22d3ee", "#ff4f9e", "#f5c542"]


def gradient_color(position: float) -> str:
    """Interpolate a hex color along GRADIENT for position in [0, 1]."""
    position = max(0.0, min(1.0, position))
    scaled = position * (len(GRADIENT) - 1)
    idx = int(scaled)
    if idx >= len(GRADIENT) - 1:
        return GRADIENT[-1]
    frac = scaled - idx
    return _lerp_hex(GRADIENT[idx], GRADIENT[idx + 1], frac)


def _lerp_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"
