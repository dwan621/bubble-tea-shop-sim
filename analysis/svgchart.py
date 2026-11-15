"""A tiny dependency-free SVG chart toolkit (standard library only).

matplotlib is not available in this environment (and the report must open
offline from the file system), so the figures are hand-built SVG strings.  The
output is deliberately plain: ``<svg>`` + ``<polyline>`` + ``<text>`` only, with
``<title>`` elements for native hover tooltips and no script, no external font
and no network reference.

All figures are responsive: the SVG carries a ``viewBox`` and ``width="100%"``
so it scales with the report column.

Public helpers
--------------
``line_chart``  : x/y line chart with optional log axes, error bars, bands.
``bar_chart``   : grouped vertical bar chart with optional error bars.
``html`` wrapper: ``<figure>`` helper used by the report builder.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

FONT = (
    "system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
)
MONO = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
INK = "#0f172a"
MUTED = "#64748b"
GRID = "#e2e8f0"
AXIS = "#94a3b8"
PAPER = "#ffffff"

#: Colour-blind friendly qualitative palette, reused across every figure.
PALETTE: Dict[str, str] = {
    "synchro+fcfs": "#64748b",
    "synchro+fast": "#0284c7",
    "split+fcfs": "#d97706",
    "split+fast": "#059669",
    "accent": "#7c3aed",
    "archive": "#e11d48",
    "python": "#0d9488",
    "neutral": "#94a3b8",
    "warn": "#b45309",
    "good": "#047857",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _nice_linear(lo: float, hi: float, count: int = 5) -> List[float]:
    """Round tick positions covering ``[lo, hi]``."""
    if hi <= lo:
        return [lo]
    span = hi - lo
    raw = span / max(count - 1, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        step = factor * magnitude
        if step >= raw:
            break
    start = math.floor(lo / step) * step
    ticks: List[float] = []
    value = start
    while value <= hi + step * 1e-9:
        if value >= lo - step * 1e-9:
            ticks.append(round(value, 10))
        value += step
    return ticks


def _log_ticks(lo: float, hi: float) -> List[float]:
    """Ticks at 1-2-5 per decade; denser when the range is narrow."""
    decades = int(math.floor(math.log10(hi))) - int(math.floor(math.log10(lo)))
    if decades <= 1:
        multipliers = (1, 2, 3, 5, 7)
    elif decades <= 2:
        multipliers = (1, 2, 5)
    else:
        multipliers = (1,)
    ticks: List[float] = []
    low = int(math.floor(math.log10(lo)))
    high = int(math.ceil(math.log10(hi)))
    for exponent in range(low, high + 1):
        for multiplier in multipliers:
            value = multiplier * 10 ** exponent
            if lo * 0.999 <= value <= hi * 1.001:
                ticks.append(value)
    return ticks or [lo, hi]


class _Scale:
    """Linear or log mapping between data space and pixel space."""

    def __init__(self, lo: float, hi: float, p0: float, p1: float, log: bool):
        self.log = log
        self.lo = lo
        self.hi = hi
        self.p0 = p0
        self.p1 = p1

    def _transform(self, value: float) -> float:
        if self.log:
            return math.log10(max(value, self.lo * 1e-6, 1e-12))
        return value

    def __call__(self, value: float) -> float:
        low = self._transform(self.lo)
        high = self._transform(self.hi)
        if high == low:
            return self.p0
        fraction = (self._transform(value) - low) / (high - low)
        fraction = min(max(fraction, -0.05), 1.05)
        return self.p0 + fraction * (self.p1 - self.p0)


def _fmt_number(value: float, digits: int = 2) -> str:
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 100:
        return f"{value:.0f}"
    if magnitude >= 10:
        return f"{value:.{min(digits, 1)}f}"
    if magnitude >= 1:
        return f"{value:.{digits}f}"
    return f"{value:.{digits + 1}f}"


# --------------------------------------------------------------------------
# line chart
# --------------------------------------------------------------------------
def line_chart(
    series: Sequence[Dict[str, object]],
    *,
    x_label: str,
    y_label: str,
    title: Optional[str] = None,
    width: int = 780,
    height: int = 400,
    x_range: Optional[Tuple[float, float]] = None,
    y_range: Optional[Tuple[float, float]] = None,
    x_ticks: Optional[Sequence[float]] = None,
    y_ticks: Optional[Sequence[float]] = None,
    y_log: bool = False,
    x_log: bool = False,
    x_fmt=_fmt_number,
    y_fmt=_fmt_number,
    zero_line: bool = False,
    legend: bool = True,
    note: Optional[str] = None,
    x_step_label: Optional[str] = None,
    aria_label: Optional[str] = None,
) -> str:
    """Render a line chart as a standalone SVG document string.

    Each series is ``{"label", "color", "points": [(x, y), ...], optional
    "errors": [(x, lower, upper), ...], optional "dash", optional "width",
    optional "marker"}``.
    """
    left = 70
    right = 24
    if legend:
        longest = max(len(str(item.get("label", ""))) for item in series)
        right = max(78, 34 + int(longest * 5.3) + 10)
    top = 44 if title else 22
    bottom = 56 if note else 46
    plot_w = width - left - right
    plot_h = height - top - bottom

    points_all: List[Tuple[float, float]] = []
    for item in series:
        points_all.extend((float(x), float(y)) for x, y in item["points"])
    if not points_all:
        raise ValueError("line_chart needs at least one point")

    if x_range is None:
        xs = [x for x, _ in points_all]
        x_range = (min(xs), max(xs))
    if y_range is None:
        ys = [y for _, y in points_all]
        lo, hi = min(ys), max(ys)
        if y_log:
            y_range = (lo * 0.9, hi * 1.1)
        else:
            pad = (hi - lo) * 0.12 if hi > lo else max(abs(hi) * 0.1, 1.0)
            y_range = (lo - pad, hi + pad)
    if y_log and y_range[0] <= 0:
        y_range = (max(y_range[0], 1e-3), y_range[1])

    sx = _Scale(x_range[0], x_range[1], left, left + plot_w, x_log)
    sy = _Scale(y_range[0], y_range[1], top + plot_h, top, y_log)

    out: List[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img" aria-label="{_esc(aria_label or title or y_label)}" '
        f'font-family="{FONT}">'
    )
    out.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="{PAPER}"/>')

    if title:
        out.append(
            f'<text x="{left}" y="22" font-size="14.5" font-weight="650" '
            f'fill="{INK}">{_esc(title)}</text>'
        )

    # grid + y ticks
    if y_ticks is None:
        y_ticks = _log_ticks(y_range[0], y_range[1]) if y_log else _nice_linear(
            y_range[0], y_range[1], 5
        )
    for tick in y_ticks:
        y = sy(tick)
        if not (top - 1 <= y <= top + plot_h + 1):
            continue
        out.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{left - 9}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
            f'fill="{MUTED}">{_esc(y_fmt(tick))}</text>'
        )

    # x ticks
    if x_ticks is None:
        x_ticks = _nice_linear(x_range[0], x_range[1], 6)
    for tick in x_ticks:
        x = sx(tick)
        if not (left - 1 <= x <= left + plot_w + 1):
            continue
        out.append(
            f'<line x1="{x:.1f}" y1="{top + plot_h}" x2="{x:.1f}" y2="{top + plot_h + 5}" '
            f'stroke="{AXIS}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{x:.1f}" y="{top + plot_h + 19}" text-anchor="middle" '
            f'font-size="11" fill="{MUTED}">{_esc(x_fmt(tick))}</text>'
        )

    # axes
    out.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" '
        f'stroke="{AXIS}" stroke-width="1"/>'
    )
    out.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" '
        f'stroke="{AXIS}" stroke-width="1"/>'
    )
    if zero_line and y_range[0] < 0 < y_range[1]:
        y = sy(0.0)
        out.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{INK}" stroke-width="1.2" stroke-dasharray="5 3"/>'
        )

    # axis titles
    out.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{height - (18 if note else 8)}" '
        f'text-anchor="middle" font-size="12" fill="{INK}">{_esc(x_label)}</text>'
    )
    out.append(
        f'<text transform="translate(16,{top + plot_h / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle" font-size="12" fill="{INK}">{_esc(y_label)}</text>'
    )
    if note:
        out.append(
            f'<text x="{left}" y="{height - 5}" font-size="10.5" fill="{MUTED}">'
            f"{_esc(note)}</text>"
        )
    if x_step_label:
        out.append(
            f'<text x="{left + plot_w}" y="{top + plot_h + 19}" text-anchor="end" '
            f'font-size="10" fill="{MUTED}">{_esc(x_step_label)}</text>'
        )

    # series
    for item in series:
        color = str(item.get("color", PALETTE["accent"]))
        label = str(item.get("label", ""))
        width_px = float(item.get("width", 2.2))
        dash = item.get("dash")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        coords = " ".join(f"{sx(float(x)):.1f},{sy(float(y)):.1f}" for x, y in item["points"])
        if not item.get("no_line"):
            out.append(
                f'<polyline points="{coords}" fill="none" stroke="{color}" '
                f'stroke-width="{width_px}" stroke-linejoin="round" stroke-linecap="round"'
                f'{dash_attr}/>'
            )
        for x, lo, hi in item.get("errors", []) or []:
            px = sx(float(x))
            out.append(
                f'<line x1="{px:.1f}" y1="{sy(float(lo)):.1f}" x2="{px:.1f}" '
                f'y2="{sy(float(hi)):.1f}" stroke="{color}" stroke-width="1.2" '
                f'opacity="0.55"/>'
            )
            for value in (float(lo), float(hi)):
                out.append(
                    f'<line x1="{px - 2.5:.1f}" y1="{sy(value):.1f}" x2="{px + 2.5:.1f}" '
                    f'y2="{sy(value):.1f}" stroke="{color}" stroke-width="1.2" opacity="0.55"/>'
                )
        if item.get("marker", True):
            for x, y in item["points"]:
                out.append(
                    f'<circle cx="{sx(float(x)):.1f}" cy="{sy(float(y)):.1f}" r="2.9" '
                    f'fill="{PAPER}" stroke="{color}" stroke-width="1.7">'
                    f"<title>{_esc(label)} | {_esc(x_fmt(float(x)))} -> "
                    f"{_esc(y_fmt(float(y)))}</title></circle>"
                )

    # legend (right margin)
    if legend:
        items = [(str(item.get("label", "")), str(item.get("color", ""))) for item in series]
        start_y = top + 6
        for index, (label, color) in enumerate(items):
            y = start_y + index * 20
            out.append(
                f'<line x1="{left + plot_w + 12}" y1="{y}" x2="{left + plot_w + 34}" '
                f'y2="{y}" stroke="{color}" stroke-width="2.6"/>'
            )
            out.append(
                f'<text x="{left + plot_w + 38}" y="{y + 4}" font-size="10.5" '
                f'fill="{INK}">{_esc(label)}</text>'
            )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# grouped bar chart
# --------------------------------------------------------------------------
def bar_chart(
    groups: Sequence[Dict[str, object]],
    *,
    categories: Sequence[str],
    y_label: str,
    title: Optional[str] = None,
    width: int = 780,
    height: int = 400,
    y_range: Optional[Tuple[float, float]] = None,
    y_fmt=_fmt_number,
    legend: bool = True,
    note: Optional[str] = None,
    value_fmt=None,
    aria_label: Optional[str] = None,
    category_labels: Optional[Sequence[str]] = None,
) -> str:
    """Grouped vertical bars. Each group is ``{"label","color","values",
    optional "errors"}`` with one value per category."""
    left = 68
    right = 24
    top = 64 if (title and legend) else (44 if title else 22)
    bottom = 64 if categories else 46
    plot_w = width - left - right
    plot_h = height - top - bottom

    values: List[float] = []
    for group in groups:
        values.extend(float(v) for v in group["values"])
        for lo, hi in group.get("errors", []) or []:
            values.extend([float(lo), float(hi)])
    if y_range is None:
        lo, hi = min(values + [0.0]), max(values + [0.0])
        pad = (hi - lo) * 0.12 if hi > lo else 1.0
        y_range = (min(lo - pad, 0.0) if lo < 0 else lo - pad * 0.3, hi + pad)
    sy = _Scale(y_range[0], y_range[1], top + plot_h, top, False)

    out: List[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img" aria-label="{_esc(aria_label or title or y_label)}" '
        f'font-family="{FONT}">'
    )
    out.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="{PAPER}"/>')
    if title:
        out.append(
            f'<text x="{left}" y="22" font-size="14.5" font-weight="650" fill="{INK}">'
            f"{_esc(title)}</text>"
        )

    ticks = _nice_linear(y_range[0], y_range[1], 5)
    for tick in ticks:
        y = sy(tick)
        if not (top - 1 <= y <= top + plot_h + 1):
            continue
        out.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{left - 9}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
            f'fill="{MUTED}">{_esc(y_fmt(tick))}</text>'
        )
    out.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" '
        f'stroke="{AXIS}" stroke-width="1"/>'
    )
    out.append(
        f'<line x1="{left}" y1="{sy(0.0):.1f}" x2="{left + plot_w}" y2="{sy(0.0):.1f}" '
        f'stroke="{AXIS}" stroke-width="1.2"/>'
    )
    out.append(
        f'<text transform="translate(16,{top + plot_h / 2:.1f}) rotate(-90)" '
        f'text-anchor="middle" font-size="12" fill="{INK}">{_esc(y_label)}</text>'
    )
    if note:
        out.append(
            f'<text x="{left}" y="{height - 6}" font-size="10.5" fill="{MUTED}">'
            f"{_esc(note)}</text>"
        )

    count = max(len(categories), 1)
    slot = plot_w / count
    group_count = max(len(groups), 1)
    bar_w = slot * 0.72 / group_count
    for index, category in enumerate(categories):
        centre = left + slot * (index + 0.5)
        label = (category_labels or categories)[index]
        out.append(
            f'<text x="{centre:.1f}" y="{top + plot_h + 18}" text-anchor="middle" '
            f'font-size="10.5" fill="{MUTED}">{_esc(label)}</text>'
        )
        for group_index, group in enumerate(groups):
            value = float(group["values"][index])
            x = centre - (group_count * bar_w) / 2 + group_index * bar_w
            y0 = sy(0.0)
            y1 = sy(value)
            color = str(group.get("color", PALETTE["accent"]))
            out.append(
                f'<rect x="{x + 1.2:.1f}" y="{min(y0, y1):.1f}" width="{max(bar_w - 2.4, 1):.1f}" '
                f'height="{abs(y0 - y1):.1f}" fill="{color}" rx="1.5" opacity="0.92">'
                f"<title>{_esc(category)} | {_esc(group.get('label', ''))} = "
                f"{_esc((value_fmt or y_fmt)(value))}</title></rect>"
            )
            errors = group.get("errors", []) or []
            if errors:
                lo, hi = errors[index]
                px = x + bar_w / 2
                out.append(
                    f'<line x1="{px:.1f}" y1="{sy(float(lo)):.1f}" x2="{px:.1f}" '
                    f'y2="{sy(float(hi)):.1f}" stroke="{INK}" stroke-width="1.1" opacity="0.65"/>'
                )
                for edge in (float(lo), float(hi)):
                    out.append(
                        f'<line x1="{px - 3:.1f}" y1="{sy(edge):.1f}" x2="{px + 3:.1f}" '
                        f'y2="{sy(edge):.1f}" stroke="{INK}" stroke-width="1.1" opacity="0.65"/>'
                    )

    if legend:
        # horizontal legend above the plot area, wrapping into two rows if needed
        x_cursor = left
        y = top - 14 if not title else top - 12
        row = 0
        for group in groups:
            label = str(group.get("label", ""))
            color = str(group.get("color", ""))
            estimate = 18 + len(label) * 5.4
            if x_cursor + estimate > left + plot_w and x_cursor > left:
                row += 1
                x_cursor = left
                y += 16
            out.append(
                f'<rect x="{x_cursor:.1f}" y="{y - 7}" width="10" height="10" rx="2" '
                f'fill="{color}"/>'
            )
            out.append(
                f'<text x="{x_cursor + 14:.1f}" y="{y + 2}" font-size="10.5" '
                f'fill="{INK}">{_esc(label)}</text>'
            )
            x_cursor += estimate
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# HTML helpers
# --------------------------------------------------------------------------
def figure(svg: str, caption: str, *, source: str = "", figure_id: str = "") -> str:
    """Wrap an SVG string in a ``<figure>`` with a caption and data source."""
    id_attr = f' id="{_esc(figure_id)}"' if figure_id else ""
    source_html = (
        f'<span class="fig-source">{_esc(source)}</span>' if source else ""
    )
    return (
        f'<figure class="figure"{id_attr}>{svg}'
        f"<figcaption>{caption}{source_html}</figcaption></figure>"
    )


__all__ = [
    "AXIS",
    "FONT",
    "GRID",
    "INK",
    "MUTED",
    "PALETTE",
    "PAPER",
    "bar_chart",
    "figure",
    "line_chart",
]
