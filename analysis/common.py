"""Shared plumbing for the analysis scripts.

Every script in ``analysis/`` is a thin, reproducible experiment runner:

* it reads nothing but the installed ``bubble_tea_sim`` package,
* it writes exactly one JSON file into ``results/``,
* it uses a fixed seed / seed stride so that re-running it reproduces the same
  numbers byte for byte (no timestamps, no hash-ordering).

The helpers here keep the JSON schema consistent across experiments so that
``analysis/build_report.py`` can consume the files without special cases.

Run everything from the repository root::

    python analysis/run_policy_sweep.py
"""

from __future__ import annotations

import json
import math
import platform
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import bubble_tea_sim
from bubble_tea_sim import scenarios, stats
from bubble_tea_sim.params import TEA, BREAD, ICE, MIX, OrderMix, ServiceTimes, SimConfig

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"
FIGURES = DOCS / "figures"

# ---- global experimental design constants ---------------------------------
SEED = 0
SEED_STRIDE = 1
DEFAULT_REPS = 200
OVERLOAD_REPS = 60
OVERLOAD_UTIL = 0.95
SCHEMA_VERSION = 1

#: The 2x2 policy matrix, in a stable display order.
POLICY_MATRIX: Tuple[Tuple[bool, bool], ...] = (
    (False, False),
    (False, True),
    (True, False),
    (True, True),
)

#: Metrics whose confidence half-width is stored in every result file.
KEY_METRICS: Tuple[str, ...] = (
    "served",
    "mean_los",
    "mix_los",
    "mix_ice_hand",
    "util",
    "profit_per_hour",
    "revenue_per_hour",
    "flow_time_total",
    "waiting_cost_total",
    "los_tea",
    "los_bread",
    "los_ice",
    "balked",
    "reneged",
)


# ---- small formatting helpers --------------------------------------------
def policy_label(split_mix: bool, fast_priority: bool) -> str:
    """Human-readable policy name used in tables and charts."""
    delivery = "Split" if split_mix else "Synchro"
    triage = "Fast priority" if fast_priority else "FCFS"
    return f"{delivery} + {triage}"


def policy_key(split_mix: bool, fast_priority: bool) -> str:
    return f"{'split' if split_mix else 'synchro'}+{'fast' if fast_priority else 'fcfs'}"


def fmt(value: float, digits: int = 2) -> str:
    """Format a number for prose/tables; ``nan`` becomes ``n/a``."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:,.{digits}f}"


def pct(value: float, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def rel_dev(observed: float, expected: float) -> float:
    """Relative deviation ``(observed - expected) / |expected|`` (NaN-safe)."""
    if expected == 0 or expected is None or math.isnan(expected):
        return float("nan")
    return (observed - expected) / abs(expected)


def round_nested(value, digits: int = 6):
    """Recursively round floats inside dicts/lists before JSON serialisation."""
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return round(value, digits)
    if isinstance(value, dict):
        return {key: round_nested(item, digits) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [round_nested(item, digits) for item in value]
    return value


# ---- JSON I/O -------------------------------------------------------------
def meta(
    experiment: str,
    *,
    seed: int = SEED,
    seed_stride: int = SEED_STRIDE,
    extra: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Common provenance block stored in every result file."""
    payload: Dict[str, object] = {
        "experiment": experiment,
        "schema_version": SCHEMA_VERSION,
        "package_version": bubble_tea_sim.__version__,
        "python_version": platform.python_version(),
        "seed": seed,
        "seed_stride": seed_stride,
        "engine": "bubble_tea_sim.engine.Simulation (stdlib only)",
        "note": (
            "All numbers are produced by re-running the Python engine; no value "
            "in this file was typed in by hand. Re-running the same script with "
            "the same seed reproduces them exactly."
        ),
    }
    if extra:
        payload.update(extra)
    return payload


