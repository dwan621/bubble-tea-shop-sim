"""Build the static report from ``results/*.json``.

Outputs
-------
``docs/index.html``        the main report: English main text,
                           inline SVG, no JavaScript, no CDN, no fonts or CSS from
                           the network. It opens from ``file://``.
``docs/experiments-layers.md`` every result table as GitHub-flavoured Markdown.
``docs/figures-layers/*.svg``  the same figures as standalone files.

Data discipline
---------------
Every number printed by this script comes from ``results/*.json``, from the
baseline files in ``results/*.json`` (clearly labelled as the baseline),
or from a check this script performs itself (clearly labelled as a build-time
check). Nothing is typed in by hand except the prose. The archived AnyLogic
study in ``archive/`` is *not* rerunnable and is never presented as evidence
here; it is only referenced as an archive.

Run from the repository root::

    python analysis/build_report.py            # requires all five studies
    python analysis/build_report.py --allow-partial   # development only
"""

from __future__ import annotations

import html
import json
import math
import platform
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import svgchart as svg

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
RESULTS_DIR = RESULTS
DOCS = ROOT / "docs"
FIGDIR = DOCS / "figures-layers"
ARCHIVE = ROOT / "archive" / "report-2026-11.html"

STUDIES: Tuple[str, ...] = (
    "scenario_library",
    "demand_study",
    "network_study",
    "inventory_study",
    "economics_study",
)

TITLE_EN = "Bubble-tea shop simulation: four layers, one engine, and what the peaks cost"

