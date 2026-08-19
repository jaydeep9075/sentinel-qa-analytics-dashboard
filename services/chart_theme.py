"""
chart_theme.py — the single source of truth for chart colour.

Why this file exists
--------------------
The previous palette (#6C8BFF / #22C55E / #F59E0B / #EF4444 / …) FAILS
colourblind separation: under protanopia #F59E0B and #22C55E sit at ΔE 5.7,
well under the ΔE 8 floor, so an amber bar and a green bar were literally the
same colour for a chunk of readers. Three of its hues also sat under 3:1
contrast on a light surface with no compensating labels.

The palette below is validated in BOTH modes (worst adjacent CVD ΔE 9.1 light /
8.4 dark; worst adjacent normal-vision ΔE 19.6 / 19.3). Everything else here
exists so a figure can be re-themed on the client without re-rendering:
`fig.layout.meta.sentinel` carries the dark variants and a per-trace slot map,
so the frontend swaps colours on a theme toggle instead of the backend guessing
which theme the viewer is in at generation time.

Rules encoded here (from the data-viz method):
  • categorical hues are assigned in FIXED slot order and never cycled — a 9th
    series folds into "Other", it does not get a generated hue;
  • colour follows the entity, never its rank;
  • sequential = one hue light→dark, never a rainbow;
  • status colours (good/warning/serious/critical) are reserved and never
    reused as "series 4".
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Categorical — fixed slot order, validated in both modes
# ---------------------------------------------------------------------------

PALETTE_LIGHT = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]

PALETTE_DARK = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]

MAX_SERIES = len(PALETTE_LIGHT)

# The tail bucket is deliberately NOT a 9th hue — it is neutral, so it reads as
# "everything else" rather than as another peer category.
OTHER_LIGHT = "#898781"
OTHER_DARK = "#898781"
OTHER_LABEL = "Other"


# ---------------------------------------------------------------------------
# Status — reserved, mode-invariant, always paired with a visible label
# ---------------------------------------------------------------------------

STATUS_COLORS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
    "neutral": "#898781",
}

# QA status values → status role. Anything unrecognised falls through to the
# categorical palette rather than being force-fit into a status colour.
STATUS_VALUE_ROLES = {
    "passed": "good",
    "pass": "good",
    "success": "good",
    "failed": "critical",
    "fail": "critical",
    "error": "critical",
    "broken": "critical",
    "skipped": "warning",
    "skip": "warning",
    "pending": "serious",
    "unknown": "neutral",
    "not run": "neutral",
}


def status_role(value) -> str | None:
    return STATUS_VALUE_ROLES.get(str(value or "").strip().lower())


def status_color(value) -> str | None:
    role = status_role(value)
    return STATUS_COLORS.get(role) if role else None


def is_status_column(values) -> bool:
    """True when a column's values are (mostly) recognisable QA statuses, which
    is what licenses using the reserved status palette instead of categorical
    hues — colour then genuinely means good/bad rather than identity."""
    vals = [v for v in values if str(v).strip()]
    if not vals:
        return False
    known = sum(1 for v in vals if status_role(v))
    return known >= max(1, int(len(vals) * 0.6))


# ---------------------------------------------------------------------------
# Sequential — one hue, light→dark (light mode) / dark→light (dark mode)
# ---------------------------------------------------------------------------

SEQUENTIAL_LIGHT = [
    [0.0, "#cde2fb"], [0.25, "#9ec5f4"], [0.5, "#5598e7"],
    [0.75, "#256abf"], [1.0, "#0d366b"],
]

# On a dark surface the low end must recede toward the surface, so the ramp
# runs dark→light — the same single hue, re-stepped, not a flipped rainbow.
SEQUENTIAL_DARK = [
    [0.0, "#104281"], [0.25, "#184f95"], [0.5, "#2a78d6"],
    [0.75, "#6da7ec"], [1.0, "#cde2fb"],
]

# Diverging: warm/cool poles with a NEUTRAL grey midpoint (never a hue at the
# middle — the midpoint has to read as "nothing").
DIVERGING_LIGHT = [
    [0.0, "#d03b3b"], [0.25, "#e87ba4"], [0.5, "#f0efec"],
    [0.75, "#5598e7"], [1.0, "#0d366b"],
]
DIVERGING_DARK = [
    [0.0, "#e66767"], [0.25, "#d55181"], [0.5, "#383835"],
    [0.75, "#6da7ec"], [1.0, "#cde2fb"],
]


# ---------------------------------------------------------------------------
# Chrome — ink, grid, baseline. Transparent plot surfaces on purpose so the
# chart sits on the card it is embedded in rather than painting its own box.
# ---------------------------------------------------------------------------

CHROME_LIGHT = {
    "ink": "#0b0b0b",
    "ink_secondary": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "baseline": "#c3c2b7",
    "surface": "#ffffff",
    "border": "rgba(11,11,11,0.10)",
}

CHROME_DARK = {
    "ink": "#ffffff",
    "ink_secondary": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "baseline": "#383835",
    "surface": "#16181d",
    "border": "rgba(255,255,255,0.10)",
}

FONT_STACK = 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'


def theme_payload() -> dict:
    """Everything the frontend needs to re-theme a rendered figure in place.
    Emitted into `layout.meta.sentinel.theme`."""
    return {
        "light": {
            "palette": PALETTE_LIGHT,
            "other": OTHER_LIGHT,
            "sequential": SEQUENTIAL_LIGHT,
            "diverging": DIVERGING_LIGHT,
            "chrome": CHROME_LIGHT,
        },
        "dark": {
            "palette": PALETTE_DARK,
            "other": OTHER_DARK,
            "sequential": SEQUENTIAL_DARK,
            "diverging": DIVERGING_DARK,
            "chrome": CHROME_DARK,
        },
        "status": STATUS_COLORS,
    }