def write_json(name: str, payload: Dict[str, object]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / name
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(round_nested(payload), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def load_json(name: str) -> Dict[str, object]:
    path = RESULTS / name
    if not path.exists():
        raise SystemExit(
            f"missing {path.relative_to(ROOT)} - run the experiment script first"
        )
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ---- summary extraction ---------------------------------------------------
def paired_from_rows(
    rows_a: Sequence[Dict[str, float]],
    rows_b: Sequence[Dict[str, float]],
    *,
    metrics: Iterable[str] = KEY_METRICS,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Paired difference ``a - b`` computed from per-replicate metric rows.

    The experiment runners keep the per-replicate rows returned by
    :func:`bubble_tea_sim.stats.replicate`; because every policy in a matrix is
    run on the *same* seeds, the difference can be paired without re-running the
    simulation (this is what makes the sweep affordable at 200 replicates).
    """
    if len(rows_a) != len(rows_b):
        raise ValueError("paired rows must have the same length")
    keys = [key for key in metrics if key in rows_a[0] and key in rows_b[0]]
    diffs: Dict[str, float] = {}
    half_widths: Dict[str, float] = {}
    for key in keys:
        values = [row_a[key] - row_b[key] for row_a, row_b in zip(rows_a, rows_b)]
        diffs[key] = stats.mean(values)
        half_widths[key] = stats.ci95(values)
    return diffs, half_widths


def summary_block(summary: stats.ReplicateSummary) -> Dict[str, object]:
    """Compact, JSON-friendly view of a :class:`stats.ReplicateSummary`."""
    return {
        "config": summary.config.describe(),
        "reps": summary.reps,
        "means": {key: summary.means[key] for key in sorted(summary.means)},
        "ci95": {key: summary.ci95[key] for key in KEY_METRICS if key in summary.ci95},
    }


def paired_block(comparison: stats.PairedComparison) -> Dict[str, object]:
    return {
        "config_a": comparison.config_a.describe(),
        "config_b": comparison.config_b.describe(),
        "reps": comparison.reps,
        "diff": {key: comparison.diffs[key] for key in sorted(comparison.diffs)},
        "ci95": {key: comparison.ci95[key] for key in KEY_METRICS if key in comparison.ci95},
    }


# ---- theory layer ---------------------------------------------------------
def service_mixture(mix: OrderMix, times: ServiceTimes) -> Dict[str, float]:
    """Mean and standard deviation of clerk-minutes per customer.

    Split and synchronised delivery consume the same total clerk time, so this
    distribution does not depend on ``split_mix``.
    """
    shares = mix.as_dict()
    values: List[Tuple[float, float]] = []
    for kind, share in shares.items():
        jobs = times.for_kind(kind, split_mix=False)
        duration = sum(value for _, value in jobs)
        values.append((share, duration))
    mean = sum(share * duration for share, duration in values)
    variance = sum(share * (duration - mean) ** 2 for share, duration in values)
    return {
        "p_bar": mean,
        "sigma_p": math.sqrt(variance),
        "cv_p": math.sqrt(variance) / mean,
        "weighted_price": 0.0,  # filled in by callers that know the economics
    }


def theory_block(
    *,
    mix: OrderMix,
    times: ServiceTimes,
    workers_list: Sequence[int],
    lambdas: Sequence[float],
    weighted_price: float,
) -> Dict[str, object]:
    """Lecture 1-4 predictions for every (workers, lambda) pair.

    * utilisation ``U = lambda * p_bar / m`` (Lecture 2);
    * multi-server queueing approximation from Lecture 3::

          Tq = (p_bar/m) * U^[sqrt(2(m+1)) - 1] * (1 + CV_p^2)/2 / (1 - U)
          Tflow = Tq + p_bar
    """
    mixture = service_mixture(mix, times)
    p_bar = mixture["p_bar"]
    cv_p = mixture["cv_p"]
    predictions: List[Dict[str, object]] = []
    for workers in workers_list:
        exponent = math.sqrt(2 * (workers + 1)) - 1
        for lam in lambdas:
            utilisation = lam * p_bar / workers
            stable = utilisation < 1.0
            if stable:
                tq = (
                    (p_bar / workers)
                    * utilisation ** exponent
                    * (1 + cv_p ** 2)
                    / 2
                    / (1 - utilisation)
                )
                tflow = tq + p_bar
            else:
                tq = float("inf")
                tflow = float("inf")
            predictions.append(
                {
                    "workers": workers,
                    "arrival_rate": lam,
                    "utilization": utilisation,
                    "stable": stable,
                    "predicted_tq": tq,
                    "predicted_tflow": tflow,
                    "capacity_per_min": workers / p_bar,
                }
            )
    return {
        "p_bar": p_bar,
        "sigma_p": mixture["sigma_p"],
        "cv_p": cv_p,
        "weighted_price": weighted_price,
        "cv_a": 1.0,
        "queueing_formula": "Tq=(p/m)*U^[sqrt(2(m+1))-1]*(CV_a^2+CV_p^2)/2/(1-U)",
        "predictions": predictions,
    }


def build_config(
    lam: float,
    *,
    workers: int,
    split_mix: bool,
    fast_priority: bool,
    **kwargs,
) -> SimConfig:
    """A ``study`` configuration with an explicit, stable name."""
    return scenarios.study(
        lam,
        workers=workers,
        split_mix=split_mix,
        fast_priority=fast_priority,
        name=f"study-w{workers}-lam{lam:g}-{policy_key(split_mix, fast_priority)}",
        **kwargs,
    )


def reps_for(config: SimConfig, *, default: int = DEFAULT_REPS) -> int:
    """Use fewer replicates once the configuration is close to overload."""
    return OVERLOAD_REPS if config.utilization() >= OVERLOAD_UTIL else default


def progress(message: str) -> None:
    print(message, flush=True)


__all__ = [
    "DOCS",
    "FIGURES",
    "KEY_METRICS",
    "OVERLOAD_REPS",
    "OVERLOAD_UTIL",
    "POLICY_MATRIX",
    "RESULTS",
    "ROOT",
    "SCHEMA_VERSION",
    "SEED",
    "SEED_STRIDE",
    "build_config",
    "fmt",
    "load_json",
    "meta",
    "paired_block",
    "paired_from_rows",
    "pct",
    "policy_key",
    "policy_label",
    "progress",
    "rel_dev",
    "reps_for",
    "round_nested",
    "service_mixture",
    "summary_block",
    "theory_block",
    "write_json",
]