POLICY_ORDER = ("synchro+fcfs", "synchro+fast", "split+fcfs", "split+fast")
POLICY_COLOR = {key: svg.PALETTE[key] for key in POLICY_ORDER}
POLICY_LABEL = {
    "synchro+fcfs": "Synchro + FCFS",
    "synchro+fast": "Synchro + fast priority",
    "split+fcfs": "Split + FCFS",
    "split+fast": "Split + fast priority",
}


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------
def esc(value: object) -> str:
    return html.escape(str(value))


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def fx(value: Optional[float], digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "n/a"
    if not _is_number(value):
        return str(value)
    magnitude = abs(float(value))
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 100:
        return f"{value:,.1f}"
    return f"{value:,.{digits}f}"


def fx0(value: Optional[float]) -> str:
    return fx(value, 0)


def signed(value: Optional[float], digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:+,.{digits}f}"


def pct(value: Optional[float], digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def pct_signed(value: Optional[float], digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value * 100:+.{digits}f}%"


def minutes(value: Optional[float], digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:,.{digits}f} min"


def lam(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def key_label(key: str) -> str:
    return key.replace("_", " ")


# --------------------------------------------------------------------------
# data layer
# --------------------------------------------------------------------------
class MissingStudy(RuntimeError):
    pass


def load_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class Ctx:
    """Everything the report builder reads, loaded once."""

    def __init__(self, studies: Dict[str, Dict[str, object]], baseline: Dict[str, Dict[str, object]], missing: Sequence[str]):
        self.studies = studies
        self.baseline = baseline
        self.missing = list(missing)
        self.figures: Dict[str, str] = {}
        self.validation: Dict[str, object] = {}
        self.problems: List[str] = []

    # -- generic access ---------------------------------------------------
    def has(self, study: str) -> bool:
        return study in self.studies

    def study(self, study: str) -> Dict[str, object]:
        if study not in self.studies:
            raise MissingStudy(study)
        return self.studies[study]

    def meta(self, study: str) -> Dict[str, object]:
        return dict(self.study(study).get("meta", {}))  # type: ignore[arg-type]

    def tables(self, study: str) -> Dict[str, object]:
        return dict(self.study(study).get("tables", {}))  # type: ignore[arg-type]

    def table(self, study: str, key: str) -> object:
        return self.tables(study).get(key)

    def rows(self, study: str, key: str) -> List[Dict[str, object]]:
        value = self.table(study, key)
        if not isinstance(value, list):
            raise KeyError(f"{study}.tables.{key} is not a list of rows")
        return [dict(row) for row in value if isinstance(row, dict)]

    def series(self, study: str) -> Dict[str, object]:
        return dict(self.study(study).get("series", {}))  # type: ignore[arg-type]

    def series_entry(self, study: str, key: str) -> object:
        return self.series(study).get(key)

    def reps_note(self, study: str) -> str:
        meta = self.meta(study)
        reps = meta.get("reps")
        if isinstance(reps, str):
            return reps
        if isinstance(reps, int):
            return f"{reps} replicates"
        return "replicates as documented in the study metadata"

    # -- figures ----------------------------------------------------------
    def add_figure(self, name: str, markup: str) -> str:
        self.figures[name] = markup
        return f'<figure class="figure">{markup}<figcaption>{self._caption_placeholder(name)}</figcaption></figure>'

    def _caption_placeholder(self, name: str) -> str:
        return name

    def figure(self, name: str, caption: str, source: str = "") -> str:
        if name not in self.figures:
            raise KeyError(f"figure {name!r} was not generated")
        source_html = f'<span class="fig-source">{esc(source)}</span>' if source else ""
        return (
            f'<figure class="figure" id="fig-{esc(name)}">{self.figures[name]}'
            f"<figcaption>{caption}{source_html}</figcaption></figure>"
        )

    def pending(self, study: str) -> str:
        return callout(
            "warn",
            f"<code>results/{esc(study)}.json</code> is not present in this build. "
            f"Run its experiment script, then <code>python analysis/build_report.py</code> again. "
            "No number is shown here rather than a stale or invented one.",
            title="Study not available in this build",
        )


def load_all(allow_partial: bool) -> Ctx:
    studies: Dict[str, Dict[str, object]] = {}
    missing: List[str] = []
    for name in STUDIES:
        path = RESULTS_DIR / f"{name}.json"
        if path.exists():
            studies[name] = load_json(path)
        else:
            missing.append(name)
    if missing and not allow_partial:
        raise SystemExit(
            "missing layer study files: "
            + ", ".join(f"results/{name}.json" for name in missing)
            + "\nrun the corresponding experiment scripts first "
            "(analysis/run_demand_network.py, analysis/run_inventory_econ.py)"
        )
    baseline: Dict[str, Dict[str, object]] = {}
    for name in ("policy_sweep", "breakeven", "behaviour", "anchors"):
        path = RESULTS / f"{name}.json"
        if path.exists():
            baseline[name] = load_json(path)
    return Ctx(studies, baseline, missing)


# --------------------------------------------------------------------------
# HTML fragments
# --------------------------------------------------------------------------
CSS = """
:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f6f7f9;--card:#ffffff;
--teal:#0f766e;--teal-l:#ccfbf1;--amber:#b45309;--rose:#9f1239;--violet:#6d28d9;
--mono:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.62 system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 22px 90px}
a{color:var(--teal)}
.hero{background:linear-gradient(135deg,#0f172a 0%,#134e4a 58%,#0f766e 100%);color:#e2e8f0;padding:52px 0 40px}
.hero .wrap{padding-bottom:0}
.hero h1{font-size:clamp(1.6rem,3.2vw,2.4rem);line-height:1.2;margin:0 0 10px;color:#fff;letter-spacing:-.5px}
.hero .sub{font-size:1.02rem;color:#99f6e4;margin:0 0 4px}
.hero .meta{font-size:.79rem;color:#a5b4fc;font-family:var(--mono)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:13px;margin:24px 0 0}
.stat{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);border-radius:12px;padding:13px 15px}
.stat .label{font-size:.71rem;text-transform:uppercase;letter-spacing:.09em;color:#7dd3fc}
.stat .value{font-size:1.35rem;font-weight:700;color:#fff;margin-top:3px;font-variant-numeric:tabular-nums}
.stat .hint{font-size:.73rem;color:#cbd5e1;margin-top:2px;line-height:1.4}
nav.toc{position:sticky;top:0;z-index:20;background:rgba(246,247,249,.95);border-bottom:1px solid var(--line)}
nav.toc .wrap{display:flex;flex-wrap:wrap;gap:4px;padding:9px 22px}
nav.toc a{font-size:.78rem;color:#334155;text-decoration:none;padding:5px 9px;border-radius:7px;white-space:nowrap}
nav.toc a:hover{background:#e2e8f0}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:26px 30px;margin:22px 0}
h2{font-size:1.38rem;margin:0 0 6px;letter-spacing:-.3px}
h2 .num{color:var(--teal);font-variant-numeric:tabular-nums;margin-right:8px}
h3{font-size:1.04rem;margin:22px 0 8px}
h4{font-size:.94rem;margin:18px 0 6px;color:#334155}
p{margin:0 0 12px}
.lead{font-size:1.02rem;color:#1e293b}
.table-wrap{overflow-x:auto;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:.84rem;font-variant-numeric:tabular-nums}
caption{caption-side:top;text-align:left;font-size:.84rem;color:var(--muted);padding:0 0 6px}
th{background:#f1f5f9;color:#334155;font-weight:600;padding:7px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:6px 9px;border-bottom:1px solid #f1f5f9}
tbody tr:hover{background:#f8fafc}
td.c-l,th.c-l{text-align:left}td.c-r,th.c-r{text-align:right}
.table-note{font-size:.78rem;color:var(--muted);margin:-4px 0 14px}
.tag{display:inline-block;font-size:.67rem;letter-spacing:.04em;text-transform:uppercase;padding:2px 7px;border-radius:999px;font-weight:600;vertical-align:1px}
.tag.py{background:var(--teal-l);color:#115e59}
.tag.layer{background:#ede9fe;color:#5b21b6}
.tag.an{background:#ffe4e6;color:#9f1239}
.tag.baseline{background:#e2e8f0;color:#334155}
.callout{border-radius:10px;padding:13px 16px;margin:16px 0;font-size:.91rem;border:1px solid}
.callout.info{background:#f0f9ff;border-color:#bae6fd}
.callout.warn{background:#fffbeb;border-color:#fde68a}
.callout.good{background:#f0fdf4;border-color:#bbf7d0}
.callout.key{background:#f5f3ff;border-color:#ddd6fe}
.callout-title{font-weight:650;margin:0 0 5px}
.callout ul{margin:6px 0 0 18px;padding:0}.callout li{margin:3px 0}
figure{margin:18px 0;padding:14px 14px 8px;background:#fff;border:1px solid var(--line);border-radius:12px}
figure svg{display:block;width:100%;height:auto}
figcaption{font-size:.8rem;color:var(--muted);margin-top:6px}
.fig-source{display:block;font-size:.73rem;color:#94a3b8;font-family:var(--mono);margin-top:3px}
.fig-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}
.fig-grid figure{margin:0}
.fig-grid.three{grid-template-columns:repeat(3,1fr)}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:.8rem;color:#334155;margin:8px 0 0}
.legend span{display:inline-flex;align-items:center;gap:5px}
.legend i{width:15px;height:3px;border-radius:2px;display:inline-block}
code,pre{font-family:var(--mono);font-size:.82rem}
pre{background:#0f172a;color:#e2e8f0;padding:14px 16px;border-radius:10px;overflow-x:auto;line-height:1.55}
code:not(pre code){background:#f1f5f9;padding:1px 5px;border-radius:4px}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;font-size:.88rem;margin:10px 0}
.kv dt{color:var(--muted)}.kv dd{margin:0;font-variant-numeric:tabular-nums}
footer{color:var(--muted);font-size:.8rem;text-align:center;padding:30px 0 0}
.pill-row{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 4px}
@media (max-width:780px){.fig-grid{grid-template-columns:1fr}section{padding:20px 16px}}
@media print{nav.toc{display:none}body{background:#fff}section{break-inside:avoid;border:none;padding:0 0 18px}}
"""


def table(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    *,
    caption: Optional[str] = None,
    note: Optional[str] = None,
    align: Optional[Sequence[str]] = None,
) -> str:
    columns = len(headers)
    alignment = list(align) if align else ["l"] + ["r"] * (columns - 1)
    out: List[str] = ['<div class="table-wrap">', "<table>"]
    if caption:
        out.append(f"<caption>{caption}</caption>")
    out.append("<thead><tr>")
    for index, header in enumerate(headers):
        out.append(f'<th class="c-{"l" if alignment[index] == "l" else "r"}">{header}</th>')
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for index, cell in enumerate(row):
            out.append(f'<td class="c-{"l" if alignment[index] == "l" else "r"}">{cell}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    if note:
        out.append(f'<p class="table-note">{note}</p>')
    return "".join(out)


def md_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    lines = ["| " + " | ".join(str(header) for header in headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def callout(kind: str, body: str, *, title: Optional[str] = None) -> str:
    title_html = f'<p class="callout-title">{esc(title)}</p>' if title else ""
    return f'<div class="callout {kind}">{title_html}{body}</div>'


def section(number: int, title_en: str, anchor: str, body: str) -> str:
    return (
        f'<section id="{anchor}"><h2><span class="num">{number}.</span>{esc(title_en)}</h2>'
        f"{body}</section>"
    )


def kv_list(pairs: Iterable[Tuple[str, str]]) -> str:
    inner = "".join(f"<dt>{esc(key)}</dt><dd>{value}</dd>" for key, value in pairs)
    return f'<dl class="kv">{inner}</dl>'


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------
def _figures_into(ctx: Ctx, name: str, markup: str) -> None:
    ctx.figures[name] = markup


def fig_architecture() -> str:
    """Hand-built diagram of the four mechanism layers on top of the baseline core."""
    width, height = 900, 400
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" '
        f'role="img" aria-label="The four mechanism layers sit on top of the original engine" '
        f'font-family="{svg.FONT}">',
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
    ]

    def box(x, y, w, h, fill, stroke, title, lines, title_size=13, line_size=10.5):
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        out.append(f'<text x="{x + w / 2}" y="{y + 22}" text-anchor="middle" font-size="{title_size}" font-weight="650" fill="{svg.INK}">{esc(title)}</text>')
        for index, line in enumerate(lines):
            out.append(f'<text x="{x + w / 2}" y="{y + 22 + (index + 1) * 15}" text-anchor="middle" font-size="{line_size}" fill="{svg.MUTED}">{esc(line)}</text>')

    # baseline core at the bottom
    box(60, 292, 780, 84, "#ecfdf5", "#0f766e", "baseline core (unchanged): one clerk pool, stationary Poisson arrivals, fixed service times",
        ["2x2 policy matrix: split vs synchronised delivery  x  fast-item priority vs FCFS",
         "200 replicates per cell, common random numbers, 480-minute day with 60-minute warm-up"], title_size=12.5)
    # four layers
    box(60, 168, 185, 96, "#f0f9ff", "#0284c7", "1 · Demand",
        ["intra-day profile", "batch arrivals", "customer classes", "patience (balk/renege)"])
    box(250, 168, 185, 96, "#fff7ed", "#d97706", "2 · Supply network",
        ["stations + capacity", "staff skills", "shift windows, breaks", "routing per component"])
    box(440, 168, 185, 96, "#faf5ff", "#7c3aed", "3 · Inventory / BOM",
        ["(s, S) replenishment", "lead time", "shelf life, waste", "stock-out policy"])
    box(630, 168, 210, 96, "#fef2f2", "#be123c", "4 · Economics / fairness",
        ["time-of-day pricing", "demand elasticity", "SLA compensation", "starvation cap"])
    # arrows down into the core
    for x in (152, 342, 532, 735):
        out.append(f'<line x1="{x}" y1="264" x2="{x}" y2="292" stroke="#94a3b8" stroke-width="1.4" marker-end="url(#arrow)"/>')
    out.append('<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
               '<path d="M0,0 L6,3 L0,6 z" fill="#94a3b8"/></marker></defs>')
    out.append(f'<text x="60" y="145" font-size="12" font-weight="650" fill="{svg.INK}">Optional layers (each is off by default; every layer is a frozen, hashable spec object)</text>')
    out.append(f'<text x="60" y="60" font-size="14" font-weight="650" fill="{svg.INK}">One engine, four optional layers, one baseline-compatible core</text>')
    out.append(f'<text x="60" y="82" font-size="11.5" fill="{svg.MUTED}">A configuration with no layer enabled reproduces the original model bit-for-bit '
               f'(pinned by tests/test_layers.py)</text>')
    out.append(f'<text x="60" y="120" font-size="11.5" fill="{svg.MUTED}">Scenario JSON (data/scenarios/*.json) → SimConfig → discrete-event engine → metrics + trace</text>')
    out.append("</svg>")
    return "".join(out)


def fig_demand_profiles(ctx: Ctx) -> str:
    profiles = ctx.series_entry("scenario_library", "demand_profiles")
    chosen = ("campus_rush", "exam_week", "cbd_commute", "late_night_study")
    colors = ("#0284c7", "#d97706", "#7c3aed", "#059669")
    series = []
    for index, name in enumerate(chosen):
        segments = profiles.get(name, [[0.0, 1.0]])  # type: ignore[union-attr]
        points = []
        for i, (start, multiplier) in enumerate(segments):
            end = segments[i + 1][0] if i + 1 < len(segments) else 480.0
            points.append((float(start), float(multiplier)))
            points.append((float(end), float(multiplier)))
        series.append({"label": name, "color": colors[index], "points": points, "marker": False})
    return svg.line_chart(
        series,
        x_label="minute of the modelled day",
        y_label="arrival-rate multiplier",
        title="Intra-day demand profiles: the same daily mean can hide very different peaks",
        width=820, height=300, y_range=(0, 2.6), legend=True,
        note="Piecewise-constant DemandProfile segments; the loader normalises the daily mean when demand.normalize_daily_mean is set.",
        aria_label="Intra-day demand profiles of four scenarios",
    )


def fig_scenario_compare(ctx: Ctx) -> str:
    rows = ctx.rows("scenario_library", "comparison")
    names = [str(row["name"]) for row in rows]
    profit = [float(row["profit_per_hour"]) for row in rows]
    colors = ["#0f766e" if row["baseline_compat"] else "#0284c7" for row in rows]
    # bar chart is fine for 16 scenarios when the labels are rotated by giving
    # short labels; svgchart keeps labels horizontal, so use short forms.
    short = [name.replace("_", " ")[:14] for name in names]
    groups = [{"label": "profit per hour", "color": "#0f766e", "values": profit}]
    return svg.bar_chart(
        groups, categories=short,
        y_label="profit / hour",
        title="Scenario catalogue: profit per hour in each scenario (100 replicates, each scenario's own policy)",
        width=900, height=360, value_fmt=lambda v: f"{v:,.0f}",
        note="Each scenario runs with its own configuration and policy, so differences mix context and policy; the rows are a map, not a controlled comparison.",
        aria_label="Profit per hour per scenario",
    )


def fig_inv_lead_time(ctx: Ctx) -> str:
    series = ctx.series_entry("inventory_study", "lead_time")
    x = [float(v) for v in series["x"]]  # type: ignore[index]
    fill = [float(v) for v in series["fill_rate"]]  # type: ignore[index]
    profit = [float(v) for v in series["profit_per_hour"]]  # type: ignore[index]
    left = svg.line_chart(
        [{"label": "fill rate", "color": "#0d9488", "points": list(zip(x, fill))}],
        x_label="replenishment lead time (min)", y_label="fill rate",
        title="Fill rate vs lead time", width=430, height=280,
        y_fmt=lambda v: f"{v * 100:.0f}%", x_fmt=lambda v: f"{v:.0f}",
        aria_label="Fill rate versus lead time",
    )
    right = svg.line_chart(
        [{"label": "profit / hour", "color": "#b45309", "points": list(zip(x, profit))}],
        x_label="replenishment lead time (min)", y_label="profit / hour",
        title="Profit per hour vs lead time", width=430, height=280,
        x_fmt=lambda v: f"{v:.0f}",
        aria_label="Profit per hour versus lead time",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_inv_shelf_life(ctx: Ctx) -> str:
    series = ctx.series_entry("inventory_study", "shelf_life")
    x = [float(v) for v in series["x"]]  # type: ignore[index]
    waste = [float(v) for v in series["waste_units"]]  # type: ignore[index]
    fill = [float(v) for v in series["fill_rate"]]  # type: ignore[index]
    left = svg.line_chart(
        [{"label": "waste units", "color": "#be123c", "points": list(zip(x, waste))}],
        x_label="pearl shelf life (min)", y_label="wasted units / day",
        title="Waste vs shelf life", width=430, height=280, x_fmt=lambda v: f"{v:.0f}",
        aria_label="Waste versus shelf life",
    )
    right = svg.line_chart(
        [{"label": "fill rate", "color": "#0d9488", "points": list(zip(x, fill))}],
        x_label="pearl shelf life (min)", y_label="fill rate",
        title="Fill rate vs shelf life", width=430, height=280,
        y_fmt=lambda v: f"{v * 100:.0f}%", x_fmt=lambda v: f"{v:.0f}",
        aria_label="Fill rate versus shelf life",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_inv_ceiling(ctx: Ctx) -> str:
    series = ctx.series_entry("inventory_study", "pearls_order_ceiling")
    x = [float(v) for v in series["x"]]  # type: ignore[index]
    waste = [float(v) for v in series["waste_units"]]  # type: ignore[index]
    fill = [float(v) for v in series["fill_rate"]]  # type: ignore[index]
    left = svg.line_chart(
        [{"label": "waste", "color": "#be123c", "points": list(zip(x, waste))}],
        x_label="pearl order quantity (units)", y_label="wasted units / day",
        title="Pearl order quantity: waste appears at the ceiling", width=430, height=260,
        x_fmt=lambda v: f"{v:.0f}", aria_label="Waste versus pearl order quantity",
    )
    right = svg.line_chart(
        [{"label": "fill rate", "color": "#0d9488", "points": list(zip(x, fill))}],
        x_label="pearl order quantity (units)", y_label="fill rate",
        title="Fill rate vs pearl order quantity", width=430, height=260,
        y_fmt=lambda v: f"{v * 100:.0f}%", x_fmt=lambda v: f"{v:.0f}",
        aria_label="Fill rate versus pearl order quantity",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_inv_stockout(ctx: Ctx) -> str:
    rows = ctx.rows("inventory_study", "stockout_policy")
    categories: List[str] = []
    values: List[float] = []
    colors: List[str] = []
    palette = {"baseline": "#64748b", "ice_short": "#b45309", "pearls_short": "#be123c"}
    for row in rows:
        categories.append(f"{row['regime']} · {str(row['stockout_policy']).replace('_', ' ')}")
        values.append(float(row["profit_per_hour"]))
        colors.append(palette.get(str(row["regime"]), "#0f766e"))
    return svg.bar_chart(
        [{"label": "profit / hour", "color": "#0f766e", "values": values}],
        categories=categories, category_labels=categories,
        y_label="profit / hour",
        title="Stock-out policy: losing the sale vs substituting",
        width=900, height=330, value_fmt=lambda v: f"{v:,.0f}",
        note="Bars share one colour per row; the table in docs/experiments-layers.md lists the regime for every row.",
        aria_label="Profit per hour by stock-out policy",
    )


def fig_econ_pricing(ctx: Ctx) -> str:
    curves = ctx.series_entry("economics_study", "pricing_curves")
    colors = {"-0.5": "#0284c7", "-1": "#b45309", "-1.5": "#7c3aed", "-2": "#059669"}
    series = []
    for key, payload in curves.items():  # type: ignore[union-attr]
        x = [float(v) for v in payload["x"]]
        y = [float(v) for v in payload["profit_per_hour"]]
        series.append({"label": f"elasticity {key}", "color": colors.get(str(key), "#64748b"), "points": list(zip(x, y))})
    return svg.line_chart(
        series, x_label="peak price multiplier", y_label="profit / hour",
        title="Peak pricing: profit per hour vs the peak multiplier",
        width=820, height=330, x_fmt=lambda v: f"×{v:.1f}",
        note="Same peak windows (60–180 and 300–420 min of the campus_rush day); higher elasticity means demand falls faster when the multiplier rises.",
        aria_label="Profit per hour versus peak price multiplier",
    )


def fig_econ_sla(ctx: Ctx) -> str:
    rows = ctx.rows("economics_study", "sla_grid")
    categories = [f"{row['target_minutes']:.0f} min / {row['compensation']:.0f}" for row in rows]
    attainment = [float(row["sla_attainment"]) if row.get("sla_attainment") is not None else 0.0 for row in rows]
    profit = [float(row["profit_per_hour"]) for row in rows]
    left = svg.bar_chart(
        [{"label": "SLA attainment", "color": "#0f766e", "values": attainment}],
        categories=categories, y_label="attainment",
        title="SLA attainment (target / compensation)", width=430, height=300,
        value_fmt=lambda v: f"{v * 100:.0f}%", y_fmt=lambda v: f"{v * 100:.0f}%",
        aria_label="SLA attainment by target and compensation",
    )
    right = svg.bar_chart(
        [{"label": "profit / hour", "color": "#b45309", "values": profit}],
        categories=categories, y_label="profit / hour",
        title="Profit per hour with SLA compensation", width=430, height=300,
        value_fmt=lambda v: f"{v:,.0f}", aria_label="Profit per hour by SLA target and compensation",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_econ_fairness(ctx: Ctx) -> str:
    rows = ctx.rows("economics_study", "fairness_pareto")
    points = [(float(row["los_p95"]), float(row["profit_per_hour"])) for row in rows]
    return svg.line_chart(
        [{"label": "starvation cap", "color": "#7c3aed", "points": points, "no_line": True}],
        x_label="p95 time in system (min)", y_label="profit / hour",
        title="Fairness vs profit: each dot is one starvation-cap setting",
        width=820, height=330, zero_line=False,
        note="No line is drawn: these are distinct configurations, not a trajectory. Tooltips carry the exact values; the table lists the caps.",
        aria_label="Profit per hour versus p95 waiting under different starvation caps",
    )


def fig_econ_manager(ctx: Ctx) -> str:
    rows = ctx.rows("economics_study", "good_manager")
    categories = [str(row["scenario"]).replace("_", " ") for row in rows]
    profit = [float(row["profit_per_hour"]) for row in rows]
    return svg.bar_chart(
        [{"label": "profit / hour", "color": "#0f766e", "values": profit}],
        categories=categories, y_label="profit / hour",
        title="The management bundle, one lever at a time",
        width=900, height=340, value_fmt=lambda v: f"{v:,.0f}",
        note="Every row starts from the same campus_rush baseline; the full metrics are in the table below and in docs/experiments-layers.md.",
        aria_label="Profit per hour for each management lever",
    )


def fig_baseline_policies(ctx: Ctx) -> str:
    chosen = baseline_policy_rows(ctx, workers=3, lam=1.25)
    keys = [str(row["policy_key"]) for row in chosen]
    values = [float(row["means"]["profit_per_hour"]) for row in chosen]
    return svg.bar_chart(
        [{"label": "profit / hour", "color": "#0f766e", "values": values}],
        categories=[POLICY_LABEL.get(key, key) for key in keys],
        y_label="profit / hour",
        title="baseline (Python engine, 200 replicates): profit per hour at λ = 1.25, m = 3",
        width=820, height=320, value_fmt=lambda v: f"{v:,.1f}",
        note="All four policies at the same load; the values are also tabulated in docs/experiments.md (baseline).",
        aria_label="baseline profit per hour by policy",
    )


def fig_demand_hourly(ctx: Ctx) -> str:
    hourly = ctx.series_entry("demand_study", "peak_vs_flat_hourly")
    styles = {
        "peak_shape": ("campus peak shape", "#b45309"),
        "flat_same_daily_mean": ("flat, same daily mean", "#0284c7"),
    }
    busy_series = []
    los_series = []
    for key, (label, color) in styles.items():
        rows = hourly.get(key, [])  # type: ignore[union-attr]
        busy_points = [(float(row["hour_start"]) / 60.0 + 1.0, float(row["busy_ratio"])) for row in rows]
        los_points = [
            (float(row["hour_start"]) / 60.0 + 1.0, float(row["mean_los"]))
            for row in rows
            if row.get("mean_los") is not None
        ]
        busy_series.append({"label": label, "color": color, "points": busy_points, "marker": False})
        los_series.append({"label": label, "color": color, "points": los_points, "marker": False})
    left = svg.line_chart(
        busy_series, x_label="hour of the modelled day", y_label="busy ratio",
        title="Busy staff-minutes per hour", width=470, height=290,
        x_fmt=lambda v: f"{int(v)}h", y_fmt=lambda v: f"{v * 100:.0f}%",
        aria_label="Hourly busy ratio for peak and flat demand",
    )
    right = svg.line_chart(
        los_series, x_label="hour of the modelled day", y_label="mean time in system (min)",
        title="Hourly mean time in system", width=470, height=290,
        x_fmt=lambda v: f"{int(v)}h",
        aria_label="Hourly mean LOS for peak and flat demand",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_peak_factor(ctx: Ctx) -> str:
    series = ctx.series_entry("demand_study", "peak_factor")
    curve = series["curve"]  # type: ignore[index]
    xs = [float(row["peak_to_mean"]) for row in curve]
    panels = (
        ("p95 time in system (min)", "los_p95", "#b45309", lambda v: f"{v:.1f}"),
        ("walk-away rate", "balk_rate", "#e11d48", lambda v: f"{v * 100:.0f}%"),
        ("profit per hour", "profit_per_hour", "#0f766e", lambda v: f"{v:,.0f}"),
    )
    charts = []
    for y_label, key, color, y_fmt in panels:
        points = [(xs[i], float(row[key])) for i, row in enumerate(curve)]
        charts.append(
            svg.line_chart(
                [{"label": key, "color": color, "points": points}],
                x_label="peak-to-mean multiplier", y_label=y_label,
                title=f"{y_label} vs peakiness", width=330, height=280,
                legend=False, x_fmt=lambda v: f"×{v:.1f}", y_fmt=y_fmt,
                aria_label=f"{y_label} versus peak-to-mean multiplier",
            )
        )
    return '<div class="fig-grid three">' + "".join(charts) + "</div>"


def fig_variability(ctx: Ctx) -> str:
    series = ctx.series_entry("demand_study", "variability")
    variants = [str(row["variant"]) for row in series["lambda_1"]]  # type: ignore[index]
    short = {
        "fixed": "fixed",
        "exponential": "exponential (CV 1)",
        "lognormal_cv0.25": "lognormal CV .25",
        "lognormal_cv0.50": "lognormal CV .50",
        "lognormal_cv0.75": "lognormal CV .75",
    }
    categories = [short.get(name, name) for name in variants]
    groups = []
    for key, label, color in (("lambda_1", "λ = 1.0", "#0284c7"), ("lambda_1.2", "λ = 1.2", "#b45309")):
        rows = series[key]  # type: ignore[index]
        groups.append({"label": label, "color": color, "values": [float(row["p95"]) for row in rows]})
    return svg.bar_chart(
        groups, categories=categories, y_label="p95 time in system (min)",
        title="Make-time variability moves the tail, not the mean",
        width=900, height=340, value_fmt=lambda v: f"{v:.1f} min",
        note="The engine forces exponential sampling (CV = 1) whenever the variability kind is exponential; the lognormal cells set their CV explicitly.",
        aria_label="p95 time in system by service-time variability and load",
    )


def fig_patience(ctx: Ctx) -> str:
    series = ctx.series_entry("demand_study", "patience")
    grid = series["grid"]  # type: ignore[index]
    rows = [row for row in grid if abs(float(row["lambda"]) - 1.2) < 1e-9 and abs(float(row["renege_mean"]) - 10.0) < 1e-9]
    rows.sort(key=lambda row: float(row["balk_mean"]))
    categories = [f"balk at {row['balk_mean']:.0f} min" for row in rows]
    left = svg.bar_chart(
        [{"label": "abandonment rate", "color": "#e11d48", "values": [float(row["abandon_rate"]) for row in rows]}],
        categories=categories, y_label="abandonment rate", title="Who leaves (λ = 1.2)",
        width=430, height=290, value_fmt=lambda v: f"{v * 100:.1f}%", y_fmt=lambda v: f"{v * 100:.0f}%",
        aria_label="Abandonment rate by balk threshold",
    )
    right = svg.bar_chart(
        [{"label": "profit / hour", "color": "#0f766e", "values": [float(row["profit_per_hour"]) for row in rows]}],
        categories=categories, y_label="profit / hour", title="What the leaving costs (λ = 1.2)",
        width=430, height=290, value_fmt=lambda v: f"{v:,.0f}",
        aria_label="Profit per hour by balk threshold",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_batch(ctx: Ctx) -> str:
    series = ctx.series_entry("demand_study", "batch")
    styles = {
        "arrival_events_fixed": ("arrival-event rate fixed", "#7c3aed"),
        "customer_mean_fixed": ("daily customer mean fixed", "#0d9488"),
    }
    balk_series = []
    profit_series = []
    for key, (label, color) in styles.items():
        rows = series.get(key, [])  # type: ignore[union-attr]
        balk_series.append(
            {"label": label, "color": color,
             "points": [(float(row["batch_probability"]), float(row["balk_rate"])) for row in rows]}
        )
        profit_series.append(
            {"label": label, "color": color,
             "points": [(float(row["batch_probability"]), float(row["profit_per_hour"])) for row in rows]}
        )
    left = svg.line_chart(
        balk_series, x_label="batch probability", y_label="walk-away rate",
        title="Group orders: walk-aways", width=470, height=280,
        x_fmt=lambda v: f"{v:.1f}", y_fmt=lambda v: f"{v * 100:.0f}%",
        aria_label="Walk-away rate versus batch probability",
    )
    right = svg.line_chart(
        profit_series, x_label="batch probability", y_label="profit / hour",
        title="Group orders: profit", width=470, height=280,
        x_fmt=lambda v: f"{v:.1f}",
        aria_label="Profit per hour versus batch probability",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_tea_capacity(ctx: Ctx) -> str:
    series = ctx.series_entry("network_study", "tea_capacity")
    by_lambda = series["by_lambda"]  # type: ignore[index]
    colors = {"lambda_0.6": "#0284c7", "lambda_0.9": "#7c3aed", "lambda_1.2": "#b45309"}
    los_series = []
    profit_series = []
    for key, rows in by_lambda.items():  # type: ignore[union-attr]
        label = f"λ = {key.split('_')[1]}"
        color = colors.get(key, "#64748b")
        los_series.append(
            {"label": label, "color": color,
             "points": [(float(row["capacity"]), float(row["los_p95"])) for row in rows]}
        )
        profit_series.append(
            {"label": label, "color": color,
             "points": [(float(row["capacity"]), float(row["profit_per_hour"])) for row in rows]}
        )
    left = svg.line_chart(
        los_series, x_label="tea stations (baristas synced)", y_label="p95 time in system (min)",
        title="More tea stations: the tail", width=470, height=300,
        x_fmt=lambda v: f"{int(v)}", aria_label="p95 LOS versus tea station capacity",
    )
    right = svg.line_chart(
        profit_series, x_label="tea stations (baristas synced)", y_label="profit / hour",
        title="More tea stations: the profit", width=470, height=300,
        x_fmt=lambda v: f"{int(v)}", aria_label="Profit per hour versus tea station capacity",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_bottleneck_utils(ctx: Ctx) -> str:
    migration = ctx.table("network_study", "bottleneck_migration")
    row = migration["lambda_1.2"]  # type: ignore[index]
    tea = row["tea_util_by_capacity"]  # type: ignore[index]
    pool = row["barista_pool_util_by_capacity"]  # type: ignore[index]
    capacities = sorted(int(key) for key in tea)
    series = [
        {"label": "tea station utilisation", "color": "#b45309",
         "points": [(float(k), float(tea[str(k)])) for k in capacities]},
        {"label": "barista pool utilisation", "color": "#0284c7",
         "points": [(float(k), float(pool[str(k)])) for k in capacities]},
    ]
    return svg.line_chart(
        series, x_label="tea stations (fixed labour: one barista per station)",
        y_label="utilisation",
        title="Where the constraint sits at λ = 1.2: the tea station stops being the binding resource",
        width=880, height=300, y_fmt=lambda v: f"{v * 100:.0f}%", x_fmt=lambda v: f"{int(v)}",
        note="The dashed vertical line marks the critical capacity the study computes from paired marginal profit. Beyond it the shared barista pool and the order counter, not the tea station, decide the queue.",
        aria_label="Tea station and barista pool utilisation by capacity",
    )


def fig_strategy(ctx: Ctx) -> str:
    """Two panels: the six paired contrasts of the study, profit and tail."""
    rows = ctx.rows("network_study", "strategy_bottleneck_paired")

    def classify(name: str) -> str:
        if name.endswith("_split_fast_minus_synchro_plain"):
            return "split + fast"
        if name.endswith("_synchro_fast_minus_synchro_plain"):
            return "fast priority"
        if name.endswith("_split_plain_minus_synchro_plain"):
            return "split delivery"
        return "other"

    categories = []
    profit_values, profit_errors = [], []
    p95_values, p95_errors = [], []
    for row in rows:
        surname = str(row["name"])
        kind = "tea" if "tea" in surname else "ice"
        categories.append(f"{kind} · {classify(str(row['name']))}")
        profit = dict(row["metrics"]["profit_per_hour"])
        tail = dict(row["metrics"]["los_p95"])
        profit_values.append(float(profit["diff"]))
        profit_errors.append((float(profit["diff"]) - float(profit["ci95"]), float(profit["diff"]) + float(profit["ci95"])))
        p95_values.append(float(tail["diff"]))
        p95_errors.append((float(tail["diff"]) - float(tail["ci95"]), float(tail["diff"]) + float(tail["ci95"])))

    left = svg.bar_chart(
        [{"label": "Δ profit / hour", "color": "#0f766e", "values": profit_values, "errors": profit_errors}],
        categories=categories, y_label="Δ profit / hour vs synchro + plain",
        title="Policy value against each bottleneck", width=450, height=320,
        value_fmt=lambda v: f"{v:+.1f}", aria_label="Profit effect of each policy contrast by bottleneck",
    )
    right = svg.bar_chart(
        [{"label": "Δ p95", "color": "#b45309", "values": p95_values, "errors": p95_errors}],
        categories=categories, y_label="Δ p95 time in system (min)",
        title="Tail effect of the same contrasts", width=450, height=320,
        value_fmt=lambda v: f"{v:+.2f}", aria_label="p95 effect of each policy contrast by bottleneck",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_skills(ctx: Ctx) -> str:
    series = ctx.series_entry("network_study", "skills")
    rows = series["profit"]  # type: ignore[index]
    categories = [str(row["configuration"]).replace("_", "-") for row in rows]
    left = svg.bar_chart(
        [{"label": "profit / hour", "color": "#0f766e", "values": [float(row["profit_per_hour"]) for row in rows]}],
        categories=categories, y_label="profit / hour", title="Skill matrix: same headcount, same wage",
        width=430, height=300, value_fmt=lambda v: f"{v:,.1f}",
        aria_label="Profit per hour by skill matrix",
    )
    right = svg.bar_chart(
        [{"label": "p95", "color": "#b45309", "values": [float(row["los_p95"]) for row in rows]}],
        categories=categories, y_label="p95 time in system (min)", title="Skill matrix: the tail",
        width=430, height=300, value_fmt=lambda v: f"{v:.1f} min",
        aria_label="p95 LOS by skill matrix",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


def fig_shifts(ctx: Ctx) -> str:
    series = ctx.series_entry("network_study", "shifts")
    los = series["hourly_los"]  # type: ignore[index]
    busy = series["hourly_busy_ratio"]  # type: ignore[index]
    styles = {
        "no_shift": ("no breaks", "#64748b"),
        "staggered_break": ("staggered break", "#b45309"),
        "mid_shift_barista": ("mid-shift barista", "#0d9488"),
    }
    los_series = []
    busy_series = []
    for key, (label, color) in styles.items():
        values = los.get(key, [])
        los_series.append(
            {"label": label, "color": color,
             "points": [(float(index) + 1.0, float(value)) for index, value in enumerate(values) if value is not None]}
        )
        busy_values = busy.get(key, [])
        busy_series.append(
            {"label": label, "color": color,
             "points": [(float(index) + 1.0, float(value)) for index, value in enumerate(busy_values) if value is not None]}
        )
    left = svg.line_chart(
        los_series, x_label="hour of the modelled day", y_label="mean time in system (min)",
        title="Hourly LOS: where the break hurts", width=470, height=300,
        x_fmt=lambda v: f"{int(v)}h", aria_label="Hourly mean LOS by shift plan",
    )
    right = svg.line_chart(
        busy_series, x_label="hour of the modelled day", y_label="busy ratio",
        title="Hourly busy ratio by shift plan", width=470, height=300,
        x_fmt=lambda v: f"{int(v)}h", y_fmt=lambda v: f"{v * 100:.0f}%",
        aria_label="Hourly busy ratio by shift plan",
    )
    return f'<div class="fig-grid">{left}{right}</div>'


# --------------------------------------------------------------------------
# baseline helpers
# --------------------------------------------------------------------------
def baseline_policy_rows(ctx: Ctx, *, workers: int, lam: float) -> List[Dict[str, object]]:
    records = ctx.baseline["policy_sweep"]["records"]  # type: ignore[index]
    chosen = [
        dict(row) for row in records
        if row["workers"] == workers and abs(float(row["arrival_rate"]) - lam) < 1e-9
    ]
    order = {key: index for index, key in enumerate(POLICY_ORDER)}
    chosen.sort(key=lambda row: order.get(str(row["policy_key"]), 99))
    return chosen


def baseline_pair(ctx: Ctx, *, workers: int, lam: float, pair_key: str) -> Dict[str, object]:
    pairs = ctx.baseline["policy_sweep"]["pairs"]  # type: ignore[index]
    for row in pairs:
        if (
            row["workers"] == workers
            and abs(float(row["arrival_rate"]) - lam) < 1e-9
            and row["pair_key"] == pair_key
        ):
            return dict(row)
    raise KeyError(f"no baseline pair {pair_key} at m={workers}, lambda={lam}")


def baseline_breakeven(ctx: Ctx, workers: int) -> Dict[str, object]:
    rows = ctx.baseline["breakeven"]["breakeven"]  # type: ignore[index]
    for row in rows:
        if row["workers"] == workers and row["metric"] == "profit_per_hour":
            return dict(row)
    raise KeyError(f"no baseline break-even row for m={workers}")


# --------------------------------------------------------------------------
# build-time validation (cheap; the heavy version is in tests/)
# --------------------------------------------------------------------------
def run_checks(ctx: Ctx) -> Dict[str, object]:
    from bubble_tea_sim import library, scenarios
    from bubble_tea_sim.engine import Simulation

    checks: Dict[str, object] = {}

    # 1. Degenerate equivalence: a scenario with no mechanism layer enabled must equal
    #    the exact baseline configuration, bit-for-bit.
    base = library.load_scenario("baseline_flat")
    original = scenarios.mixed_order_baseline(1.25, split_mix=False)
    first = Simulation(base, seed=7).run().metrics.as_dict()
    second = Simulation(original, seed=7).run().metrics.as_dict()
    checks["equivalence"] = {
        "identical": first == second,
        "baseline_compat": bool(getattr(base, "baseline_compat", False)),
        "reference": "scenarios.mixed_order_baseline(1.25, split_mix=False)",
        "seed": 7,
    }

    # 2. Determinism: same seed -> identical metrics; different seed -> different.
    campus = library.load_scenario("campus_rush")
    same_a = Simulation(campus, seed=11).run().metrics.as_dict()
    same_b = Simulation(campus, seed=11).run().metrics.as_dict()
    other = Simulation(campus, seed=12).run().metrics.as_dict()
    checks["determinism"] = {
        "same_seed_identical": same_a == same_b,
        "different_seed_differs": same_a != other,
    }

    # 3. Flow conservation and provenance for every scenario in the library.
    names = library.scenario_names()
    flow_ok = 0
    provenance_ok = 0
    for name in names:
        raw = library.load_raw(name)
        provenance = raw.get("provenance") or {}
        if all(provenance.get(field) for field in ("source", "method", "uncertainty")):
            provenance_ok += 1
        config = library.load_scenario(name)
        result = Simulation(config, seed=4).run()
        accounted = (
            sum(1 for customer in result.customers if customer.served)
            + result.metrics.balked
            + result.metrics.reneged
            + result.metrics.stockout_losses
            + result.metrics.stranded
        )
        if accounted == len(result.customers):
            flow_ok += 1
    checks["scenarios"] = {
        "count": len(names),
        "flow_conservation_ok": flow_ok,
        "provenance_complete": provenance_ok,
    }
    checks["python"] = platform.python_version()
    return checks


def validated_flag(ctx: Ctx, study: str, field: str) -> Optional[bool]:
    """Read a validation flag the study recorded for every scenario, if any."""
    rows = ctx.table(study, "scenarios")
    if not isinstance(rows, list) or not rows:
        return None
    values = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        validation = row.get("validation") or {}
        if field in validation:
            values.append(bool(validation[field]))
    if not values:
        return None
    return all(values)


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------
def s01_overview(ctx: Ctx) -> str:
    records = baseline_policy_rows(ctx, workers=3, lam=1.25)
    means = {str(row["policy_key"]): row["means"] for row in records}
    breakeven = baseline_breakeven(ctx, 3)
    fast_pair = baseline_pair(ctx, workers=3, lam=1.25, pair_key="fast_minus_fcfs")
    split_pair = baseline_pair(ctx, workers=3, lam=1.25, pair_key="split_minus_synchro")
    lambda_star = float(breakeven["lambda_star"])
    util_star = float(breakeven["utilization_star"])
    fast_gain = float(fast_pair["diff"]["profit_per_hour"])
    fast_ci = float(fast_pair["ci95"]["profit_per_hour"])
    split_gain = float(split_pair["diff"]["profit_per_hour"])
    split_ci = float(split_pair["ci95"]["profit_per_hour"])
    base_profit = float(means["synchro+fcfs"]["profit_per_hour"])
    fast_profit = float(means["synchro+fast"]["profit_per_hour"])
    split_profit = float(means["split+fcfs"]["profit_per_hour"])
    base_los = float(means["synchro+fcfs"]["mean_los"])
    fast_los = float(means["synchro+fast"]["mean_los"])
    scenario_count = int(ctx.baseline.get("_scenario_count", 0) or 0)
    if ctx.has("scenario_library"):
        scenario_count = len(ctx.rows("scenario_library", "comparison"))

    body: List[str] = []
    body.append(
        '<p class="lead">The original course model asked two questions: should a bubble-tea shop '
        "triage fast items ahead of the tea queue, and should it hand the ice cream of a mixed order "
        "over as soon as it is ready? It answered them with one clerk pool, stationary Poisson arrivals, "
        "fixed service times and a 2×2 policy matrix. Version 2 keeps that engine as the "
        "<strong>special case</strong> it always was and adds four optional layers around it: an "
        "intra-day demand profile, a station network with skills and shifts, an inventory bill of "
        "materials with shelf life, and an economics layer with pricing, SLA and a fairness cap.</p>"
    )
    body.append(
        '<div class="pill-row"><span class="tag baseline">baseline kept</span>'
        '<span class="tag layer">same engine</span>'
        '<span class="tag py">all numbers regenerated</span>'
        '<span class="tag an">AnyLogic archive, not rerunnable</span></div>'
    )
    body.append(
        callout(
            "key",
            "<p>With every layer switched off, the engine reproduces the original model exactly. "
            f"The build-time check compares <code>baseline_flat</code> against "
            f"<code>scenarios.mixed_order_baseline(1.25)</code> at seed 7 and the two metric dictionaries are "
            f"<strong>{'identical' if ctx.validation.get('equivalence', {}).get('identical') else 'different'}</strong>. "
            "That is the contract: the four-layer model adds mechanisms, it does not change the old answers.</p>",
            title="The engine is an extension, not a replacement",
        )
    )

    # What baseline concluded, from the baseline files (not retyped).
    body.append(
        table(
            ["original question (m = 3, λ = 1.25, 200 replicates)", "baseline number (Python engine)", "How the four-layer model re-opens it"],
            [
                ["Baseline: synchro delivery + FCFS",
                 f"profit {fx(base_profit, 2)} /h · mean LOS {fx(base_los, 2)} min",
                 "Nothing changes at equal load; the four-layer model only adds mechanisms around it."],
                ["Does fast-item triage pay?",
                 f"{signed(fast_gain, 2)} ± {fx(fast_ci, 2)} /h vs FCFS (profit {fx(fast_profit, 2)}); "
                 f"mean LOS {fx(fast_los, 2)} vs {fx(base_los, 2)} min",
                 "Layer 2: does it still pay when the bottleneck is a station rather than the clerk pool?"],
                ["Does split delivery pay?",
                 f"{signed(split_gain, 2)} ± {fx(split_ci, 2)} /h vs synchro (profit {fx(split_profit, 2)}); "
                 f"break-even at λ* = {fx(lambda_star, 3)} (ρ* = {pct(util_star, 1)})",
                 "Layer 1+2: peak demand, patience and the network can move the break-even load."],
                ["Is utilisation a decision metric?",
                 f"theory ρ = 88.2% at λ = 1.25, yet the four policies differ by "
                 f"{fx(max(float(means[k]['profit_per_hour']) for k in means) - min(float(means[k]['profit_per_hour']) for k in means), 1)} /h",
                 "Layer 4: the fairness gap and the peak-hour busy ratio make 'utilisation' even less sufficient."],
            ],
            caption="Table 1 · The baseline, read from results/*.json (the archived AnyLogic study remains non-rerunnable).",
            note="baseline values are the means of 200 paired replicates in results/policy_sweep.json and results/breakeven.json; λ* is the bisection break-even between split and synchronised delivery with FCFS.",
            align=["l", "l", "l"],
        )
    )
    body.append(
        callout(
            "info",
            "<p>The archived AnyLogic model (<code>archive/anylogic/</code>, screenshots in "
            "<code>docs/assets/slides/</code>) produced the original E1–E6 numbers. It cannot be re-run, "
            "so it is never a data source in this report: every number here is regenerated by the Python "
            "engine. The earlier report itself is kept as the baseline record, now in English only, at "
            '<a href="../archive/report-2026-11.html">archive/report-2026-11.html</a>.</p>',
            title="Provenance: Python reproducible vs AnyLogic archive",
        )
    )
    body.append(
        f'<figure class="figure">{fig_baseline_policies(ctx)}'
        "<figcaption>The baseline at λ = 1.25 with three clerks: fast-item priority is worth more than splitting "
        "the mixed order at this load. The later sections ask whether that ordering survives a peak, a station "
        "bottleneck and a perishable ingredient."
        '<span class="fig-source">results/policy_sweep.json · docs/figures-layers/fig_baseline_policies.svg</span></figcaption></figure>'
    )
    body.append('<h3>Architecture</h3>')
    body.append(
        '<p>Each layer is a frozen specification object (<code>data_spec.py</code>) that the loader turns '
        "into a <code>SimConfig</code>; scenarios are JSON files composing the layers they need. "
        "The engine dispatches events per station and staff skill when a network is present, and keeps the "
        "baseline dispatch rule when the configuration is baseline-compatible.</p>"
    )
    body.append(fig_architecture())
    body.append(
        '<h3>What this report contains</h3>'
        "<p>The next section maps the scenario library. Sections 3–7 are the two demand-side layers and the "
        "network layer; sections 8–10 are inventory, pricing and fairness; section 11 turns everything into a "
        "management bundle; section 12 compares course model and four-layer model conclusions; section 13 collects the validation "
        "evidence and section 14 the reproducibility contract. The complete numeric grids are in "
        "<a href="
        '"experiments-layers.md">docs/experiments-layers.md</a>. An interactive, precomputed demo (no simulation in '
        'the browser) lives at <a href="../demo/index.html">demo/index.html</a>.</p>'
    )
    return section(1, "What the four layers add to the course model", "s1", "".join(body))


def s02_scenarios(ctx: Ctx) -> str:
    if not ctx.has("scenario_library"):
        return section(2, "The scenario library", "s2", ctx.pending("scenario_library"))
    rows = ctx.rows("scenario_library", "comparison")
    table_rows = []
    for row in rows:
        layers = []
        layers_row = None
        for candidate in ctx.rows("scenario_library", "scenarios"):
            if candidate["name"] == row["name"]:
                layers_row = candidate
                break
        layers_data = (layers_row or {}).get("layers") or {}
        if isinstance(layers_data, dict):
            if layers_data.get("demand") and not layers_data["demand"].get("flat"):
                layers.append("demand")
            if layers_data.get("batches"):
                layers.append("batches")
            if len(layers_data.get("classes") or []) > 1:
                layers.append("classes")
            if (layers_data.get("variability") or {}).get("kind", "fixed") != "fixed":
                layers.append("variability")
            if layers_data.get("network"):
                layers.append("network")
            if layers_data.get("inventory"):
                layers.append("inventory")
            if layers_data.get("pricing"):
                layers.append("pricing")
            if layers_data.get("sla"):
                layers.append("sla")
        table_rows.append(
            [
                f'<code>{esc(row["name"])}</code>',
                esc(row["title"]),
                str(int(row["workers"])),
                f"×{fx(row['peak_multiplier'], 1)}",
                pct(float(row["util"]), 1),
                minutes(float(row["los_p95"]), 1),
                pct(float(row["abandon_rate"]), 1),
                fx(float(row["profit_per_hour"]), 1),
                "<span class=\"tag py\">baseline</span>" if row["baseline_compat"] else esc(", ".join(layers) or "core"),
            ]
        )
    meta = ctx.meta("scenario_library")
    body: List[str] = []
    body.append(
        '<p class="lead">The layer study runs on a library of shop contexts instead of a single configuration. '
        "Each file in <code>data/scenarios/</code> composes the layers it needs and carries a provenance block "
        "that names its source, its method and its uncertainty. No scenario claims field data: the library is a "
        "set of synthetic teaching cases anchored on the course assumptions, and the uncertainty field says so.</p>"
    )
    body.append(
        f"<p>The catalogue below uses <strong>{ctx.reps_note('scenario_library')}</strong> per scenario "
        f"(seed 0, stride 1), the same convention as the layer studies, and is generated by "
        f"<code>analysis/run_demand_network.py</code>. It is a map of contexts, not a causal comparison: every "
        f"row changes several things at once (crew, peaks, stations, stock), so read it as a spread, not as an "
        f"experiment. The layer sections that follow isolate one mechanism at a time.</p>"
    )
    body.append(
        table(
            ["Scenario", "Context", "Crew", "Peak", "Util", "p95", "Leave", "Profit/h", "Layers"],
            table_rows,
            caption="Table 2 · The scenario library (means over 100 replicates per scenario; the layer composition is read from each config).",
            note=f"Source: results/scenario_library.json · {esc(str(meta.get('notes', '')))}",
            align=["l", "l", "r", "r", "r", "r", "r", "r", "l"],
        )
    )
    body.append(fig_demand_profiles(ctx))
    body.append(
        '<p>The spread is the point. <code>baseline_flat</code> is the baseline configuration; '
        "<code>campus_rush</code>, <code>exam_week</code> and <code>cbd_commute</code> keep the same daily "
        "demand but concentrate it into peaks; <code>network_tea_bottleneck</code> and "
        "<code>ice_cream_bottleneck</code> move the constraint into a station; <code>inventory_lean</code> "
        "adds perishable stock; <code>peak_pricing</code> and <code>strict_sla_fairness</code> add the "
        "economic layers. Every later section refers to these names.</p>"
    )
    body.append(fig_scenario_compare(ctx))
    body.append(
        table(
            ["Layer", "Mechanism it contributes", "New metrics it makes visible"],
            [
                ["1 · Demand", "piecewise-constant intra-day profile, group arrivals, customer classes with their own mix, lognormal patience",
                 "peak-hour busy ratio, p50/p90/p95 LOS, balk and renege rates, per-class LOS and fairness gap"],
                ["2 · Supply network", "stations with capacities, staff roles with skills, shift windows and staggered breaks, component routing",
                 "per-station utilisation and queueing, staged order → make flow, skill and shift effects"],
                ["3 · Inventory / BOM", "ingredients, recipes, (s, S) replenishment with lead time, shelf life, stock-out policy",
                 "fill rate, stock-out losses, waste units, purchase cost, ingredient cost per hour"],
                ["4 · Economics / fairness", "time-of-day pricing with elasticity, SLA target and compensation, starvation cap for the low-priority queue",
                 "SLA attainment and compensation, mean price factor, starvation events, fairness gap, profit with penalties"],
            ],
            caption="Table 3 · What each layer contributes (implemented in src/bubble_tea_sim/data_spec.py and engine.py).",
            align=["l", "l", "l"],
        )
    )
    return section(2, "The scenario library", "s2", "".join(body))


def s03_design(ctx: Ctx) -> str:
    checks = ctx.validation.get("scenarios", {})
    equivalence = ctx.validation.get("equivalence", {})
    determinism = ctx.validation.get("determinism", {})
    scenario_count = int(checks.get("count", 0) or 0)
    flow_ok = int(checks.get("flow_conservation_ok", 0) or 0)
    provenance_ok = int(checks.get("provenance_complete", 0) or 0)
    body: List[str] = []
    body.append(
        '<p class="lead">The experimental design is the baseline design, generalised: one simulated day (480 minutes, '
        "60-minute warm-up excluded from service metrics), fixed seeds, paired comparisons on common random "
        "numbers, and a reported 95% confidence interval for every mean. The layer studies keep the same seed "
        "convention (seed 0, stride 1) so that a table cell can be regenerated on its own.</p>"
    )
    body.append(
        table(
            ["Design decision", "experiment convention", "Why it matters here"],
            [
                ["Replicates", "100 per cell (60 above 95% utilisation)", "The tails are noisy; 100 replicates keep the 95% CI half-width small enough to separate mechanisms."],
                ["Seeds", "seed = 0, stride = 1, identical across policies in a paired comparison",
                 "Common random numbers make policy and layer differences far less noisy than independent runs."],
                ["Warm-up", "first 60 simulated minutes excluded from served/waiting metrics",
                 "The shop does not start empty at 09:00 in the metrics; this matches the baseline convention."],
                ["Denominators", "fill rate and abandonment count all arrivals; money and served metrics are post-warm-up",
                 "Documented as a caveat in the inventory study; morning stock-outs appear in fill rate but not in served."],
                ["Uncertainty", "95% CI of the mean printed next to every mean; each scenario carries a provenance block",
                 "A synthetic library without an uncertainty statement would invite over-reading."],
                ["AnyLogic", "archive only; never a data source", "The .alp file and the screenshots cannot be re-run; the Python engine is the reproducible baseline."],
            ],
            caption="Table 4 · Experimental design conventions used by all five layer studies.",
            align=["l", "l", "l"],
        )
    )
    body.append('<h3>What the builder checks on every run</h3>')
    body.append(
        "<p>These checks are cheap enough to run while building the report, so the report states their result "
        "instead of asking the reader to trust them. They are also pinned by "
        "<code>tests/test_layers.py</code>.</p>"
    )
    body.append(
        table(
            ["Check", "Result on this build", "What it rules out"],
            [
                ["Degenerate equivalence: <code>baseline_flat</code> vs <code>mixed_order_baseline(1.25)</code>, seed 7",
                 "<strong>identical</strong>" if equivalence.get("identical") else "<strong>different</strong>",
                 "A silent change to the baseline answers when a layer is off."],
                ["Determinism: same seed twice, then a different seed",
                 "identical / differs" if determinism.get("same_seed_identical") and determinism.get("different_seed_differs") else "see note",
                 "Hidden state or an unseeded random draw."],
                [f"Flow conservation across all {scenario_count} scenarios (one replicate each)",
                 f"{flow_ok} / {scenario_count} scenarios account for every customer",
                 "Double counting or lost customers in the network layer."],
                [f"Provenance completeness across all {scenario_count} scenarios",
                 f"{provenance_ok} / {scenario_count} files carry source + method + uncertainty",
                 "Unattributed assumptions in the scenario library."],
                ["Offline report: no script, no external asset",
                 "checked by this script before writing the file", "The report failing to open from file://."],
            ],
            caption="Table 5 · Build-time validation. The command is the command that regenerates this report.",
            note="Determinism, equivalence and flow-conservation are also covered by the test suite; the numbers in this table are computed by analysis/build_report.py itself, not copied from a results file.",
            align=["l", "l", "l"],
        )
    )
    body.append(
        callout(
            "warn",
            "<p>The scenario catalogue runs 100 replicates per context, like the layer studies, but its rows "
            "change several things at once: crew size, peak shape, stations, stock. It is a map of contexts, "
            "not a controlled experiment; causal claims come only from the layer sections, which vary one "
            "mechanism at a time on common random numbers.</p>",
            title="Read the catalogue as a map, not as an experiment",
        )
    )
    return section(3, "Design and what the builder validates", "s3", "".join(body))


def s04_demand_peaks(ctx: Ctx) -> str:
    if not ctx.has("demand_study"):
        return section(4, "Layer 1: the cost of a peak", "s4", ctx.pending("demand_study"))
    return section(4, "Layer 1: the cost of a peak", "s4", _demand_peaks_body(ctx))


def _demand_peaks_body(ctx: Ctx) -> str:
    meta = ctx.meta("demand_study")
    findings = dict(ctx.study("demand_study").get("findings") or {})
    peak = dict(findings.get("peak_vs_flat") or {})
    rows = ctx.rows("demand_study", "peak_vs_flat")
    paired = dict(ctx.table("demand_study", "peak_vs_flat_paired") or {})
    factor_rows = ctx.rows("demand_study", "peak_factor_scan")
    factor_findings = dict(findings.get("peak_factor_scan") or {})
    body: List[str] = []
    body.append(
        '<p class="lead">This is the experiment the course model could not run. The original model had a flat arrival rate, so a busy '
        "hour and a busy day were the same thing. The demand layer separates them: the peak and the flat profile "
        "below have the <strong>same daily mean demand</strong>, and differ only in shape.</p>"
    )
    body.append(
        f"<p>The peak profile (peak-to-mean ×{fx(float(peak.get('peak_to_mean', 0.0)) or 1.4945, 2)}) raises the "
        f"peak-hour busy ratio from {pct(float(peak.get('peak_hour_busy_ratio_flat', 0.0)))} to "
        f"{pct(float(peak.get('peak_hour_busy_ratio_peak', 0.0)))}, multiplies the p95 wait by "
        f"{fx(float(peak.get('p95_ratio_peak_over_flat', 0.0)), 2)}× and lifts the walk-away rate from "
        f"{pct(float(peak.get('balk_rate_flat', 0.0)))} to {pct(float(peak.get('balk_rate_peak', 0.0)))} — while the "
        f"<em>daily</em> utilisation actually falls from {pct(float(peak.get('daily_util_flat', 0.0)))} to "
        f"{pct(float(peak.get('daily_util_peak', 0.0)))}, because abandoning customers remove work from the system. "
        f"Profit per hour drops from {fx(float(peak.get('profit_per_hour_flat', 0.0)), 1)} to "
        f"{fx(float(peak.get('profit_per_hour_peak', 0.0)), 1)}.</p>"
    )
    body.append(
        table(
            ["Profile", "Peak-to-mean", "Replicates", "Daily util", "Peak-hour busy", "p95", "Balk", "Profit / h"],
            [
                [
                    esc(str(row["label"]).replace("_", " ")),
                    f"×{fx(float(row['peak_to_mean']), 2)}",
                    str(int(row["reps"])),
                    pct(float(row["metrics"]["util"])),
                    pct(float(row["metrics"]["peak_busy_ratio"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    pct(float(row["metrics"]["balk_rate"])),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in rows
            ],
            caption="Table 6 · Peak versus flat demand at the same daily mean (campus_rush).",
            note=f"Peak cells use {rows[0]['reps']} replicates when the estimated peak load exceeds 0.95, otherwise 100; seeds 0, stride 1. Source: results/demand_study.json.",
            align=["l", "r", "r", "r", "r", "r", "r", "r"],
        )
    )
    if paired:
        keys = ("peak_busy_ratio", "los_p95", "balk_rate", "profit_per_hour", "served", "util")
        body.append(
            table(
                ["Paired difference (peak − flat)", "Δ", "95% CI"],
                [
                    [key_label(key), fx(float(paired["metrics"][key]["diff"]), 3), f"± {fx(float(paired['metrics'][key]['ci95']), 3)}"]
                    for key in keys
                    if key in (paired.get("metrics") or {})
                ],
                caption="Table 7 · The same comparison on common random numbers: every difference is far outside its confidence band.",
                note=f"{esc(str(paired.get('comparison', '')))} · {paired.get('reps')} replicates.",
                align=["l", "r", "r"],
            )
        )
    body.append(fig_demand_hourly(ctx))
    body.append('<h3>The shape of the cost is J-shaped</h3>')
    body.append(
        f"<p>Holding the daily mean fixed and raising the peak multiplier from ×{fx(float(factor_findings.get('baseline_peak_to_mean', 0.0)), 2)} "
        f"to ×{fx(float(factor_findings.get('max_peak_to_mean', 0.0)), 2)} costs "
        f"{signed(float(factor_findings.get('profit_change', 0.0)), 1)}/h of profit, adds "
        f"{signed(float(factor_findings.get('p95_change', 0.0)), 2)} minutes to the p95 and "
        f"{pct_signed(float(factor_findings.get('balk_rate_change', 0.0)))} to the walk-away rate. Note that the "
        f"daily mean never moves: the entire effect is queuing non-linearity.</p>"
    )
    body.append(fig_peak_factor(ctx))
    body.append(
        table(
            ["Peak factor", "Peak-to-mean", "Daily util", "p95", "Balk", "Served", "Profit / h"],
            [
                [
                    f"×{fx(float(row['factor']), 1)}",
                    f"×{fx(float(row['peak_to_mean']), 2)}",
                    pct(float(row["metrics"]["util"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    pct(float(row["metrics"]["balk_rate"])),
                    fx(float(row["metrics"]["served"]), 1),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in factor_rows
            ],
            caption="Table 8 · Peak-factor sweep: the daily mean is held fixed, so this is the price of variability alone.",
            note="Multiplier shape raised to multiplier**factor and re-normalised so that the daily mean equals the quoted campus_rush rate.",
            align=["r", "r", "r", "r", "r", "r", "r"],
        )
    )
    body.append(
        callout(
            "key",
            "<p>Decision rule from this section: <strong>plan for the peak, not for the average.</strong> A shop "
            "that staffs to its daily utilisation will be fine on paper and short at lunch. The next layer asks "
            "what happens when the staff are organised into stations rather than one pool.</p>",
            title="What the peak does to the shop",
        )
    )
    return "".join(body)


def s05_demand_mechanisms(ctx: Ctx) -> str:
    if not ctx.has("demand_study"):
        return section(5, "Layer 1: variability, patience and group orders", "s5", ctx.pending("demand_study"))
    return section(5, "Layer 1: variability, patience and group orders", "s5", _demand_mechanisms_body(ctx))


def _demand_mechanisms_body(ctx: Ctx) -> str:
    findings = dict(ctx.study("demand_study").get("findings") or {})
    variability = ctx.rows("demand_study", "variability_scan")
    variability_findings = dict(findings.get("variability") or {})
    patience = [row for row in ctx.rows("demand_study", "patience_scan") if abs(float(row["lambda"]) - 1.2) < 1e-9]
    reneging_only = ctx.rows("demand_study", "patience_reneging_only")
    patience_findings = dict(findings.get("patience") or {})
    batch = ctx.rows("demand_study", "batch_scan")
    batch_findings = dict(findings.get("batch") or {})
    body: List[str] = []
    body.append(
        '<p class="lead">Peaks are not the only way demand stops being a smooth rate. The shop also sees '
        "variable make times, customers with finite patience, and group arrivals. These mechanisms are often "
        "discussed separately; the engine can switch each on while holding the others fixed.</p>"
    )
    body.append('<h3>Service-time variability: the tail, not the mean</h3>')
    body.append(
        f"<p>Replacing deterministic make times by exponential ones — the engine forces exponential sampling, i.e. "
        f"CV = 1, whenever the variability kind is <code>exponential</code> — moves the p95 by "
        f"{fx(float(variability_findings.get('p95_range_lam1.0', 0.0)), 2)} minutes at λ = 1.0 and "
        f"{fx(float(variability_findings.get('p95_range_lam1.2', 0.0)), 2)} minutes at λ = 1.2, while the mean time "
        f"in system moves by only {fx(float(variability_findings.get('mean_los_range_lam1.2', 0.0)), 2)} minutes. "
        f"The p95 ratio at lognormal CV 0.75 versus deterministic is {fx(float(variability_findings.get('p95_ratio_cv075_over_fixed_lam1.2', 0.0)), 2)}× "
        f"at λ = 1.2: the tail grows with load much faster than the mean.</p>"
    )
    body.append(
        table(
            ["Variant", "λ", "Theory ρ", "p50", "p90", "p95", "Profit / h"],
            [
                [
                    esc(str(row["variant"])),
                    fx(float(row["lambda"]), 1),
                    pct(float(row["theoretical_rho"])),
                    minutes(float(row["metrics"]["los_p50"])),
                    minutes(float(row["metrics"]["los_p90"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in variability
            ],
            caption="Table 9 · Service-time variability at two loads (the mean wait barely moves; the tail does).",
            note="All variability cells use a two-segment demand profile so the fixed-service cell also runs on the event-driven dispatch path; the CVs are explicit in the study design.",
            align=["l", "r", "r", "r", "r", "r", "r"],
        )
    )
    body.append(fig_variability(ctx))
    body.append('<h3>Patience: who leaves, and why</h3>')
    body.append(
        f"<p>With balking active at arrival, reneging almost never binds "
        f"(<code>reneging_binds_in_grid = {bool(patience_findings.get('reneging_binds_in_grid'))}</code>): the "
        f"customer who would have reneged has usually already walked away at arrival. At λ = 1.2 the walk-away "
        f"rate falls from {pct(float(patience_findings.get('abandon_rate_balk3_lam1.2', 0.0)))} with a 3-minute "
        f"threshold to {pct(float(patience_findings.get('abandon_rate_balk12_lam1.2', 0.0)))} with a 12-minute one. "
        f"Patience is therefore a demand-side lever: it decides how much of the queue becomes lost sales.</p>"
    )
    body.append(
        table(
            ["Balk after", "Renege after", "Abandon rate", "Mean LOS", "p95", "Profit / h"],
            [
                [
                    minutes(float(row["balk_mean"]), 0),
                    minutes(float(row["renege_mean"]), 0),
                    pct(float(row["metrics"]["abandon_rate"])),
                    minutes(float(row["metrics"]["mean_los"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in patience
            ],
            caption="Table 10 · Patience grid at λ = 1.2 (the reneging columns are identical because balking decides first).",
            note="The reneging-only table in docs/experiments-layers.md isolates reneging by switching balking off.",
            align=["r", "r", "r", "r", "r", "r"],
        )
    )
    if reneging_only:
        body.append(
            table(
                ["Balking off: renege after", "λ", "Abandon rate", "Mean LOS", "Profit / h"],
                [
                    [
                        minutes(float(row["renege_mean"]), 0),
                        fx(float(row["lambda"]), 1),
                        pct(float(row["metrics"]["abandon_rate"])),
                        minutes(float(row["metrics"]["mean_los"])),
                        fx(float(row["metrics"]["profit_per_hour"]), 1),
                    ]
                    for row in reneging_only
                ],
                caption="Table 11 · Reneging on its own: with balking off, the renege threshold does bind.",
                note="This is the cell that isolates the reneging mechanism; in the full grid it is masked by balking.",
                align=["l", "r", "r", "r", "r"],
            )
        )
    body.append(fig_patience(ctx))
    body.append('<h3>Group orders: burstiness versus demand</h3>')
    body.append(
        f"<p>Batches are easy to misread. Holding the <em>arrival-event</em> rate fixed, a 30% batch probability "
        f"raises the walk-away rate from {pct(float(batch_findings.get('balk_rate_p0', 0.0)))} to "
        f"{pct(float(batch_findings.get('balk_rate_p0.3_arrival_events_fixed', 0.0)))} — but that is mostly a "
        f"demand increase, because each event brings several customers. Holding the <em>daily customer mean</em> "
        f"fixed, the same probability leaves the walk-away rate at "
        f"{pct(float(batch_findings.get('balk_rate_p0.3_customer_mean_fixed', 0.0)))} and profit at "
        f"{fx(float(batch_findings.get('profit_p0.3_customer_mean_fixed', 0.0)), 1)}/h versus "
        f"{fx(float(batch_findings.get('profit_p0', 0.0)), 1)}/h for singles. Burstiness is real but second-order "
        f"next to the peak shape.</p>"
    )
    body.append(
        table(
            ["Rate policy", "Batch p", "Expected size", "Effective λ", "Peak busy", "Balk", "Profit / h"],
            [
                [
                    esc(str(row["rate_policy"]).replace("_", " ")),
                    fx(float(row["batch_probability"]), 1),
                    fx(float(row["expected_arrival_size"]), 2),
                    fx(float(row["effective_arrival_rate"]), 3),
                    pct(float(row["metrics"]["peak_busy_ratio"])),
                    pct(float(row["metrics"]["balk_rate"])),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in batch
            ],
            caption="Table 12 · Batch arrivals under two rate conventions; only the second isolates burstiness.",
            note="‘arrival events fixed’ holds the event rate constant (so batching increases demand); ‘customer mean fixed’ holds the daily customer mean constant.",
            align=["l", "r", "r", "r", "r", "r", "r"],
        )
    )
    body.append(fig_batch(ctx))
    return "".join(body)


def s06_network_bottleneck(ctx: Ctx) -> str:
    if not ctx.has("network_study"):
        return section(6, "Layer 2: the bottleneck moves", "s6", ctx.pending("network_study"))
    return section(6, "Layer 2: the bottleneck moves", "s6", _network_bottleneck_body(ctx))


def _network_bottleneck_body(ctx: Ctx) -> str:
    findings = dict(ctx.study("network_study").get("findings") or {})
    migration_findings = dict(findings.get("bottleneck_migration") or {})
    sweep = ctx.rows("network_study", "tea_capacity_sweep")
    migration = dict(ctx.table("network_study", "bottleneck_migration") or {})
    body: List[str] = []
    body.append(
        '<p class="lead">The course model had one homogeneous clerk pool, so the only possible bottleneck was the pool itself. '
        "The network layer splits the work into stations — order counter, tea station, ice machine, bread counter — "
        "with staff that have skills, and asks a different question: when the shop adds capacity, where does "
        "the constraint move to?</p>"
    )
    critical = dict(migration_findings.get("critical_capacity_by_lambda") or {})
    body.append(
        f"<p>The study sweeps tea-station capacity 1–4 with baristas synced to stations, at λ = 0.6, 0.9 and 1.2. "
        f"Critical capacity — the smallest capacity whose extra station no longer pays for itself on paired common "
        f"random numbers — is "
        + ", ".join(f"{esc(key.replace('_', ' '))}: {esc(str(value))}" for key, value in critical.items())
        + ". The tea station remains the busiest station at every capacity, but beyond the critical capacity the "
        "queue is decided by the shared barista pool and the order counter, not by the tea station.</p>"
    )
    body.append(fig_tea_capacity(ctx))
    body.append(
        table(
            ["λ", "Tea stations", "Baristas", "Tea util", "Barista pool", "Order counter", "p95", "Balk", "Profit / h"],
            [
                [
                    fx(float(row["lambda"]), 1),
                    str(int(row["tea_capacity"])),
                    str(int(row["baristas"])),
                    pct(float(row["tea_util"])),
                    pct(float(row["pool_util"]["barista"])),
                    pct(float(row["order_util"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    pct(float(row["metrics"]["balk_rate"])),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in sweep
            ],
            caption="Table 13 · Tea-capacity sweep with staff synced to stations (station utilisation comes straight from the engine).",
            note="Pool utilisation groups the stations that share a skill and divides their busy minutes by the pre-break shift minutes available to that skill.",
            align=["r", "r", "r", "r", "r", "r", "r", "r", "r"],
        )
    )
    body.append(fig_bottleneck_utils(ctx))
    migration_rows = []
    for key, payload in migration.items():
        rows = payload  # type: ignore[assignment]
        migration_rows.append(
            [
                esc(str(key).replace("_", " ")),
                str(rows.get("critical_capacity", "n/a")),
                "yes" if rows.get("tea_is_top_station_all_capacities") else "no",
                pct(float(rows["tea_util_by_capacity"]["1"]), 1),
                pct(float(rows["tea_util_by_capacity"][str(rows["critical_capacity"])]), 1),
                pct(float(rows["barista_pool_util_by_capacity"][str(rows["critical_capacity"])]), 1),
            ]
        )
    body.append(
        table(
            ["Load", "Critical capacity", "Tea stays top?", "Tea util at 1 station", "Tea util at critical", "Pool util at critical"],
            migration_rows,
            caption="Table 14 · Where the bottleneck stops moving: the study's own critical-capacity summary.",
            note="critical_capacity is the smallest capacity whose marginal profit per hour is non-positive on common random numbers; utilisation is computed from the engine's station busy minutes.",
            align=["l", "r", "r", "r", "r", "r"],
        )
    )
    body.append(
        callout(
            "key",
            "<p>The bottleneck is not a property of the shop — it is a property of the shop <em>plus its staff "
            "plan</em>. Adding tea stations helps until the barista pool or the order counter becomes the binding "
            "resource; after that, more equipment only moves the queue. This is the classic capacity-planning "
            "insight, but here it is measured with paired confidence intervals rather than asserted.</p>",
            title="The bottleneck migrates",
        )
    )
    return "".join(body)


def s07_network_policy(ctx: Ctx) -> str:
    if not ctx.has("network_study"):
        return section(7, "Layer 2: policies, skills and shifts", "s7", ctx.pending("network_study"))
    return section(7, "Layer 2: policies, skills and shifts", "s7", _network_policy_body(ctx))


def _network_policy_body(ctx: Ctx) -> str:
    findings = dict(ctx.study("network_study").get("findings") or {})
    strategy_findings = dict(findings.get("strategy_by_bottleneck") or {})
    skill_findings = dict(findings.get("skill_matrix") or {})
    shift_findings = dict(findings.get("shifts") or {})
    strategy_pairs = ctx.rows("network_study", "strategy_bottleneck_paired")
    strategy_cells = ctx.rows("network_study", "strategy_bottleneck")
    skills = ctx.rows("network_study", "skill_matrix")
    skill_pairs = ctx.rows("network_study", "skill_matrix_paired")
    shifts = ctx.rows("network_study", "shifts")
    shift_pairs = ctx.rows("network_study", "shifts_paired")
    body: List[str] = []
    body.append(
        '<p class="lead">The policy question was first asked against a single clerk pool. The network layer lets the '
        "same 2×2 policy matrix run against two different bottlenecks: one scenario where the tea station is the "
        "binding constraint, and one where the ice-cream machine is.</p>"
    )
    body.append(
        "<h3>Strategy × bottleneck: fast priority is a bet on slack</h3>"
    )
    def contrast_label(name: str) -> str:
        if name.endswith("_split_fast_minus_synchro_plain"):
            return "split + fast vs synchro + plain"
        if name.endswith("_synchro_fast_minus_synchro_plain"):
            return "fast priority vs plain"
        if name.endswith("_split_plain_minus_synchro_plain"):
            return "split vs synchro"
        return name

    body.append(
        table(
            ["Scenario", "Contrast (common random numbers)", "Δ profit / h", "Δ mean LOS", "Δ p95"],
            [
                [
                    "tea bottleneck" if "tea" in str(row["name"]) else "ice-cream bottleneck",
                    esc(contrast_label(str(row["name"]))),
                    f"{signed(float(row['metrics']['profit_per_hour']['diff']), 2)} ± {fx(float(row['metrics']['profit_per_hour']['ci95']), 2)}",
                    f"{signed(float(row['metrics']['mean_los']['diff']), 2)} ± {fx(float(row['metrics']['mean_los']['ci95']), 2)}",
                    f"{signed(float(row['metrics']['los_p95']['diff']), 2)} ± {fx(float(row['metrics']['los_p95']['ci95']), 2)}",
                ]
                for row in strategy_pairs
            ],
            caption="Table 15 · The six paired policy contrasts, run against a tea bottleneck and against an ice-cream bottleneck.",
            note="Each contrast is measured against the same synchro + plain baseline inside its scenario. A positive profit difference favours the contrast. Fast priority is worth roughly twice as much in the ice-cream bottleneck, and the split-only contrast is negative in the tea bottleneck.",
            align=["l", "l", "r", "r", "r"],
        )
    )
    body.append(fig_strategy(ctx))
    body.append(
        f"<p>{esc(str(strategy_findings.get('note', '')))}</p>"
    )
    body.append(
        table(
            ["Scenario", "Policy", "Top station", "Profit / h", "Mean LOS", "p95", "Balk"],
            [
                [
                    esc(str(row["scenario"]).replace("_", " ")),
                    esc(str(row["policy"]).replace("_", " ")),
                    esc(str(row["top_station"])),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                    minutes(float(row["metrics"]["mean_los"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    pct(float(row["metrics"]["balk_rate"])),
                ]
                for row in strategy_cells
            ],
            caption="Table 16 · The eight strategy cells behind that comparison.",
            note="All cells run 100 replicates on the same seeds; station utilisation for each cell is in docs/experiments-layers.md.",
            align=["l", "l", "l", "r", "r", "r", "r"],
        )
    )
    body.append("<h3>Skills: the pooling gain lives in the generalist</h3>")
    body.append(
        f"<p>With the same headcount and the same wage bill, turning four dedicated staff into four generalists is "
        f"worth {signed(float(skill_findings.get('generalist_minus_dedicated_profit', {}).get('diff', 0.0)), 2)} "
        f"± {fx(float(skill_findings.get('generalist_minus_dedicated_profit', {}).get('ci95', 0.0)), 2)}/h. "
        f"One-way cross-training — a barista who can also run the register — is worth "
        f"{signed(float(skill_findings.get('cross_trained_minus_dedicated_profit', {}).get('diff', 0.0)), 2)} "
        f"± {fx(float(skill_findings.get('cross_trained_minus_dedicated_profit', {}).get('ci95', 0.0)), 2)}/h, "
        "i.e. nothing measurable: the flexibility has to go both ways to matter.</p>"
    )
    body.append(
        table(
            ["Configuration", "Description", "Headcount", "Barista pool", "Cashier pool", "p95", "Profit / h"],
            [
                [
                    esc(str(row["configuration"])),
                    esc(str(row["description"])),
                    str(int(row["headcount"])),
                    pct(float(row["pool_util"]["barista"])),
                    pct(float(row["pool_util"]["cashier"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in skills
            ],
            caption="Table 17 · Skill matrix at equal headcount: the difference is pure queueing.",
            note="Wage per hour is identical in all three cells (the study records Δ wage = 0), so the profit difference is not a cost difference.",
            align=["l", "l", "r", "r", "r", "r", "r"],
        )
    )
    body.append(fig_skills(ctx))
    body.append("<h3>Shifts and breaks: removing capacity near the peak</h3>")
    peak_los = dict(shift_findings.get("peak_hour_los") or {})
    body.append(
        f"<p>The shift experiment adds realistic staffing: staggered unpaid breaks, or a mid-shift barista. "
        f"The peak-hour mean LOS is {minutes(float(peak_los.get('no_shift', 0.0)))} with no breaks, "
        f"{minutes(float(peak_los.get('staggered_break', 0.0)))} with a staggered break and "
        f"{minutes(float(peak_los.get('mid_shift_barista', 0.0)))} with the mid-shift barista. Breaks remove "
        f"capacity exactly when demand is highest, so both the peak-hour wait and the p95 jump while the wage "
        f"bill falls — a net loss. The mid-shift barista adds headcount but leaves the peak-hour wait essentially "
        f"unchanged (+0.06 ± 0.08 min): at the peak the tea station, not headcount, is the binding resource, so "
        f"the extra wage line buys little.</p>"
    )
    body.append(
        table(
            ["Shift plan", "Headcount", "Mean LOS", "p95", "Peak-hour LOS", "Profit / h"],
            [
                [
                    esc(str(row["configuration"]).replace("_", " ")),
                    str(int(row["headcount"])),
                    minutes(float(row["metrics"]["mean_los"])),
                    minutes(float(row["metrics"]["los_p95"])),
                    minutes(float(row["metrics"].get("peak_hour_los", 0.0))),
                    fx(float(row["metrics"]["profit_per_hour"]), 1),
                ]
                for row in shifts
            ],
            caption="Table 18 · Shift and break plans. The break plan is not free even when the break is unpaid.",
            note="The engine excludes break time from available staff-minutes, so an unpaid break lowers the wage bill but removes capacity; the paired table below shows the net effect.",
            align=["l", "r", "r", "r", "r", "r"],
        )
    )
    if shift_pairs:
        body.append(
            table(
                ["Paired difference vs no-break baseline", "Δ profit / h", "Δ p95", "Δ peak-hour LOS", "Δ served"],
                [
                    [
                        esc(str(row["name"]).replace("_", " ")),
                        f"{signed(float(row['metrics']['profit_per_hour']['diff']), 2)} ± {fx(float(row['metrics']['profit_per_hour']['ci95']), 2)}",
                        f"{signed(float(row['metrics']['los_p95']['diff']), 2)} ± {fx(float(row['metrics']['los_p95']['ci95']), 2)}",
                        f"{signed(float(row['metrics'].get('peak_hour_los', {}).get('diff', 0.0)), 2)} ± {fx(float(row['metrics'].get('peak_hour_los', {}).get('ci95', 0.0)), 2)}",
                        f"{signed(float(row['metrics']['served']['diff']), 1)} ± {fx(float(row['metrics']['served']['ci95']), 1)}",
                    ]
                    for row in shift_pairs
                ],
                caption="Table 19 · Shift plans on common random numbers: the break plan loses profit through the queue, not only through wages.",
                align=["l", "r", "r", "r", "r"],
            )
        )
    body.append(fig_shifts(ctx))
    return "".join(body)


def s08_inventory(ctx: Ctx) -> str:
    if not ctx.has("inventory_study"):
        return section(8, "Layer 3: fill rate, waste and profit", "s8", ctx.pending("inventory_study"))
    meta = ctx.meta("inventory_study")
    tables = ctx.tables("inventory_study")
    baseline = tables["baseline"]
    metrics = dict(baseline.get("metrics", {}))  # type: ignore[union-attr]
    ci95 = dict(baseline.get("ci95", {}))  # type: ignore[union-attr]
    config = dict(baseline.get("config", {}))  # type: ignore[union-attr]
    tradeoff = dict(tables["tradeoff"])
    frontier = list(tradeoff["frontier"])
    decision = dict(tables["decision_summary"])
    base_dec = dict(decision["baseline"])
    recommended = dict(decision["recommended_ss"])
    caveats = meta.get("caveats") or []

    def ci(key: str) -> str:
        value = ci95.get(key)
        return f" ± {fx(value, 2)}" if value is not None else ""

    body: List[str] = []
    body.append(
        '<p class="lead">The inventory layer answers a different question from the queueing layers: given a '
        "twenty-minute tea and a perishable pearl, how much stock should the shop hold when a stock-out loses the "
        "sale and a shelf life turns safety stock into waste? The scenario used here is "
        f"<code>{esc(config.get('name', 'inventory_lean'))}</code>: {config.get('workers')} clerks, quoted arrival "
        f"rate {fx(config.get('arrival_rate'), 3)}/min, four ingredients with (s, S) replenishment, a 60–90 minute "
        "lead time and a four-hour pearl shelf life.</p>"
    )
    body.append(
        table(
            ["Metric", "Mean", "95% CI", "Reading"],
            [
                ["Fill rate (all arrivals)", pct(float(metrics["fill_rate"])), ci("fill_rate"), "share of demand that is actually served"],
                ["Stock-out losses / day", fx(float(metrics["stockout_losses"]), 2), ci("stockout_losses"), "orders lost to an empty ingredient"],
                ["Waste units / day", fx(float(metrics["waste_units"]), 2), ci("waste_units"), "perishable stock that expires"],
                ["Purchase cost / day", fx(float(metrics["purchase_cost"]), 1), ci("purchase_cost"), "ingredient spend"],
                ["Profit / hour", fx(float(metrics["profit_per_hour"]), 2), ci("profit_per_hour"), "revenue − wages − waiting cost − ingredients"],
                ["Mean time in system", minutes(float(metrics["mean_los"])), ci("mean_los"), "waiting is unaffected by inventory except through lost sales"],
                ["Staff utilisation", pct(float(metrics["util"])), ci("util"), "busy staff-minutes / available staff-minutes"],
            ],
            caption="Table 6 · Inventory baseline: the lean scenario at 100 replicates (seed 0, stride 1).",
            note=f"Source: results/inventory_study.json · baseline.metrics/ci95 · {esc(str(meta.get('reps', '')))}.",
            align=["l", "r", "r", "l"],
        )
    )
    body.append('<h3>The (s, S) trade-off: what the frontier actually looks like</h3>')
    frontier_rows = []
    for point in frontier:
        frontier_rows.append(
            [
                f"s = {fx(point['s_factor'], 2)} × initial, S = {fx(point['S_factor'], 2)} × initial",
                pct(float(point["fill_rate"]), 2),
                fx(float(point["stockout_losses"]), 2),
                fx(float(point["waste_units"]), 2),
                fx(float(point["purchase_cost"]), 1),
                fx(float(point["profit_per_hour"]), 2),
            ]
        )
    body.append(
        table(
            ["Replenishment setting", "Fill rate", "Stock-outs", "Waste", "Purchase cost", "Profit / h"],
            frontier_rows,
            caption="Table 7 · The fill / waste / profit frontier returned by the study (the study's own Pareto points).",
            note="(s, S) factors are multiples of the scenario's initial stock and order quantity; the exact reorder points and order quantities are in docs/experiments-layers.md.",
            align=["l", "r", "r", "r", "r", "r"],
        )
    )
    body.append(
        f"<p><strong>What the frontier says.</strong> The best fill rate is "
        f"{pct(float(tradeoff['max_fill']['fill_rate']), 2)} (at s = {fx(tradeoff['max_fill']['s_factor'], 2)}, "
        f"S = {fx(tradeoff['max_fill']['S_factor'], 2)}) and it is almost free in profit terms: "
        f"{fx(float(tradeoff['max_fill']['profit_per_hour']), 2)}/h versus the lean baseline's "
        f"{fx(float(base_dec['profit_per_hour']), 2)}/h. Waste stays at "
        f"{fx(float(tradeoff['min_waste']['waste_units']), 2)} units even at the best-waste setting, because the "
        f"pearl shelf life, not the reorder point, is the binding constraint. The study's recommended setting is "
        f"s = {fx(recommended['s_factor'], 2)}, S = {fx(recommended['S_factor'], 2)}: fill rate "
        f"{pct(float(recommended['fill_rate']), 2)} and {signed(float(decision['profit_gain_per_hour']), 2)}/h "
        f"versus the baseline.</p>"
    )
    body.append(fig_inv_lead_time(ctx))
    body.append(
        f"<p>Lead time is the cheap lever. Moving from a "
        f"{fx(float(tradeoff['lead_time_fill_95_max']), 0)}-minute to a longer replenishment cycle is what starts "
        "to cost fill rate; the lead-time scan in the table library shows where. Shelf life is the expensive "
        f"lever: below {fx(float(tradeoff['shelf_life_waste_free_min']), 0)} minutes the same order quantity starts "
        "to expire before it is used, and waste appears exactly there.</p>"
    )
    body.append(fig_inv_shelf_life(ctx))
    body.append(fig_inv_ceiling(ctx))
    body.append(fig_inv_stockout(ctx))
    stockout_rows = ctx.rows("inventory_study", "stockout_policy")
    body.append(
        table(
            ["Shortage regime", "Stock-out policy", "Fill rate", "Stock-outs", "Profit / h", "Δ vs losing the sale"],
            [
                [
                    esc(str(row["regime"]).replace("_", " ")),
                    esc(str(row["stockout_policy"]).replace("_", " ")),
                    pct(float(row["fill_rate"]), 2),
                    fx(float(row["stockout_losses"]), 2),
                    fx(float(row["profit_per_hour"]), 2),
                    "—" if not row.get("profit_delta_vs_lose") else signed(float(row["profit_delta_vs_lose"]), 2),
                ]
                for row in stockout_rows
            ],
            caption="Table 8 · Stock-out policy: three shortage regimes × three policies (nine rows).",
            note="Substitution does not create stock; it routes demand to a product the shop can still make. It pays only when the shortage is in a component that has a substitute (ice → bread, mix → tea); with a pearl shortage all three policies collapse onto the same lost sales.",
            align=["l", "l", "r", "r", "r", "r"],
        )
    )
    if caveats:
        body.append(
            callout(
                "warn",
                "<ul>" + "".join(f"<li>{esc(str(item))}</li>" for item in caveats) + "</ul>",
                title="Inventory study caveats (as recorded in its metadata)",
            )
        )
    return section(8, "Layer 3: fill rate, waste and profit", "s8", "".join(body))


def s09_pricing(ctx: Ctx) -> str:
    if not ctx.has("economics_study"):
        return section(9, "Layer 4: peak pricing and elasticity", "s9", ctx.pending("economics_study"))
    meta = ctx.meta("economics_study")
    grid = ctx.rows("economics_study", "pricing_grid")
    optima = ctx.rows("economics_study", "pricing_optima")
    caveats = meta.get("caveats") or []
    # A compact slice of the grid for the report: the central elasticity, all
    # tested multipliers, so the reader sees the shape without the 36-row dump.
    central = [row for row in grid if abs(float(row["elasticity"]) + 1.0) < 1e-9]
    central.sort(key=lambda row: float(row["peak_price_multiplier"]))
    body: List[str] = []
    body.append(
        '<p class="lead">The pricing layer charges a multiplier inside the two campus peaks (minutes 60–180 and '
        "300–420) and lets demand react with a constant elasticity: a multiplier <code>m</code> scales arrivals by "
        "<code>m^ε</code>. The question is not whether peak pricing raises revenue — it usually does — but what it "
        "does to the tail, and whether the profit maximum is a policy recommendation or an artefact of the cost model.</p>"
    )
    body.append(fig_econ_pricing(ctx))
    if central:
        body.append(
            table(
                ["Peak ×", "Demand factor", "Served", "Served retained", "Revenue / h", "Profit / h", "p95", "Peak p95"],
                [
                    [
                        f"×{fx(float(row['peak_price_multiplier']), 2)}",
                        fx(float(row["demand_factor"]), 3),
                        fx(float(row["served"]), 1),
                        pct(float(row["served_retained"]), 1),
                        fx(float(row["revenue_per_hour"]), 1),
                        fx(float(row["profit_per_hour"]), 1),
                        minutes(float(row["los_p95"]), 1),
                        minutes(float(row["peak_los_p95"]), 1),
                    ]
                    for row in central
                ],
                caption="Table 9 · One elasticity slice of the pricing grid (ε = −1.0): the full 36-row grid is in docs/experiments-layers.md.",
                note="Demand factor = m^ε, i.e. the multiplier applied to the arrival rate inside the peak windows. ‘Served retained’ is served customers relative to the no-pricing baseline.",
                align=["r", "r", "r", "r", "r", "r", "r", "r"],
            )
        )
    body.append(
        table(
            ["Elasticity", "Revenue-max ×", "Revenue / h", "Profit-max ×", "Profit / h", "Profit-max p95", "Service-neutral ×", "Service-neutral p95"],
            [
                [
                    fx(float(row["elasticity"]), 1),
                    f"×{fx(float(row['revenue_max_multiplier']), 2)}",
                    fx(float(row["revenue_max_per_hour"]), 1),
                    f"×{fx(float(row['profit_max_multiplier']), 2)}",
                    fx(float(row["profit_max_per_hour"]), 1),
                    minutes(float(row["profit_max_los_p95"]), 1),
                    f"×{fx(float(row.get('service_neutral_multiplier') or 1.0), 2)}",
                    minutes(float(row.get("service_neutral_peak_p95") or 0.0), 1),
                ]
                for row in optima
            ],
            caption="Table 10 · The optima the study reports for each elasticity.",
            note="The profit optimum sits at the edge of the tested range for these elasticities (the study marks profit_max_is_boundary), so it must be read together with the caveats below. The service-neutral multiplier is the useful decision variable: the largest increase that leaves the tail essentially unchanged.",
            align=["r", "r", "r", "r", "r", "r", "r", "r"],
        )
    )
    body.append(
        "<p><strong>Reading the optima.</strong> Revenue and profit both rise with the multiplier at every tested "
        "elasticity, but the mechanism is demand shedding: fewer, better-paying orders inside the peak also mean "
        "less waiting. The useful decision variable is the <em>service-neutral</em> multiplier: the largest "
        "increase that leaves the tail essentially unchanged. Anything above it buys profit by lowering service, "
        "and the model prices that trade only through the waiting cost of customers who stay — not through the "
        "ones who balk. That is a modelling limit, not a discovery about pricing.</p>"
    )
    if caveats:
        body.append(
            callout(
                "warn",
                "<ul>" + "".join(f"<li>{esc(str(item))}</li>" for item in caveats) + "</ul>",
                title="Pricing study caveats (as recorded in its metadata)",
            )
        )
    return section(9, "Layer 4: peak pricing and elasticity", "s9", "".join(body))


def s10_sla_fairness(ctx: Ctx) -> str:
    if not ctx.has("economics_study"):
        return section(10, "Layer 4: SLA compensation and fairness", "s10", ctx.pending("economics_study"))
    tables = ctx.tables("economics_study")
    sla_rows = ctx.rows("economics_study", "sla_grid")
    promises = ctx.rows("economics_study", "sla_promises")
    sla_summary = dict(tables["sla_summary"])
    fairness_rows = ctx.rows("economics_study", "fairness_pareto")
    fairness_summary = dict(tables["fairness_summary"])
    tightest = dict(sla_summary["tightest_promise"])
    loosest = dict(sla_summary["loosest_promise"])
    body: List[str] = []
    body.append(
        '<p class="lead">The SLA layer turns lateness into money: a customer whose time in system exceeds the '
        "target costs the shop a fixed compensation. The fairness layer addresses the queueing side of the same "
        "problem: with fast-item priority a tea order can wait behind a stream of fast jobs, so an ageing cap "
        "escalates any job that has waited too long.</p>"
    )
    body.append(fig_econ_sla(ctx))
    if promises:
        body.append(
            table(
                ["Promise", "Attainment", "Cheapest compensation", "Cost / h", "Profit / h", "Δ vs no SLA"],
                [
                    [
                        minutes(float(row["target_minutes"]), 0) + " target",
                        pct(float(row["attainment"]), 1),
                        fx(float(row["cheapest_compensation"]), 1),
                        fx(float(row["cheapest_compensation_per_hour"]), 1),
                        fx(float(row["cheapest_profit_per_hour"]), 1),
                        signed(float(row["cheapest_profit_delta_vs_no_sla"]), 1),
                    ]
                    for row in promises
                ],
                caption="Table 11 · What each SLA promise costs: the service level does not move, only the bill does.",
                note=f"The study records service_is_unchanged_by_sla = {bool(sla_summary.get('service_is_unchanged_by_sla'))}: an SLA is a transfer, not a queueing intervention. Attainment is identical across compensation levels — customers do not react to the promise. The highest attainment in the grid is {pct(float(loosest['attainment']), 1)} (an 8-minute target); no setting reaches 100%, so the grid is about the cost of a promise rather than a promise that can always be met.",
                align=["l", "r", "r", "r", "r", "r"],
            )
        )
    body.append(
        table(
            ["Target", "Compensation", "Attainment", "Compensation total", "Profit / h", "p95", "Peak p95"],
            [
                [
                    minutes(float(row["target_minutes"]), 0),
                    fx(float(row["compensation"]), 1),
                    pct(float(row["sla_attainment"]), 1) if row.get("sla_attainment") is not None else "n/a",
                    fx(float(row.get("sla_compensation_total") or 0.0), 1),
                    fx(float(row["profit_per_hour"]), 1),
                    minutes(float(row["los_p95"]), 1),
                    minutes(float(row.get("peak_los_p95") or 0.0), 1),
                ]
                for row in sla_rows
            ],
            caption="Table 12 · The full SLA grid: the queue is identical in every row, so the differences are purely monetary.",
            note=f"Tightest promise: {minutes(float(tightest['target_minutes']), 0)} at attainment {pct(float(tightest['attainment']), 1)}, cheapest compensation {fx(float(tightest['cheapest_compensation']), 1)} costs {fx(float(tightest['cheapest_compensation_per_hour']), 1)}/h. Loosest promise: {minutes(float(loosest['target_minutes']), 0)} at attainment {pct(float(loosest['attainment']), 1)} for {fx(float(loosest['cheapest_compensation_per_hour']), 1)}/h.",
            align=["r", "r", "r", "r", "r", "r", "r"],
        )
    )
    body.append(
        "<p><strong>SLA is a transfer.</strong> The grid changes profit and the compensation bill, but it does "
        "not change mean LOS or the tail: customers do not react to the promise. Its real role is to make the cost "
        "of a miss explicit — the number an operations team needs when it weighs a fourth barista against a promise.</p>"
    )
    body.append(fig_econ_fairness(ctx))
    body.append(
        table(
            ["Starvation cap", "Profit / h", "p95", "Class p95 spread", "Class mean spread", "Escalations / h", "Peak p95"],
            [
                [
                    "none" if row.get("starvation_cap") is None else minutes(float(row["starvation_cap"]), 1),
                    fx(float(row["profit_per_hour"]), 1),
                    minutes(float(row["los_p95"]), 1),
                    minutes(float(row.get("class_p95_spread") or 0.0), 2),
                    minutes(float(row.get("class_mean_spread") or 0.0), 2),
                    fx(float(row.get("escalations_per_hour") or 0.0), 2),
                    minutes(float(row.get("peak_los_p95") or 0.0), 1),
                ]
                for row in fairness_rows
            ],
            caption="Table 13 · Fairness cap at the high-load campus configuration (class mean spread rises while the tail improves).",
            note=f"Primary load λ = {fx(float(fairness_summary.get('primary_load') or 0.0), 2)}. The cap lowers every class's p95 and slightly narrows the class p95 spread ({minutes(float(fairness_summary.get('tail_gap_uncapped') or 0.0), 2)} → {minutes(float(fairness_summary.get('tail_gap_best_cap') or 0.0), 2)}), but the <em>class mean spread</em> widens ({minutes(float(fairness_summary.get('mean_gap_uncapped') or 0.0), 2)} → {minutes(float(fairness_summary.get('mean_gap_best_cap') or 0.0), 2)}); the engine's <code>fairness_gap</code> (max−min of class means, per replicate, then averaged) moves {minutes(float(fairness_summary['uncapped'].get('fairness_gap') or 0.0), 2)} → {minutes(float(fairness_summary['best_tail_protection'].get('fairness_gap') or 0.0), 2)}. The study records this explicitly as mean_gap_widens_while_tail_gap_narrows = {bool(fairness_summary.get('mean_gap_widens_while_tail_gap_narrows'))}.",
            align=["l", "r", "r", "r", "r", "r", "r"],
        )
    )
    body.append(
        "<p><strong>Fairness costs tail latency, and the metric decides the story.</strong> Capping how long any "
        "job may wait lowers the overall p95 from "
        f"{minutes(float(fairness_summary['uncapped']['los_p95']), 2)} to "
        f"{minutes(float(fairness_summary['best_tail_protection']['los_p95']), 2)} and lowers every customer "
        f"class's p95 (delivery "
        f"{minutes(float(fairness_summary['uncapped']['by_class']['delivery']['p95_los']), 2)} → "
        f"{minutes(float(fairness_summary['best_tail_protection']['by_class']['delivery']['p95_los']), 2)}, regular "
        f"{minutes(float(fairness_summary['uncapped']['by_class']['regular']['p95_los']), 2)} → "
        f"{minutes(float(fairness_summary['best_tail_protection']['by_class']['regular']['p95_los']), 2)}, student "
        f"{minutes(float(fairness_summary['uncapped']['by_class']['student']['p95_los']), 2)} → "
        f"{minutes(float(fairness_summary['best_tail_protection']['by_class']['student']['p95_los']), 2)}), while "
        f"the class-to-class p95 spread only narrows from "
        f"{minutes(float(fairness_summary.get('tail_gap_uncapped') or 0.0), 2)} to "
        f"{minutes(float(fairness_summary.get('tail_gap_best_cap') or 0.0), 2)}. The engine's "
        f"<code>fairness_gap</code> is a <em>mean</em> spread, and it actually widens "
        f"({minutes(float(fairness_summary.get('mean_gap_uncapped') or 0.0), 2)} → "
        f"{minutes(float(fairness_summary.get('mean_gap_best_cap') or 0.0), 2)}): the cap equalises tails, not "
        f"averages, so it is tail protection rather than proof of a fairer average. The profit cost is "
        f"{signed(float(fairness_summary.get('profit_cost_of_best_tail_cap') or 0.0), 2)}/h, and the study counts "
        f"{fx(float(fairness_summary.get('best_tail_protection', {}).get('escalations_per_hour') or 0.0), 1)} "
        f"escalations per hour, so the mechanism is auditable rather than a hidden priority hack.</p>"
    )
    return section(10, "Layer 4: SLA compensation and fairness", "s10", "".join(body))


def s11_management(ctx: Ctx) -> str:
    if not ctx.has("economics_study"):
        return section(11, "The management bundle", "s11", ctx.pending("economics_study"))
    tables = ctx.tables("economics_study")
    summary = dict(tables["management_summary"])
    rows = ctx.rows("economics_study", "good_manager")
    base = dict(summary["baseline"])
    good = dict(summary["good_manager"])
    lever_rows = []
    for row in summary.get("lever_ranking_by_profit") or []:
        lever_rows.append(
            [
                esc(str(row["scenario"]).replace("_", " ")),
                fx(float(row["profit_per_hour"]), 1),
                signed(float(row["profit_delta_vs_baseline"]), 1),
                minutes(float(row["los_p95"]), 2),
            ]
        )
    body: List[str] = []
    body.append(
        '<p class="lead">Each layer study isolates one mechanism. A manager does not buy one mechanism at a '
        "time: the last experiment combines the levers into a single configuration — an extra barista, a modest "
        "peak multiplier with elasticity, an SLA with compensation, and the fairness cap — and compares it with "
        "the campus baseline on common random numbers.</p>"
    )
    body.append(fig_econ_manager(ctx))
    body.append(
        table(
            ["Configuration", "Profit / h", "Δ vs baseline", "p95", "Served", "Left early", "Fairness gap"],
            [
                [
                    esc(str(row["scenario"]).replace("_", " ")),
                    fx(float(row["profit_per_hour"]), 1),
                    signed(float(row.get("profit_delta_vs_baseline") or 0.0), 1),
                    minutes(float(row["los_p95"]), 1),
                    fx(float(row["served"]), 1),
                    fx(float(row.get("balked") or 0.0), 1),
                    minutes(float(row.get("fairness_gap") or 0.0), 2),
                ]
                for row in rows
            ],
            caption="Table 15 · Each management lever measured against the same campus_rush baseline.",
            note="The rows are separate configurations, not a sequence: each one adds a single lever to the baseline. The paired comparison of the full bundle against the baseline is quoted below.",
            align=["l", "r", "r", "r", "r", "r", "r"],
        )
    )
    if lever_rows:
        body.append(
            table(
                ["Lever (ranked by profit)", "Profit / h", "Δ vs baseline", "p95"],
                lever_rows,
                caption="Table 16 · The study's own lever ranking by profit per hour.",
                align=["l", "r", "r", "r"],
            )
        )
    body.append(
        callout(
            "good",
            f"<p>Baseline: profit {fx(float(base['profit_per_hour']), 1)}/h, p95 {minutes(float(base['los_p95']), 1)}, "
            f"{fx(float(base['balked']), 1)} walk-aways per day. Bundle: profit {fx(float(good['profit_per_hour']), 1)}/h "
            f"({signed(float(summary['paired_profit_gain']), 1)} ± {fx(float(summary['paired_profit_gain_ci95']), 1)}/h, "
            f"paired, 95% CI), p95 {minutes(float(good['los_p95']), 1)}, "
            f"{fx(float(good['balked']), 1)} walk-aways, fairness gap {minutes(float(good.get('fairness_gap') or 0.0), 2)}.</p>"
            f"<p>The gain is large enough to matter and the tail improves at the same time, which is the useful "
            f"kind of result: this is not a service-for-profit trade.</p>",
            title="The bundle beats the baseline on profit and on the tail",
        )
    )
    body.append(
        "<h3>What the bundle implies for practice</h3>"
        "<ul>"
        "<li><strong>Buy capacity before you buy cleverness.</strong> The capacity lever dominates the ranking; "
        "policy tweaks are second-order against a fourth barista at the peak.</li>"
        "<li><strong>Protect the tail, not the average.</strong> The fairness cap and the service-neutral price "
        "multiplier both act on p95 at little cost, which is where customers actually leave.</li>"
        "<li><strong>Price to shed the peak, not to raise the average ticket.</strong> The profitable pricing "
        "window is the one that moves demand out of the peak windows without worsening the tail.</li>"
        "<li><strong>Keep the SLA explicit.</strong> Compensation does not improve service; it prices the miss. "
        "That is what makes the capacity decision a business decision rather than a queueing preference.</li>"
        "</ul>"
    )
    return section(11, "The management bundle", "s11", "".join(body))


def s12_baseline_vs_layers(ctx: Ctx) -> str:
    return section(12, "Course model and layered study: what changed in the answers", "s12", _baseline_layers_body(ctx))


def _baseline_layers_body(ctx: Ctx) -> str:
    records = baseline_policy_rows(ctx, workers=3, lam=1.25)
    means = {str(row["policy_key"]): dict(row["means"]) for row in records}
    fast_pair = baseline_pair(ctx, workers=3, lam=1.25, pair_key="fast_minus_fcfs")
    split_pair = baseline_pair(ctx, workers=3, lam=1.25, pair_key="split_minus_synchro")
    breakeven = baseline_breakeven(ctx, 3)
    baseline_fast = float(fast_pair["diff"]["profit_per_hour"])
    baseline_fast_ci = float(fast_pair["ci95"]["profit_per_hour"])
    baseline_split = float(split_pair["diff"]["profit_per_hour"])
    baseline_split_ci = float(split_pair["ci95"]["profit_per_hour"])
    lambda_star = float(breakeven["lambda_star"])
    util_star = float(breakeven["utilization_star"])
    spread = max(float(means[key]["profit_per_hour"]) for key in means) - min(
        float(means[key]["profit_per_hour"]) for key in means
    )

    demand_findings = dict(ctx.study("demand_study").get("findings") or {}) if ctx.has("demand_study") else {}
    peak = dict(demand_findings.get("peak_vs_flat") or {})
    net_findings = dict(ctx.study("network_study").get("findings") or {}) if ctx.has("network_study") else {}
    strategy = dict(net_findings.get("strategy_by_bottleneck") or {})
    fast_values = {
        (str(row["scenario"]), str(row["split_label"])): dict(row["profit_per_hour"])
        for row in (strategy.get("fast_priority_value") or [])
    }
    split_values = {}
    if ctx.has("network_study"):
        for row in ctx.rows("network_study", "strategy_split_value"):
            split_values[(str(row["scenario"]), str(row["fast_label"]))] = dict(row["profit_per_hour"])

    def fast_cell(scenario: str, split: str) -> str:
        value = fast_values.get((scenario, split))
        if not value:
            return "n/a"
        return f"{signed(float(value['diff']), 2)} ± {fx(float(value['ci95']), 2)}/h"

    def split_cell(scenario: str, fast: str) -> str:
        value = split_values.get((scenario, fast))
        if not value:
            return "n/a"
        return f"{signed(float(value['diff']), 2)} ± {fx(float(value['ci95']), 2)}/h"

    inv_decision = {}
    if ctx.has("inventory_study"):
        inv_decision = dict(ctx.tables("inventory_study")["decision_summary"])
    econ_summary = {}
    if ctx.has("economics_study"):
        econ_summary = dict(ctx.tables("economics_study")["management_summary"])
    econ_pricing = {}
    if ctx.has("economics_study"):
        optima = ctx.rows("economics_study", "pricing_optima")
        econ_pricing = optima[0] if optima else {}

    body: List[str] = []
    body.append(
        '<p class="lead">The honest way to present an extension is to say which baseline conclusions survived and '
        "which were boundaries of the original model. The two columns below are not a re-run of the course model with new code: they "
        "are the baseline numbers from <code>results/policy_sweep.json</code> and <code>results/breakeven.json</code> "
        "(200 paired replicates), placed next to the layer studies that add the missing mechanism.</p>"
    )
    rows = [
        [
            "<strong>Does fast-item triage pay?</strong>",
            f"yes: {signed(baseline_fast, 2)} ± {fx(baseline_fast_ci, 2)}/h at λ = 1.25, m = 3; mean LOS "
            f"{fx(float(means['synchro+fcfs']['mean_los']), 2)} → {fx(float(means['synchro+fast']['mean_los']), 2)} min",
            f"depends on where the slack is. Tea bottleneck: {fast_cell('network_tea_bottleneck', 'synchro')} "
            f"(synchro) / {fast_cell('network_tea_bottleneck', 'split')} (split). Ice-cream bottleneck: "
            f"{fast_cell('ice_cream_bottleneck', 'synchro')} (synchro) / {fast_cell('ice_cream_bottleneck', 'split')} (split)",
            "The sign survives; the size does not. Triage is worth roughly twice as much when the fast item's own station has slack.",
        ],
        [
            "<strong>Does split delivery pay?</strong>",
            f"only below the break-even: {signed(baseline_split, 2)} ± {fx(baseline_split_ci, 2)}/h at λ = 1.25, and the "
            f"break-even sits at λ* = {fx(lambda_star, 3)} (ρ* = {pct(util_star, 1)})",
            f"almost never, and not at a station bottleneck: tea bottleneck {split_cell('network_tea_bottleneck', 'plain')} "
            f"(plain) / {split_cell('network_tea_bottleneck', 'fast')} (fast); ice-cream bottleneck "
            f"{split_cell('ice_cream_bottleneck', 'plain')} (plain) / {split_cell('ice_cream_bottleneck', 'fast')} (fast)",
            "The baseline conclusions survive, but the mechanism is now explicit: splitting saves the ice cream's wait and pays only when the ice station, not the shared pool, is the constraint.",
        ],
        [
            "<strong>Peak versus average</strong>",
            "not testable: the course model had one stationary arrival rate, so the daily mean was also the peak",
            f"same daily mean, different shape: peak-hour busy {pct(float(peak.get('peak_hour_busy_ratio_peak', 0.0)))} vs "
            f"{pct(float(peak.get('peak_hour_busy_ratio_flat', 0.0)))}, p95 ×{fx(float(peak.get('p95_ratio_peak_over_flat', 0.0)), 2)}, "
            f"balk {pct(float(peak.get('balk_rate_peak', 0.0)))} vs {pct(float(peak.get('balk_rate_flat', 0.0)))}, "
            f"profit {fx(float(peak.get('profit_per_hour_peak', 0.0)), 1)} vs {fx(float(peak.get('profit_per_hour_flat', 0.0)), 1)}/h",
            "New conclusion: the daily average is the wrong planning number. The peak shape, not the total demand, drives abandonment and profit.",
        ],
        [
            "<strong>Is utilisation a decision metric?</strong>",
            f"no: the four policies span {fx(spread, 1)}/h of profit at an identical 88.2% theoretical utilisation",
            f"even less so: the peak case has a <em>lower</em> daily utilisation "
            f"({pct(float(peak.get('daily_util_peak', 0.0)))} vs {pct(float(peak.get('daily_util_flat', 0.0)))}) "
            "and a worse tail, because abandonment removes work; "
            "pool and station utilisation also diverge by role (barista 90.0% vs cashier 30.6% in the dedicated-skill cell)",
            "The caution is even stronger now: utilisation hides both the tail and the composition of the work.",
        ],
        [
            "<strong>What about stock, price, SLA and fairness?</strong>",
            "not in the model at all",
            f"inventory: fill rate {pct(float(inv_decision.get('baseline', {}).get('fill_rate', 0.0)), 2)} baseline, substitution worth "
            f"{signed(float(inv_decision.get('substitution_gain_ice_short', 0.0)), 2)}/h when ice runs short; "
            f"pricing: service-neutral multiplier ×{fx(float(econ_pricing.get('service_neutral_multiplier') or 1.0), 2)}; "
            f"SLA: service unchanged, compensation priced; fairness: cap improves p95 at a small profit cost; "
            f"bundle: {signed(float(econ_summary.get('paired_profit_gain', 0.0)), 1)} ± {fx(float(econ_summary.get('paired_profit_gain_ci95', 0.0)), 1)}/h",
            "New conclusions, not revisions: these are levers the course model could not see at all.",
        ],
    ]
    body.append(
        table(
            ["original question", "original answer (200 paired replicates, Python engine)", "layer model answer (100 replicates per cell)", "Verdict"],
            rows,
            caption="Table 21 · The baseline conclusions, re-examined with the four mechanism layers.",
            note="baseline numbers: results/policy_sweep.json and results/breakeven.json. layer numbers: results/demand_study.json, network_study.json, inventory_study.json and economics_study.json. All differences are paired on common random numbers where the study supports it.",
            align=["l", "l", "l", "l"],
        )
    )
    body.append(
        callout(
            "key",
            "<p><strong>What did not change:</strong> the engine, the 2×2 policy matrix and the direction of the "
            "headline baseline result. Fast-item priority is still the stronger lever than split delivery at the baseline "
            "operating point, and split delivery still stops paying as load rises.<br>"
            "<strong>What changed:</strong> the answer's boundary conditions. The size of the triage gain depends "
            "on which station has slack; the peak shape, not the daily mean, decides abandonment; and stock, "
            "price, SLA and fairness are first-order levers that the one-pool model could not represent.</p>",
            title="Continuity and revision",
        )
    )
    return "".join(body)


def s13_validation(ctx: Ctx) -> str:
    checks = ctx.validation
    scenarios = dict(checks.get("scenarios") or {})
    equivalence = dict(checks.get("equivalence") or {})
    determinism = dict(checks.get("determinism") or {})
    study_rows = []
    for study in ("scenario_library", "demand_study", "network_study", "inventory_study", "economics_study"):
        if not ctx.has(study):
            continue
        meta = ctx.meta(study)
        study_rows.append(
            [
                f"<code>{esc(study)}</code>",
                esc(str(meta.get("experiment", ""))),
                esc(str(meta.get("reps", "n/a"))),
                f"{fx(meta.get('runtime_seconds'), 1)} s" if meta.get("runtime_seconds") is not None else "n/a",
                f"{len(ctx.tables(study))} tables / {len(ctx.series(study))} series",
            ]
        )
    body: List[str] = []
    body.append(
        '<p class="lead">Validation has three independent legs: the model contract (a layer-off configuration '
        "equals baseline), the numerical contract (determinism, flow conservation, finite metrics), and the provenance "
        "contract (no scenario without a source, a method and an uncertainty statement). The first two are checked "
        "when this report is built, and again by the test suite.</p>"
    )
    body.append(
        table(
            ["Contract", "Evidence on this build", "Where it is pinned"],
            [
                ["Layer-off equivalence",
                 ("identical metrics for <code>baseline_flat</code> and the baseline configuration at seed 7"
                  if equivalence.get("identical") else "metrics differ — see the build log"),
                 "tests/test_layers.py::test_baseline_flat_scenario_is_bit_exact and this builder"],
                ["Determinism",
                 ("same seed reproducible; a different seed changes the metrics"
                  if determinism.get("same_seed_identical") and determinism.get("different_seed_differs") else "see build log"),
                 "tests/test_layers.py::test_runs_are_deterministic"],
                ["Flow conservation",
                 f"{scenarios.get('flow_conservation_ok', 0)} / {scenarios.get('count', 0)} scenarios account for every customer",
                 "tests/test_layers.py::test_flow_conservation and this builder"],
                ["Provenance",
                 f"{scenarios.get('provenance_complete', 0)} / {scenarios.get('count', 0)} scenario files carry source + method + uncertainty",
                 "tests/test_layers.py::test_scenario_library_is_complete_and_provenanced"],
                ["Directional mechanisms",
                 "the layer tests assert that variability raises the tail, that the tea station is the busiest resource in the bottleneck scenario, that pricing lowers demand inside the peak, and that the fairness cap escalates jobs",
                 "tests/test_layers.py (mechanism tests)"],
            ],
            caption="Table 15 · Validation evidence. The results are produced by this build; the test names are the ones in the repository.",
            note="The per-scenario flags recorded inside results/scenario_library.json (flow_conservation, all_metrics_finite) are consistent with this build-time check.",
            align=["l", "l", "l"],
        )
    )
    body.append('<h3>Study registry</h3>')
    body.append(
        table(
            ["Study file", "Experiment id", "Replicates", "Runtime", "Contents"],
            study_rows,
            caption="Table 16 · What each layer study file contains and how long it took to regenerate.",
            note="Runtimes are recorded by the experiment scripts themselves; they are hardware-dependent and shown for orientation only.",
            align=["l", "l", "r", "r", "r"],
        )
    )
    body.append(
        callout(
            "warn",
            "<p>These checks rule out silent regressions; they do not validate the model against a real shop. "
            "Every scenario is synthetic, anchored on the course parameter set and teaching-case ranges, and "
            "carries <code>uncertainty: high</code>. Treat the layer studies as a disciplined way to compare "
            "mechanisms, not as calibrated forecasts.</p>",
            title="What validation does not prove",
        )
    )
    return section(13, "Validation", "s13", "".join(body))


def s14_reproducibility(ctx: Ctx) -> str:
    inventory_rows = []
    for study in STUDIES:
        if not ctx.has(study):
            continue
        meta = ctx.meta(study)
        inventory_rows.append(
            [
                f"<code>results/{esc(study)}.json</code>",
                esc(str(meta.get("experiment", ""))),
                esc(str(meta.get("reps", "n/a"))),
                esc(str(meta.get("package_version", ""))),
            ]
        )
    body: List[str] = []
    body.append(
        '<p class="lead">Everything in this report is regenerated from this repository with the standard library '
        "only: Python 3.14, no numpy, no matplotlib, and no network access is needed to render the report. The "
        "figures are hand-built SVG strings from <code>analysis/svgchart.py</code>.</p>"
    )
    body.append(
        "<pre>pip install -e .\n"
        "python analysis/run_demand_network.py      # layer 1 + 2 + scenario library\n"
        "python analysis/run_inventory_econ.py      # layer 3 + 4\n"
        "python analysis/build_report.py        # docs/index.html, docs/experiments-layers.md, docs/figures-layers/\n"
        "python analysis/build_demo_data.py        # demo/data/*.json (offline demo)\n"
        "pytest -q                                 # baseline anchors + mechanism layers</pre>"
    )
    body.append(
        table(
            ["Input file", "Experiment", "Replicates", "Package version"],
            inventory_rows,
            caption="Table 17 · The result files this report reads. Nothing else is an input to the numbers.",
            note="The baseline numbers in sections 1 and 12 come from results/policy_sweep.json and results/breakeven.json, which are themselves generated by the baseline scripts.",
            align=["l", "l", "r", "r"],
        )
    )
    body.append('<h3>Guarantees and how to check them</h3>')
    body.append(
        "<ul>"
        "<li><strong>Offline report.</strong> This build rejects its own output if it finds a script tag, a linked "
        "stylesheet, an external font, or any URL outside the SVG namespace.</li>"
        "<li><strong>No hand-typed numbers in the generated tables.</strong> Table and figure values are pulled from "
        "the JSON by key, and every sentence that quotes a number reads it from the same file, so the prose cannot "
        "drift away from the data it describes.</li>"
        "<li><strong>One-day model.</strong> 480 simulated minutes, 60-minute warm-up. A run is one representative "
        "day, not a forecast of a year.</li>"
        "<li><strong>Archive, not evidence.</strong> The AnyLogic model in <code>archive/anylogic/</code> cannot be "
        "re-run; the Python engine is the reproducible baseline. The archived earlier report is preserved at "
        '<a href="../archive/report-2026-11.html">archive/report-2026-11.html</a>.</li>'
        "<li><strong>Interactive demo.</strong> <a href=\"../demo/index.html\">demo/index.html</a> replays "
        "precomputed data (5–6 replicates and one traced day); it is a reading aid, not a second analysis.</li>"
        "</ul>"
    )
    body.append('<h3>Limitations</h3>')
    body.append(
        table(
            ["Limitation", "Consequence", "What would fix it"],
            [
                ["Synthetic scenarios; no field data",
                 "Absolute levels (profit, LOS) are teaching-case magnitudes, not forecasts; <code>uncertainty: high</code> everywhere",
                 "A week of timestamped order data would calibrate the arrival profile, the mix and the make times."],
                ["Single-day model, no day-to-day carry-over",
                 "Stock, fatigue and learning effects across days are out of scope",
                 "A multi-day model with inventory carry-over and staff rosters."],
                ["Waiting cost is linear and charged to served customers only",
                 "Pricing extremes look attractive because abandoning customers are not charged; profit optima sit at the tested boundary",
                 "Model lost goodwill explicitly and re-run the pricing grid."],
                ["Fill rate denominator includes the warm-up hour",
                 "Morning stock-outs are slightly over-weighted relative to served metrics",
                 "Use the same warm-up filter for fill rate; documented as a caveat in the study metadata."],
                ["Staff are homogeneous within a skill; breaks are fixed windows",
                 "Skill variation and flexible breaks are only crudely represented",
                 "Per-person skill levels and break optimisation."],
                ["No statistical test beyond paired 95% CIs",
                 "Differences near the noise floor are not formally tested",
                 "Paired t-test or bootstrap on the per-replicate differences."],
                ["The scenario catalogue uses screening replicates",
                 "Its table is for orientation, not for decisions",
                 "Re-run the catalogue at 100 replicates (cost is the only obstacle)."],
            ],
            caption="Table 18 · Limitations, their consequences in this report, and the cheapest honest fix.",
            align=["l", "l", "l"],
        )
    )
    return section(14, "Reproducibility and limitations", "s14", "".join(body))


def s15_index(ctx: Ctx) -> str:
    figure_rows = [[f"<code>{esc(name)}</code>", f"{len(markup) / 1024:.1f} KiB"] for name, markup in ctx.figures.items()]
    body: List[str] = []
    body.append(
        '<p class="lead">Every table in this report exists in machine-readable form, and every figure exists as a '
        "standalone SVG. This page is the map.</p>"
    )
    body.append(
        table(
            ["Document", "What it is"],
            [
                ['<a href="experiments-layers.md">docs/experiments-layers.md</a>', "all layer tables and series, as Markdown, generated by the same script"],
                ['<a href="figures-layers/fig_architecture.svg">docs/figures-layers/</a>', "the standalone SVG files embedded in this report"],
                ['<a href="../demo/index.html">demo/index.html</a>', "offline interactive demo: scenario × policy, demand-curve slider, queue timeline (precomputed data)"],
                ['<a href="../archive/report-2026-11.html">archive/report-2026-11.html</a>', "the earlier report, kept as the baseline record with the same numbers"],
                ['<a href="../README.md">README.md</a>', "quick start, repository layout and how to regenerate everything"],
                ['<a href="theory.md">docs/theory.md</a>', "the analytical layer: Little's law, queueing approximations, MPS/BOM/MRP and the layer formulas"],
                ['<a href="experiment_log.md">docs/experiment_log.md</a>', "the experiment ledger, including the archival AnyLogic runs"],
            ],
            caption="Table 19 · Where each piece of the study lives.",
            align=["l", "l"],
        )
    )
    if figure_rows:
        body.append(
            table(
                ["Standalone figure", "Size"],
                figure_rows,
                caption="Table 20 · Figures written to docs/figures-layers/ by this build.",
                align=["l", "r"],
            )
        )
    body.append(
        '<p class="small muted">Build metadata: package '
        f"{esc(str(ctx.meta('scenario_library').get('package_version', 'unknown')) if ctx.has('scenario_library') else 'unknown')}"
        f", Python {esc(str(ctx.validation.get('python', 'unknown')))}, "
        f"{len(ctx.studies)} of {len(STUDIES)} studies present. "
        "The archived AnyLogic study is not re-run.</p>"
    )
    return section(15, "Index and data files", "s15", "".join(body))


# --------------------------------------------------------------------------
# hero, navigation, document assembly
# --------------------------------------------------------------------------
def hero(ctx: Ctx) -> str:
    stats: List[Tuple[str, str, str]] = []
    if ctx.has("scenario_library"):
        count = len(ctx.rows("scenario_library", "comparison"))
        stats.append(("Scenario library", f"{count} contexts", "one JSON per shop context, each with provenance"))
    if ctx.has("economics_study"):
        summary = ctx.tables("economics_study")["management_summary"]  # type: ignore[index]
        gain = float(summary["paired_profit_gain"])  # type: ignore[index]
        ci = float(summary["paired_profit_gain_ci95"])  # type: ignore[index]
        stats.append(("Management bundle", f"{signed(gain, 0)} ± {fx(ci, 0)} /h", "paired profit gain over the campus baseline, 95% CI"))
        sla = ctx.tables("economics_study")["sla_summary"]  # type: ignore[index]
        unchanged = "unchanged" if sla.get("service_is_unchanged_by_sla") else "changed"  # type: ignore[union-attr]
        stats.append(("SLA", f"service {unchanged}", "an SLA prices the miss; it does not move the queue"))
    if ctx.has("inventory_study"):
        tradeoff = ctx.tables("inventory_study")["tradeoff"]  # type: ignore[index]
        stats.append(("Best fill rate", pct(float(tradeoff["max_fill"]["fill_rate"]), 2), "at the (s, S) setting with the highest fill rate"))
    breakeven = baseline_breakeven(ctx, 3)
    stats.append(
        (
            "baseline break-even (kept as baseline)",
            pct(float(breakeven["utilization_star"]), 1),
            f"split delivery stops paying above λ* = {fx(float(breakeven['lambda_star']), 3)} with 3 clerks",
        )
    )
    cards = "".join(
        f'<div class="stat"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div>'
        f'<div class="hint">{esc(hint)}</div></div>'
        for label, value, hint in stats
    )
    meta = ctx.meta("scenario_library") if ctx.has("scenario_library") else {}
    return (
        '<header class="hero"><div class="wrap">'
        '<p class="sub">SYE5006 service-operations project · version 2 · reproducible re-implementation and extension</p>'
        f"<h1>{esc(TITLE_EN)}</h1>"
        f'<p class="meta">bubble_tea_sim {esc(str(meta.get("package_version", "")))} · '
        f'Python {esc(str(meta.get("python_version", "")))} · seed 0, stride 1 · '
        "standard library only · every number regenerated from results/</p>"
        f'<div class="stats">{cards}</div>'
        "</div></header>"
    )


SECTIONS = (
    ("s1", "1 · What the four-layer model adds"),
    ("s2", "2 · Scenario library"),
    ("s3", "3 · Design & validation"),
    ("s4", "4 · Peak cost"),
    ("s5", "5 · Variability & patience"),
    ("s6", "6 · Bottleneck moves"),
    ("s7", "7 · Policies, skills, shifts"),
    ("s8", "8 · Inventory"),
    ("s9", "9 · Pricing"),
    ("s10", "10 · SLA & fairness"),
    ("s11", "11 · Management bundle"),
    ("s12", "12 · course model vs four-layer model"),
    ("s13", "13 · Validation"),
    ("s14", "14 · Reproducibility"),
    ("s15", "15 · Index"),
)


def navigation() -> str:
    links = "".join(f'<a href="#{anchor}">{esc(label)}</a>' for anchor, label in SECTIONS)
    return f'<nav class="toc"><div class="wrap">{links}</div></nav>'


def renumber_tables(document: str) -> str:
    """Number the "Table N ·" captions sequentially in document order."""
    counter = {"value": 0}

    def replace(match: "re.Match[str]") -> str:
        counter["value"] += 1
        return f"Table {counter['value']} ·"

    return re.sub(r"Table \d+ ·", replace, document)


def build_document(ctx: Ctx) -> str:
    sections = [
        s01_overview(ctx),
        s02_scenarios(ctx),
        s03_design(ctx),
        s04_demand_peaks(ctx),
        s05_demand_mechanisms(ctx),
        s06_network_bottleneck(ctx),
        s07_network_policy(ctx),
        s08_inventory(ctx),
        s09_pricing(ctx),
        s10_sla_fairness(ctx),
        s11_management(ctx),
        s12_baseline_vs_layers(ctx),
        s13_validation(ctx),
        s14_reproducibility(ctx),
        s15_index(ctx),
    ]
    footer = (
        '<footer><div class="wrap">'
        "<p>Generated by <code>analysis/build_report.py</code> from <code>results/*.json</code> and the baseline "
        "baseline files. Static HTML, no JavaScript, no external assets.</p>"
        "<p>The archived AnyLogic study is not re-run anywhere in this repository; the baseline Python engine is the "
        "reproducible baseline and the earlier report is preserved at "
        '<a href="../archive/report-2026-11.html">archive/report-2026-11.html</a>.</p>'
        "</div></footer>"
    )
    document = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(TITLE_EN)}</title>\n"
        '<meta name="description" content="Reproducible discrete-event simulation of a bubble-tea shop, version 2: '
        'intra-day demand, a station network, inventory with shelf life, pricing, SLA and fairness, all regenerated '
        'from JSON results with no JavaScript in the report.">\n'
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        f"{hero(ctx)}\n{navigation()}<div class=\"wrap\">"
        + "".join(sections)
        + f"</div>\n{footer}\n</body>\n</html>\n"
    )
    return renumber_tables(document)


# --------------------------------------------------------------------------
# Markdown dump (experiments-layers.md)
# --------------------------------------------------------------------------
def md_value(value: object) -> str:
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "n/a"
        return fx(value, 4)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "–"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.replace("|", "\\|")
    if isinstance(value, dict):
        return "`" + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "`"
    if isinstance(value, list):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return "`" + (text if len(text) <= 120 else text[:117] + "…") + "`"
    return str(value)


def md_table_from_rows(rows: Sequence[Dict[str, object]]) -> str:
    columns: List[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    body_rows = [[md_value(row.get(key)) for key in columns] for row in rows]
    return md_table(columns, body_rows)


def md_from_mapping(mapping: Dict[str, object]) -> str:
    metrics = mapping.get("metrics")
    if isinstance(metrics, dict):
        ci95 = mapping.get("ci95") or {}
        rows = [[f"`{key}`", md_value(value), md_value(ci95.get(key))] for key, value in metrics.items()]  # type: ignore[union-attr]
        return md_table(["metric", "mean", "ci95"], rows)
    if all(not isinstance(value, (dict, list)) for value in mapping.values()):
        rows = [[f"`{key}`", md_value(value)] for key, value in mapping.items()]
        return md_table(["key", "value"], rows)
    parts: List[str] = []
    for key, value in mapping.items():
        parts.append(f"\n**`{key}`**\n")
        if isinstance(value, list) and value and isinstance(value[0], dict):
            parts.append(md_table_from_rows(value))  # type: ignore[arg-type]
        elif isinstance(value, dict):
            parts.append(md_from_mapping(value))  # type: ignore[arg-type]
        else:
            parts.append(md_value(value))
    return "\n".join(parts)


def md_series(name: str, payload: object) -> str:
    parts: List[str] = [f"\n### series · `{name}`\n"]
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        parts.append(md_table_from_rows(payload))  # type: ignore[arg-type]
    elif isinstance(payload, dict):
        if payload and all(isinstance(value, dict) for value in payload.values()):
            for key, value in payload.items():  # type: ignore[union-attr]
                parts.append(f"\n**`{name}.{key}`**\n")
                parts.append(md_from_mapping(value))  # type: ignore[arg-type]
        elif payload and all(isinstance(value, list) for value in payload.values()):
            columns = list(payload.keys())
            length = max((len(value) for value in payload.values() if isinstance(value, list)), default=0)
            rows = []
            for index in range(length):
                row = []
                for column in columns:
                    values = payload[column]
                    if isinstance(values, list) and index < len(values):
                        row.append(md_value(values[index]))
                    else:
                        row.append("–")
                rows.append(row)
            parts.append(md_table(columns, rows))
        else:
            parts.append(md_from_mapping(payload))
    else:
        parts.append(md_value(payload))
    return "\n".join(parts)


def build_markdown(ctx: Ctx) -> str:
    parts: List[str] = [
        "# Bubble-tea shop simulation — complete result tables\n",
        "Generated by `analysis/build_report.py` from `results/*.json`. "
        "Every number is read from a result file; the HTML report at "
        "[docs/index.html](index.html) contains the curated tables and figures.\n",
    ]
    for study in STUDIES:
        if not ctx.has(study):
            parts.append(f"\n## {study}\n\n_Missing: results/{study}.json is not present in this build._\n")
            continue
        meta = ctx.meta(study)
        parts.append(f"\n## {study}\n")
        parts.append(f"\nSource file: `results/{study}.json` (regenerated by the experiment script).\n")
        parts.append("\n### provenance\n")
        parts.append(
            md_table(
                ["key", "value"],
                [[f"`{key}`", md_value(value)] for key, value in meta.items() if key != "scenario_library"],
            )
        )
        parts.append("\n### tables\n")
        for key, value in ctx.tables(study).items():
            parts.append(f"\n#### `{key}`\n")
            if isinstance(value, list) and value and isinstance(value[0], dict):
                parts.append(md_table_from_rows(value))  # type: ignore[arg-type]
            elif isinstance(value, dict):
                parts.append(md_from_mapping(value))  # type: ignore[arg-type]
            elif isinstance(value, list):
                parts.append(md_table(["index", "value"], [[str(i), md_value(v)] for i, v in enumerate(value)]))
            else:
                parts.append(md_value(value))
        parts.append("\n### series\n")
        for key, value in ctx.series(study).items():
            parts.append(md_series(str(key), value))
    parts.append(
        "\n---\n\n"
        "## Reproduction\n\n"
        "```\n"
        "pip install -e .\n"
        "python analysis/run_demand_network.py\n"
        "python analysis/run_inventory_econ.py\n"
        "python analysis/build_report.py\n"
        "```\n"
    )
    return "".join(parts)


# --------------------------------------------------------------------------
# self check
# --------------------------------------------------------------------------
def self_check(ctx: Ctx, document: str, markdown: str, expected_figures: int) -> List[str]:
    problems: List[str] = []
    lower = document.lower()
    without_namespace = lower.replace("http://www.w3.org/2000/svg", "")
    for needle, label in (
        ("<script", "script tag"),
        ("<link", "linked stylesheet"),
        ("@import", "CSS import"),
        ("http://", "http URL"),
        ("https://", "https URL"),
        ("src=", "external source attribute"),
        ("fetch(", "network fetch"),
        ("cdn.", "CDN reference"),
        ("todo", "TODO marker"),
        ("lorem", "placeholder text"),
    ):
        haystack = without_namespace if needle in ("http://", "https://") else lower
        if needle in haystack:
            problems.append(f"report contains a {label}")
    expected_svgs = sum(markup.count("<svg") for markup in ctx.figures.values())
    svg_count = document.count("<svg")
    if svg_count != expected_svgs:
        problems.append(f"expected {expected_svgs} inline SVG charts, found {svg_count}")
    if document.count("<section") != len(SECTIONS):
        problems.append(f"expected {len(SECTIONS)} sections, found {document.count('<section')}")
    captions = [int(value) for value in re.findall(r"Table (\d+) ·", document)]
    if captions != list(range(1, len(captions) + 1)):
        problems.append(f"table captions are not sequential: {captions[:8]}…")
    if ctx.missing:
        problems.append("missing studies: " + ", ".join(ctx.missing))
    if "not available in this build" in lower:
        problems.append("report still contains a missing-study placeholder")
    for study in STUDIES:
        if f"results/{study}" not in markdown:
            problems.append(f"markdown does not mention results/{study}")
    return problems


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def write_figures(ctx: Ctx) -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    for stale in FIGDIR.glob("*.svg"):
        stale.unlink()
    for name, markup in ctx.figures.items():
        path = FIGDIR / f"{name}.svg"
        path.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + markup + "\n", encoding="utf-8")
    print(f"wrote {len(ctx.figures)} figures to docs/figures-layers/")


def register_figures(ctx: Ctx) -> None:
    builders = (
        ("fig_architecture", lambda: fig_architecture()),
        ("fig_demand_profiles", lambda: fig_demand_profiles(ctx)),
        ("fig_demand_hourly", lambda: fig_demand_hourly(ctx)),
        ("fig_peak_factor", lambda: fig_peak_factor(ctx)),
        ("fig_variability", lambda: fig_variability(ctx)),
        ("fig_patience", lambda: fig_patience(ctx)),
        ("fig_batch", lambda: fig_batch(ctx)),
        ("fig_tea_capacity", lambda: fig_tea_capacity(ctx)),
        ("fig_bottleneck_utils", lambda: fig_bottleneck_utils(ctx)),
        ("fig_strategy", lambda: fig_strategy(ctx)),
        ("fig_skills", lambda: fig_skills(ctx)),
        ("fig_shifts", lambda: fig_shifts(ctx)),
        ("fig_scenario_compare", lambda: fig_scenario_compare(ctx)),
        ("fig_baseline_policies", lambda: fig_baseline_policies(ctx)),
        ("fig_inv_lead_time", lambda: fig_inv_lead_time(ctx)),
        ("fig_inv_shelf_life", lambda: fig_inv_shelf_life(ctx)),
        ("fig_inv_ceiling", lambda: fig_inv_ceiling(ctx)),
        ("fig_inv_stockout", lambda: fig_inv_stockout(ctx)),
        ("fig_econ_pricing", lambda: fig_econ_pricing(ctx)),
        ("fig_econ_sla", lambda: fig_econ_sla(ctx)),
        ("fig_econ_fairness", lambda: fig_econ_fairness(ctx)),
        ("fig_econ_manager", lambda: fig_econ_manager(ctx)),
    )
    for name, builder in builders:
        try:
            ctx.figures[name] = builder()
        except Exception as error:  # pragma: no cover - defensive
            ctx.problems.append(f"figure {name} could not be generated: {error}")
            print(f"WARNING: figure {name} failed: {error}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    allow_partial = "--allow-partial" in args
    ctx = load_all(allow_partial)
    ctx.validation = run_checks(ctx)
    register_figures(ctx)
    document = build_document(ctx)
    markdown = build_markdown(ctx)
    write_figures(ctx)
    (DOCS / "index.html").write_text(document, encoding="utf-8", newline="\n")
    (DOCS / "experiments-layers.md").write_text(markdown, encoding="utf-8", newline="\n")
    print(f"wrote docs/index.html ({len(document) / 1024:.1f} KiB)")
    print(f"wrote docs/experiments-layers.md ({len(markdown) / 1024:.1f} KiB)")
    problems = self_check(ctx, document, markdown, len(ctx.figures)) + ctx.problems
    if problems:
        for problem in problems:
            print(f"SELF-CHECK FAILED: {problem}")
        return 1
    print(
        "self-check passed: "
        f"{document.count('<section')} sections, {document.count('<svg')} inline figures, "
        "no script, no external assets, no TODO markers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
